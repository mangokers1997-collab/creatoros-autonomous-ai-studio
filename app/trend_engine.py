from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from uuid import uuid4

from app.database import trend_items_upsert, trend_items_list

MARKETS = {
    "US": "United States", "GB": "United Kingdom", "CA": "Canada",
    "AU": "Australia", "JP": "Japan", "AE": "United Arab Emirates",
    "IN": "India", "ID": "Indonesia",
}
TRAFFIC_SCORE = [
    ("100000+", 100), ("50000+", 90), ("20000+", 82), ("10000+", 74),
    ("5000+", 66), ("2000+", 58), ("1000+", 50), ("500+", 42),
    ("200+", 34), ("100+", 26), ("50+", 18), ("0+", 10),
]


def _traffic_score(label: str) -> float:
    value = (label or "").replace(",", "").strip().lower()
    for prefix, score in TRAFFIC_SCORE:
        if value.startswith(prefix):
            return float(score)
    match = re.search(r"(\d+)", value)
    return min(90.0, float(match.group(1)) / 1000) if match else 10.0


def _score(title: str, traffic: str, niche: str, keywords: list[str]) -> float:
    text = title.casefold()
    niche_match = bool(niche and niche.casefold() in text)
    keyword_hits = sum(1 for word in keywords if word.casefold() in text)
    relevance = min(20, keyword_hits * 8) + (10 if niche_match else 0)
    return round(min(100.0, _traffic_score(traffic) * 0.7 + relevance), 1)


def fetch_google_trends(market: str, niche: str = "", keywords: list[str] | None = None) -> dict:
    code = market.upper()
    if code not in MARKETS:
        raise ValueError(f"Unsupported market. Choose: {', '.join(MARKETS)}")
    url = f"https://trends.google.com/trending/rss?geo={urllib.parse.quote(code)}"
    request = urllib.request.Request(url, headers={"User-Agent": "CreatorOS/0.1 (trend research; contact: admin@example.invalid)", "Accept": "application/rss+xml, application/xml"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = response.read(1_500_000)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Google Trends RSS request failed: {exc}") from exc

    root = ET.fromstring(payload)
    now = datetime.now(timezone.utc).isoformat()
    items = []
    for node in root.findall(".//item"):
        title = (node.findtext("title") or "").strip()
        if not title:
            continue
        traffic = ""
        published = (node.findtext("pubDate") or "").strip()
        link = (node.findtext("link") or "").strip()
        for child in node:
            if child.tag.endswith("approx_traffic"):
                traffic = (child.text or "").strip()
                break
        items.append({
            "id": str(uuid4()), "market": code, "title": title,
            "source": "Google Trends RSS", "source_url": link or url,
            "traffic_label": traffic, "published_at": published,
            "niche": niche, "relevance_score": _score(title, traffic, niche, keywords or []),
            "collected_at": now,
        })
    trend_items_upsert(items)
    return {
        "market": code, "market_name": MARKETS[code], "source": "Google Trends RSS",
        "feed_url": url, "items_fetched": len(items),
        "items": trend_items_list(market=code, niche=niche or None, limit=50),
        "notice": "Trend signal only: traffic values are approximate labels, not verified audience demand or guaranteed virality.",
    }
