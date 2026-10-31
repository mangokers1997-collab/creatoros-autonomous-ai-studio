"""Evidence-aware content planning that combines trends, research and channel results."""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from app import database

LANGUAGE_HOOKS = {
    "id": ["Kesalahan yang sering terjadi tentang {topic}", "Sebelum mencoba {topic}, pahami ini", "Cara sederhana memahami {topic}", "Hal penting tentang {topic} yang sering terlewat"],
    "en": ["The mistake beginners make about {topic}", "Before trying {topic}, know this", "A practical guide to {topic}", "What people often miss about {topic}"],
    "ja": ["{topic}で見落としがちなポイント", "{topic}を始める前に知っておきたいこと"],
    "ar": ["أخطاء شائعة حول {topic}", "ما الذي يجب معرفته عن {topic}؟"],
}
ANGLES = ["beginner explainer", "step-by-step tutorial", "common mistakes", "myth versus fact", "practical checklist", "verified case study"]


def _norm(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9\u3040-\u30ff\u3400-\u9fff\u0600-\u06ff]+", (value or "").casefold()))


def _tokens(value: str) -> set[str]:
    return {x for x in _norm(value).split() if len(x) > 2}


def _duplicate(candidate: str, existing: list[str]) -> bool:
    a = _tokens(candidate)
    if not a:
        return True
    for value in existing:
        b = _tokens(value)
        if _norm(candidate) == _norm(value):
            return True
        if b and len(a & b) / max(1, len(a | b)) >= 0.72:
            return True
    return False


def build_content_brain_report(market: str, niche: str, language: str = "",
                               channel_id: str | None = None, limit: int = 12) -> dict:
    code = market.upper()
    channel = database.channel_get(channel_id) if channel_id else None
    if channel_id and not channel:
        raise ValueError("Channel not found")
    if channel and channel["target_market"].upper() != code:
        raise ValueError("Channel market does not match requested market")

    trends = database.trend_items_list(market=code, niche=niche, limit=100)
    if not trends:
        trends = database.trend_items_list(market=code, limit=100)
    reports = database.intelligence_report_list(market=code, niche=niche, limit=20)
    performance = database.channel_performance_records(channel_id=channel_id, limit=500)
    experiments = database.experiment_list(limit=100)

    format_scores = {}
    niche_scores = {}
    for row in performance:
        views = max(0, row.get("views") or 0)
        engagement = max(0, row.get("engagement_rate") or 0)
        score = min(25, views / 1000) + min(25, engagement * 2)
        format_scores[row.get("format") or "short"] = format_scores.get(row.get("format") or "short", []) + [score]
        niche_scores[row.get("niche") or niche] = niche_scores.get(row.get("niche") or niche, []) + [score]

    history = []
    plans = database.strategy_plan_list(market=code, niche=niche, limit=100)
    for plan in plans:
        detail = database.strategy_plan_get(plan["id"])
        if detail:
            history.extend(item.get("topic", "") for item in detail["items"])
    candidates = {}
    for row in trends:
        title = (row.get("title") or "").strip()
        if title:
            candidates.setdefault(_norm(title), {"topic": title, "trend_score": float(row.get("relevance_score") or 0),
                                                  "sources": ["trend_feed"], "evidence": []})
    for report in reports:
        try:
            data = json.loads(report["report_json"])
        except (ValueError, TypeError):
            continue
        for idea in data.get("recommended_ideas", []):
            topic = (idea.get("keyword") or idea.get("topic") or "").strip()
            if topic:
                entry = candidates.setdefault(_norm(topic), {"topic": topic, "trend_score": 0, "sources": [], "evidence": []})
                entry["sources"].append("saved_research")
                entry["evidence"].append("Found in saved content intelligence report")
        for cluster in data.get("keyword_clusters", []):
            topic = (cluster.get("keyword") or "").strip()
            if topic and len(topic) > 3:
                entry = candidates.setdefault(_norm(topic), {"topic": topic, "trend_score": 0, "sources": [], "evidence": []})
                entry["sources"].append("keyword_cluster")
                entry["trend_score"] = max(entry["trend_score"], float(cluster.get("opportunity_score") or 0) * 0.45)

    removed = []
    for key, item in list(candidates.items()):
        if _duplicate(item["topic"], history):
            removed.append(item["topic"])
            del candidates[key]

    if not candidates:
        for topic in [f"{niche} for beginners", f"common mistakes in {niche}",
                      f"practical checklist for {niche}", f"frequently asked questions about {niche}"]:
            candidates[_norm(topic)] = {"topic": topic, "trend_score": 25, "sources": ["evergreen_fallback"], "evidence": []}

    for item in candidates.values():
        score = min(65, item["trend_score"] * 0.65)
        if item["sources"]:
            score += min(15, len(set(item["sources"])) * 5)
        score += min(10, sum(format_scores.values(), []) and 5 or 0)
        if niche_scores.get(niche):
            score += min(10, sum(niche_scores[niche]) / len(niche_scores[niche]) / 5)
        item["priority_score"] = round(min(100, score), 1)
        item["priority"] = "high" if score >= 55 else "medium" if score >= 30 else "explore"
        item["angle"] = ANGLES[sum(ord(c) for c in item["topic"]) % len(ANGLES)]
        lang = (language or ("id" if code == "ID" else "ja" if code == "JP" else "ar" if code == "AE" else "en")).split("-")[0].lower()
        templates = LANGUAGE_HOOKS.get(lang, LANGUAGE_HOOKS["en"])
        item["hook"] = templates[sum(ord(c) for c in item["topic"]) % len(templates)].format(topic=item["topic"])
        item["reasons"] = list(dict.fromkeys(item["sources"] + item["evidence"]))
    ranked = sorted(candidates.values(), key=lambda x: (x["priority_score"], x["topic"]), reverse=True)[:limit]
    return {
        "market": code, "niche": niche, "channel": channel,
        "generated_at": date.today().isoformat(),
        "candidate_count": len(candidates), "excluded_duplicates": removed[:30],
        "recommendations": ranked,
        "evidence": {"trend_items": len(trends), "saved_research_reports": len(reports),
                     "published_video_records": len(performance),
                     "experiments_reviewed": len(experiments),
                     "performance_influenced_scoring": bool(performance)},
        "caveats": [
            "Priority is a transparent heuristic, not predicted views, revenue or virality.",
            "Channel performance is used only as a weak directional signal; it does not prove topic causation.",
            "Trend and saved-research coverage depends on data previously collected.",
            "Duplicate filtering compares recent saved strategy topics for the selected market and niche."
        ]
    }


