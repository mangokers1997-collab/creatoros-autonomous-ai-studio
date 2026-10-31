from __future__ import annotations

from datetime import datetime, timezone
import os

from app.database import (
    channel_get, project_get, render_job_get,
    publish_job_create, publish_job_get, publish_job_list, publish_job_update,
    publish_job_retry,
)


def create_publish_draft(channel_id: str, project_id: str, render_job_id: str,
                         title: str, caption: str) -> dict:
    channel = channel_get(channel_id)
    if not channel:
        raise ValueError("Channel not found.")
    project = project_get(project_id)
    if not project:
        raise ValueError("Project not found.")
    if project.get("channel_id") != channel_id:
        raise ValueError("Project must belong to the selected channel.")
    if project.get("status") not in {"approved", "rendered"}:
        raise ValueError("Project must be approved or rendered before it can enter the publishing queue.")
    render = render_job_get(render_job_id)
    if not render or render.get("project_id") != project_id or render.get("status") != "rendered":
        raise ValueError("A completed render belonging to this project is required.")
    return publish_job_create({
        "channel_id": channel_id, "project_id": project_id,
        "render_job_id": render_job_id, "title": title.strip(),
        "caption": caption.strip(),
    })


def approve_publish_job(job_id: str, scheduled_at: str) -> dict | None:
    job = publish_job_get(job_id)
    if not job or job["status"] != "awaiting_approval":
        return None
    try:
        parsed = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("scheduled_at must be ISO 8601 with a timezone, e.g. 2026-11-01T10:00:00+07:00.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("scheduled_at must include a timezone offset.")
    if parsed <= datetime.now(timezone.utc):
        raise ValueError("scheduled_at must be in the future.")
    return publish_job_update(job_id, "scheduled", scheduled_at=parsed.astimezone(timezone.utc).isoformat(),
                              approved_at=datetime.now(timezone.utc).isoformat())


def cancel_publish_job(job_id: str) -> dict | None:
    job = publish_job_get(job_id)
    if not job or job["status"] not in {"awaiting_approval", "scheduled"}:
        return None
    return publish_job_update(job_id, "cancelled", error="Cancelled by user.")


def list_publish_jobs(channel_id: str | None = None, status: str | None = None, limit: int = 50) -> list[dict]:
    return publish_job_list(channel_id=channel_id, status=status, limit=limit)


def get_publish_job(job_id: str) -> dict | None:
    return publish_job_get(job_id)


def publishing_adapter_status() -> dict:
    return {
        "youtube": {
            "implemented": True,
            "configured": all(os.getenv(key, "").strip() for key in (
                "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REDIRECT_URI",
                "CREATOROS_FERNET_KEY", "CREATOROS_OAUTH_STATE_SECRET",
            )),
            "mode": "manual_upload_private_by_default",
            "reason": "OAuth adapter is implemented; configure Google OAuth and connect each channel before uploading.",
        },
        "instagram": {"implemented": False, "reason": "Meta app review, permissions, and account connection are not configured."},
        "facebook": {"implemented": False, "reason": "Meta app review, permissions, and account connection are not configured."},
        "tiktok": {"implemented": False, "reason": "TikTok Content Posting API approval and creator authorization are not configured."},
    }


def retry_publish_job(job_id: str, scheduled_at: str) -> dict | None:
    try:
        parsed = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("scheduled_at must be ISO 8601 with a timezone.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("scheduled_at must include a timezone offset.")
    if parsed <= datetime.now(timezone.utc):
        raise ValueError("Retry time must be in the future.")
    return publish_job_retry(job_id, parsed.astimezone(timezone.utc).isoformat())
