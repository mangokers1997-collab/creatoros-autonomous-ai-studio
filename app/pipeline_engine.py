from __future__ import annotations

from app.database import (
    production_batch_get, production_batch_item_get, production_batch_item_update,
    production_batch_refresh, strategy_plan_get, strategy_item_update,
    project_create, project_update_status, content_package_list,
    voice_job_create, voice_job_get, render_job_create, render_scene_assets_replace,
)
from app.content_engine import generate_content_package
from app.voice_engine import piper_available, run_voice_job
from app.renderer import ffmpeg_available, run_render_job


def run_production_batch(batch_id: str) -> None:
    batch = production_batch_get(batch_id)
    if not batch:
        return
    plan = strategy_plan_get(batch["strategy_id"])
    if not plan:
        return
    options = batch.get("options", {})
    for batch_item in batch["items"]:
        if batch_item["status"] in {"completed", "failed"}:
            continue
        current = production_batch_item_update(
            batch_item["id"], "processing",
            attempts=int(batch_item.get("attempts", 0)) + 1, error=""
        )
        production_batch_refresh(batch_id)
        try:
            source = next((row for row in plan["items"] if row["id"] == current["strategy_item_id"]), None)
            if not source:
                raise RuntimeError("Strategy calendar item was not found.")
            project = None
            if current.get("project_id"):
                from app.database import project_get
                project = project_get(current["project_id"])
            if not project:
                project = project_create({
                    "title": source["title"], "niche": plan["niche"],
                    "target_market": plan["market"], "language": plan["language"],
                    "format": source.get("format", "short"), "channel_id": plan.get("channel_id"),
                    "brief": f"Angle: {source['angle']}\nOpening hook: {source['hook']}\nPlanned date: {source['planned_date']}\nSlot: {source['slot']}. Review facts and add sourced examples before publishing.",
                })
                strategy_item_update(source["id"], "in_progress", project["id"])
                current = production_batch_item_update(current["id"], "processing", project_id=project["id"])
            packages = content_package_list(project["id"])
            package = next((row for row in packages if row["id"] == current.get("package_id")), None)
            if not package:
                package = generate_content_package(project["id"])
                if not package:
                    raise RuntimeError("Content package generation failed.")
                current = production_batch_item_update(current["id"], "processing", package_id=package["id"])
            if options.get("generate_voice") and piper_available():
                voice = voice_job_get(current.get("voice_job_id")) if current.get("voice_job_id") else None
                if not voice:
                    voice = voice_job_create({"project_id": project["id"], "package_id": package["id"]})
                    current = production_batch_item_update(current["id"], "processing", voice_job_id=voice["id"])
                    run_voice_job(voice["id"])
                    voice = voice_job_get(voice["id"])
                if voice and voice["status"] != "ready":
                    raise RuntimeError(voice.get("error") or "Local voice generation failed.")
            if options.get("render_video"):
                if not ffmpeg_available():
                    raise RuntimeError("FFmpeg is not installed; install it to enable video rendering.")
                from app.database import media_asset_get
                audio_id = voice["audio_asset_id"] if options.get("generate_voice") and piper_available() and voice else None
                render = None
                if current.get("render_job_id"):
                    from app.database import render_job_get
                    render = render_job_get(current["render_job_id"])
                if not render:
                    render = render_job_create({
                        "project_id": project["id"], "package_id": package["id"],
                        "image_asset_id": None, "audio_asset_id": audio_id,
                        "duration_seconds": int(options.get("duration_seconds", 48)),
                    })
                    storyboard = package.get("storyboard_json", [])
                    render_scene_assets_replace(render["id"], [{
                        "image_asset_id": None,
                        "caption": scene.get("narration") or scene.get("on_screen_text") or "",
                        "visual_direction": scene.get("visual_direction") or "",
                    } for scene in storyboard[:12]])
                    current = production_batch_item_update(current["id"], "processing", render_job_id=render["id"])
                    run_render_job(render["id"])
                    from app.database import render_job_get
                    render = render_job_get(render["id"])
                if not render or render["status"] != "rendered":
                    raise RuntimeError((render or {}).get("error") or "Video rendering failed.")
                project_update_status(project["id"], "rendered")
            else:
                project_update_status(project["id"], "ready_for_review")
            production_batch_item_update(current["id"], "completed", error="")
            strategy_item_update(source["id"], "ready_for_review", project["id"])
        except Exception as exc:
            production_batch_item_update(current["id"], "failed", error=str(exc)[:1800])
            if current.get("project_id"):
                project_update_status(current["project_id"], "failed")
            strategy_item_update(batch_item["strategy_item_id"], "ready_for_review", current.get("project_id"))
        production_batch_refresh(batch_id)


def retry_production_batch_item(item_id: str) -> dict | None:
    item = production_batch_item_get(item_id)
    if not item or item["status"] != "failed":
        return None
    production_batch_item_update(item_id, "queued", error="")
    production_batch_refresh(item["batch_id"])
    return production_batch_get(item["batch_id"])
