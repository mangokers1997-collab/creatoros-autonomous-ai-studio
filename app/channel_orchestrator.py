"""Portfolio view and collision-aware planning across multiple creator channels."""
from __future__ import annotations

from datetime import date, timedelta
from app import database
from app.content_brain import create_brain_strategy


def build_channel_orchestrator_overview() -> dict:
    channels = database.channel_list()
    all_plans = database.strategy_plan_list(limit=500)
    batches = database.production_batch_list(limit=200)
    jobs = database.publish_job_list(limit=500)
    projects = database.project_list(limit=500)
    output = []
    for channel in channels:
        channel_id = channel["id"]
        plans = [p for p in all_plans if p.get("channel_id") == channel_id]
        plan_ids = {p["id"] for p in plans}
        channel_batches = [b for b in batches if b.get("strategy_id") in plan_ids]
        channel_jobs = [j for j in jobs if j.get("channel_id") == channel_id]
        channel_projects = [p for p in projects if p.get("channel_id") == channel_id]
        item_status = {}
        for plan in plans:
            detail = database.strategy_plan_get(plan["id"])
            if detail:
                for item in detail["items"]:
                    status = item.get("status", "planned")
                    item_status[status] = item_status.get(status, 0) + 1
        output.append({
            **channel,
            "strategy_count": len(plans),
            "planned_items": sum(item_status.values()),
            "item_status": item_status,
            "project_count": len(channel_projects),
            "production_batches": len(channel_batches),
            "active_batches": sum(1 for b in channel_batches if b.get("status") in {"queued", "processing"}),
            "publishing_jobs": len(channel_jobs),
            "awaiting_approval": sum(1 for j in channel_jobs if j.get("status") == "awaiting_approval"),
            "scheduled_jobs": sum(1 for j in channel_jobs if j.get("status") == "scheduled"),
            "published_jobs": sum(1 for j in channel_jobs if j.get("status") == "published"),
            "failed_jobs": sum(1 for j in channel_jobs if j.get("status") == "failed"),
        })
    return {
        "channel_count": len(output),
        "configured_channels": output,
        "totals": {
            "strategies": sum(c["strategy_count"] for c in output),
            "projects": sum(c["project_count"] for c in output),
            "production_batches": sum(c["production_batches"] for c in output),
            "active_batches": sum(c["active_batches"] for c in output),
            "awaiting_approval": sum(c["awaiting_approval"] for c in output),
            "scheduled_jobs": sum(c["scheduled_jobs"] for c in output),
            "published_jobs": sum(c["published_jobs"] for c in output),
            "failed_jobs": sum(c["failed_jobs"] for c in output),
        },
        "limits": [
            "This is a portfolio view of locally stored records; it does not verify live platform state.",
            "Publishing adapters and platform permissions remain platform-specific.",
            "Human approval remains required before publication."
        ]
    }


def create_multi_channel_strategy_plans(channel_ids: list[str], start_date: str,
                                        days: int = 30, videos_per_day: int = 1) -> dict:
    if not 1 <= days <= 90 or not 1 <= videos_per_day <= 5:
        raise ValueError("days must be 1-90 and videos_per_day must be 1-5")
    requested_start = date.fromisoformat(start_date)
    if not channel_ids:
        raise ValueError("Select at least one channel")
    if len(channel_ids) > 25 or len(set(channel_ids)) != len(channel_ids):
        raise ValueError("Select between 1 and 25 unique channels")
    available = {c["id"]: c for c in database.channel_list()}
    unknown = [cid for cid in channel_ids if cid not in available]
    if unknown:
        raise ValueError("Unknown channel ID: " + ", ".join(unknown))

    results = []
    for channel_id in channel_ids:
        channel = available[channel_id]
        plans = [p for p in database.strategy_plan_list(limit=500) if p.get("channel_id") == channel_id]
        candidate_start = requested_start
        # Keep each channel's planning windows non-overlapping. Different channels
        # may run in parallel because they have separate audiences and destinations.
        for _ in range(len(plans) + 1):
            candidate_end = candidate_start + timedelta(days=days - 1)
            overlaps = []
            for plan in plans:
                plan_start = date.fromisoformat(plan["start_date"])
                plan_end = plan_start + timedelta(days=int(plan["days"]) - 1)
                if candidate_start <= plan_end and plan_start <= candidate_end:
                    overlaps.append(plan_end)
            if not overlaps:
                break
            candidate_start = max(overlaps) + timedelta(days=1)
        try:
            plan = create_brain_strategy(
                channel["target_market"], channel["niche"], channel["language"],
                channel_id, candidate_start.isoformat(), days, videos_per_day,
            )
            results.append({
                "channel_id": channel_id, "channel_name": channel["name"],
                "status": "created", "plan_id": plan["id"], "plan_name": plan["name"],
                "start_date": candidate_start.isoformat(), "item_count": len(plan["items"]),
            })
        except Exception as exc:
            results.append({
                "channel_id": channel_id, "channel_name": channel["name"],
                "status": "failed", "error": str(exc),
            })
    return {
        "requested_channels": len(channel_ids),
        "created": sum(1 for r in results if r["status"] == "created"),
        "failed": sum(1 for r in results if r["status"] == "failed"),
        "results": results,
        "note": "Plans are drafts. Review them before production. Publication still requires human approval."
    }