def create_brain_strategy(market: str, niche: str, language: str, channel_id: str | None,
                          start_date: str, days: int, videos_per_day: int) -> dict:
    if not 1 <= days <= 90 or not 1 <= videos_per_day <= 5:
        raise ValueError("days must be 1-90 and videos_per_day must be 1-5")
    report = build_content_brain_report(market, niche, language, channel_id, limit=days * videos_per_day)
    recommendations = report["recommendations"]
    if not recommendations:
        raise ValueError("No content recommendations available")
    start = date.fromisoformat(start_date)
    items = []
    for index in range(days * videos_per_day):
        idea = recommendations[index % len(recommendations)]
        planned = start + timedelta(days=index // videos_per_day)
        items.append({
            "day_number": index // videos_per_day + 1, "planned_date": planned.isoformat(),
            "slot": index % videos_per_day + 1, "topic": idea["topic"],
            "angle": idea["angle"], "title": f"{idea['topic'].title()}: {idea['angle'].title()}",
            "hook": idea["hook"], "format": "short",
        })
    summary = {"engine": "content_brain", "evidence": report["evidence"],
               "recommendations": recommendations, "caveats": report["caveats"],
               "production_note": "Planning draft only. Review originality, facts, audience fit and media rights before production."}
    return database.strategy_plan_create({
        "name": f"Content Brain — {niche.title()} {market.upper()}",
        "market": market.upper(), "niche": niche, "language": language,
        "channel_id": channel_id, "start_date": start_date, "days": days,
        "videos_per_day": videos_per_day, "plan_json": json.dumps(summary, ensure_ascii=False),
    }, items)
