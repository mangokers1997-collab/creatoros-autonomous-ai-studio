from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone

from app.database import trend_items_list, intelligence_report_create, intelligence_report_list

STOPWORDS = {
    "the","and","for","with","from","that","this","your","you","are","was","how","why",
    "what","when","where","into","about","after","before","tips","best","new","2026",
    "yang","dan","untuk","dari","dengan","ini","itu","cara","apa","bagaimana","paling",
}
COUNTRY_LANGUAGE = {"US":"en","GB":"en","CA":"en","AU":"en","JP":"ja","AE":"ar","IN":"en","ID":"id"}


def _tokens(text: str) -> list[str]:
    return [word for word in re.findall(r"[\w'-]{3,}", text.casefold()) if word not in STOPWORDS and not word.isdigit()]


def _youtube_search(query: str, market: str, max_results: int = 8) -> list[dict]:
    api_key = os.getenv("YOUTUBE_DATA_API_KEY", "").strip()
    if not api_key:
        return []
    params = urllib.parse.urlencode({
        "part":"snippet", "q":query, "type":"video", "regionCode":market,
        "maxResults":max_results, "order":"viewCount", "key":api_key,
    })
    url = "https://www.googleapis.com/youtube/v3/search?" + params
    request = urllib.request.Request(url, headers={"User-Agent":"CreatorOS/0.9"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read(1_500_000))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"YouTube Data API search failed: {exc}") from exc
    videos = []
    for item in payload.get("items", []):
        snippet = item.get("snippet", {})
        video_id = item.get("id", {}).get("videoId")
        if not video_id:
            continue
        videos.append({
            "video_id": video_id,
            "title": snippet.get("title", ""),
            "channel_title": snippet.get("channelTitle", ""),
            "published_at": snippet.get("publishedAt", ""),
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "description": (snippet.get("description", "") or "")[:500],
        })
    return videos


def _keyword_clusters(seed_keywords: list[str], trend_titles: list[str]) -> list[dict]:
    buckets: dict[str, dict] = defaultdict(lambda: {"terms": Counter(), "trend_matches": 0, "examples": []})
    all_phrases = [(word, "seed") for seed in seed_keywords for word in _tokens(seed)]
    for title in trend_titles:
        all_phrases.extend((word, title) for word in _tokens(title))
    for word, origin in all_phrases:
        buckets[word]["terms"][origin if origin == "seed" else "trend"] += 1
        if origin != "seed" and origin not in buckets[word]["examples"] and len(buckets[word]["examples"]) < 3:
            buckets[word]["examples"].append(origin)
    clusters = []
    for keyword, data in buckets.items():
        seed_count = data["terms"]["seed"]
        trend_count = data["terms"]["trend"]
        score = min(100, seed_count * 18 + trend_count * 16 + min(30, len(data["examples"]) * 10))
        clusters.append({
            "keyword": keyword, "seed_mentions": seed_count,
            "trend_mentions": trend_count, "trend_examples": data["examples"],
            "opportunity_score": score,
            "intent_hint": "informational" if keyword in {"how","why","guide","tips","cara","tutorial"} else "topic_discovery",
        })
    return sorted(clusters, key=lambda row: (row["opportunity_score"], row["trend_mentions"]), reverse=True)[:30]


def analyze_content_opportunities(market: str, niche: str, language: str,
                                  seed_keywords: list[str], competitor_queries: list[str]) -> dict:
    code = market.upper()
    if code not in COUNTRY_LANGUAGE:
        raise ValueError(f"Unsupported market: {code}")
    trend_rows = trend_items_list(market=code, niche=niche or None, limit=100)
    if not trend_rows:
        trend_rows = trend_items_list(market=code, limit=100)
    titles = [row["title"] for row in trend_rows]
    clusters = _keyword_clusters(seed_keywords, titles)
    competitor_results = []
    warnings = []
    if not os.getenv("YOUTUBE_DATA_API_KEY", "").strip():
        warnings.append("Competitor video lookup is disabled: configure YOUTUBE_DATA_API_KEY. Keyword clustering still works from seed terms and saved trend titles.")
    else:
        for query in competitor_queries[:5]:
            try:
                competitor_results.append({"query":query, "videos":_youtube_search(query, code, 8)})
            except RuntimeError as exc:
                warnings.append(str(exc))
    report = {
        "market": code, "niche": niche, "language": language or COUNTRY_LANGUAGE[code],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trend_items_used": len(titles), "keyword_clusters": clusters,
        "competitor_research": competitor_results,
        "content_gaps": [
            {"keyword": item["keyword"], "reason": "Trend mentions exist; consider an original explainer, comparison, case study, or practical tutorial."}
            for item in clusters if item["trend_mentions"] >= 2
        ][:10],
        "recommended_ideas": [
            {"priority": index + 1, "keyword": item["keyword"],
             "angle": f"{niche}: practical guide and examples around {item['keyword']}",
             "reason": f"Opportunity score {item['opportunity_score']}/100 from seed and trend text matches."}
            for index, item in enumerate(clusters[:10])
        ],
        "warnings": warnings,
        "methodology": "Heuristic text co-occurrence, not search-volume, keyword difficulty, competitor channel performance, or revenue estimates. YouTube results are public search results only and do not represent a complete competitor audit.",
    }
    stored = intelligence_report_create(code, niche, report["language"], json.dumps(report, ensure_ascii=False))
    report["report_id"] = stored["id"]
    return report


def get_intelligence_reports(market: str | None = None, niche: str | None = None, limit: int = 30) -> list[dict]:
    rows = intelligence_report_list(market=market, niche=niche, limit=limit)
    result = []
    for row in rows:
        try:
            parsed = json.loads(row["report_json"])
        except json.JSONDecodeError:
            parsed = {"error":"Stored report could not be parsed"}
        result.append({**row, "report": parsed})
    return result
