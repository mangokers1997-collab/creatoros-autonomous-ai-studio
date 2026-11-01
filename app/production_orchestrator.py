"""Sequential, capacity-limited orchestration across channel production batches."""
from __future__ import annotations

from app import database
from app.pipeline_engine import run_production_batch


def create_production_orchestration(strategy_ids: list[str], max_items: int,
                                    generate_voice: bool, render_video: bool,
                                    duration_seconds: int) -> dict:
    if not strategy_ids or len(strategy_ids) > 25 or len(set(strategy_ids)) != len(strategy_ids):
        raise ValueError("Select 1-25 unique strategy plans.")
    if not 1 <= max_items <= 5:
        raise ValueError("max_items must be between 1 and 5.")
    if not 8 <= duration_seconds <= 180:
        raise ValueError("duration_seconds must be between 8 and 180.")
    records = []
    channels_seen = set()
    for strategy_id in strategy_ids:
        plan = database.strategy_plan_get(strategy_id)
        if not plan:
            raise ValueError(f"Strategy plan not found: {strategy_id}")
        channel_id = plan.get("channel_id")
        if not channel_id:
            raise ValueError(f"Strategy '{plan['name']}' is not assigned to a channel.")
        if channel_id in channels_seen:
            raise ValueError("Select only one strategy per channel in each orchestration.")
        channels_seen.add(channel_id)
        if not any(item.get("status") in {"planned", "in_progress"} for item in plan["items"]):
            raise ValueError(f"No eligible planned items in strategy '{plan['name']}'.")
        records.append({"strategy_id": strategy_id, "channel_id": channel_id})
    return database.production_orchestration_create(records, {
        "max_items": max_items, "generate_voice": generate_voice,
        "render_video": render_video, "duration_seconds": duration_seconds,
        "execution_mode": "sequential_single_worker",
    })


def run_production_orchestration(orchestration_id: str) -> None:
    orchestration = database.production_orchestration_get(orchestration_id)
    if not orchestration:
        return
    options = orchestration.get("options", {})
    for item in orchestration["items"]:
        if item["status"] in {"completed", "failed"}:
            continue
        database.production_orchestration_item_update(item["id"], "processing", error="")
        database.production_orchestration_refresh(orchestration_id)
        try:
            plan = database.strategy_plan_get(item["strategy_id"])
            if not plan:
                raise RuntimeError("Strategy plan no longer exists.")
            eligible = [row for row in plan["items"] if row["status"] in {"planned", "in_progress"}]
            eligible = eligible[:int(options.get("max_items", 5))]
            if not eligible:
                raise RuntimeError("No planned strategy items remain.")
            batch = database.production_batch_get(item.get("batch_id")) if item.get("batch_id") else None
            if not batch:
                batch = database.production_batch_create(item["strategy_id"], eligible, {
                    "generate_voice": bool(options.get("generate_voice", True)),
                    "render_video": bool(options.get("render_video", True)),
                    "duration_seconds": int(options.get("duration_seconds", 48)),
                })
                database.production_orchestration_item_update(item["id"], "processing", batch_id=batch["id"])
            database.production_orchestration_refresh(orchestration_id)
            run_production_batch(batch["id"])
            final_batch = database.production_batch_refresh(batch["id"])
            if not final_batch:
                raise RuntimeError("Production batch disappeared.")
            if final_batch["status"] == "completed":
                database.production_orchestration_item_update(item["id"], "completed", batch_id=batch["id"], error="")
            else:
                raise RuntimeError(
                    f"Batch {final_batch['status']}: {final_batch['completed_items']} completed, "
                    f"{final_batch['failed_items']} failed. Review batch errors before retrying."
                )
        except Exception as exc:
            database.production_orchestration_item_update(item["id"], "failed", error=str(exc)[:1800])
        database.production_orchestration_refresh(orchestration_id)
    database.production_orchestration_refresh(orchestration_id)


def get_production_orchestrations(limit: int = 30) -> list[dict]:
    return database.production_orchestration_list(limit=max(1, min(limit, 100)))
