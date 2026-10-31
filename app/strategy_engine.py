from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from app.database import (
    strategy_plan_create, strategy_plan_get, strategy_plan_list,
    strategy_item_update, trend_items_list, intelligence_report_list,
)

LANGUAGE_NAMES = {
    "en": "English", "id": "Bahasa Indonesia", "ja": "Japanese", "ar": "Arabic",
}
HOOKS = {
    "en": ["The mistake most beginners make about {topic}", "Before you try {topic}, know this", "A practical way to understand {topic}", "What nobody explains clearly about {topic}"],
    "id": ["Kesalahan yang sering terjadi saat membahas {topic}", "Sebelum mencoba {topic}, pahami ini", "Cara sederhana memahami {topic}", "Hal penting tentang {topic} yang sering terlewat"],
    "ja": ["{topic}を始める前に知っておきたいこと", "{topic}で見落としがちなポイント", "{topic}を分かりやすく解説"],
    "ar": ["ما الذي يجب معرفته عن {topic}؟", "أخطاء شائعة عند التعامل مع {topic}", "دليل مبسط لفهم {topic}"],
}
ANGLES = [
    "beginner explainer", "step-by-step tutorial", "common mistakes",
    "myth versus fact", "practical checklist", "case study with verified sources",
    "comparison of available approaches", "frequently asked questions",
    "expert concept explained simply", "actionable recap",
]


def _load_ideas(market: str, niche: str) -> list[dict]:
    rows = trend_items_list(market=market, niche=niche, limit=100)
    if not rows:
        rows = trend_items_list(market=market, limit=100)
    reports = intelligence_report_list(market=market, niche=niche, limit=10)
    ideas = []
    seen = set()
    for report in reports:
        try:
            data = json.loads(report["report_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        for idea in data.get("recommended_ideas", []):
            keyword = (idea.get("keyword") or "").strip()
            if keyword and keyword.casefold() not in seen:
                seen.add(keyword.casefold())
                ideas.append({"topic": keyword, "source": "saved_intelligence_report", "score": 60})
    for row in rows:
        title = (row.get("title") or "").strip()
        if title and title.casefold() not in seen:
            seen.add(title.casefold())
            ideas.append({"topic": title, "source": row.get("source", "trend_feed"), "score": row.get("relevance_score", 0)})
    if not ideas:
        ideas = [
            {"topic": niche + " for beginners", "source": "evergreen_fallback", "score": 35},
            {"topic": "common mistakes in " + niche, "source": "evergreen_fallback", "score": 32},
            {"topic": "practical guide to " + niche, "source": "evergreen_fallback", "score": 30},
            {"topic": "frequently asked questions about " + niche, "source": "evergreen_fallback", "score": 28},
        ]
    return sorted(ideas, key=lambda item: item["score"], reverse=True)


def generate_strategy(market: str, niche: str, language: str, channel_id: str | None,
                      start_date: str, days: int, videos_per_day: int) -> dict:
    lang = (language or "en").lower().split("-")[0]
    if lang not in HOOKS:
        lang = "en"
    start = date.fromisoformat(start_date)
    ideas = _load_ideas(market.upper(), niche)
    items = []
    for day_idx in range(days):
        planned = start + timedelta(days=day_idx)
        for slot in range(videos_per_day):
            idea = ideas[(day_idx * videos_per_day + slot) % len(ideas)]
            angle = ANGLES[(day_idx * videos_per_day + slot) % len(ANGLES)]
            topic = idea["topic"]
            hook_template = HOOKS[lang][(day_idx + slot) % len(HOOKS[lang])]
            hook = hook_template.format(topic=topic)
            title = f"{topic.title()}: {angle.replace('-', ' ').title()}"
            items.append({
                "day_number": day_idx + 1, "planned_date": planned.isoformat(),
                "slot": slot + 1, "topic": topic, "angle": angle,
                "title": title, "hook": hook, "format": "short",
            })
    summary = {
        "idea_sources": sorted({idea["source"] for idea in ideas}),
        "ideas_available": len(ideas),
        "total_content_pieces": len(items),
        "production_note": "Treat this calendar as a planning draft. Validate facts, originality, audience fit, and media rights before production and publication.",
        "language_name": LANGUAGE_NAMES.get(lang, "English"),
    }
    data = {
        "name": f"{niche.title()} — {market.upper()} {days}-Day Strategy",
        "market": market.upper(), "niche": niche, "language": lang,
        "channel_id": channel_id, "start_date": start_date,
        "days": days, "videos_per_day": videos_per_day,
        "plan_json": json.dumps(summary, ensure_ascii=False),
    }
    return strategy_plan_create(data, items)


def get_strategy(plan_id: str) -> dict | None:
    return strategy_plan_get(plan_id)


def list_strategies(market: str | None = None, niche: str | None = None, limit: int = 30) -> list[dict]:
    return strategy_plan_list(market=market, niche=niche, limit=limit)


def update_strategy_item(item_id: str, status: str, project_id: str | None = None) -> dict | None:
    return strategy_item_update(item_id, status, project_id)
