from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

from app.database import publish_job_claim_due, publish_job_requeue_stale, publish_job_update
from app.publishing_engine import publishing_adapter_status
from app.youtube_adapter import upload_youtube_video

log = logging.getLogger("creatoros.publisher")
_stop = threading.Event()
_thread: threading.Thread | None = None


def worker_status() -> dict:
    enabled = os.getenv("CREATOROS_PUBLISH_WORKER_ENABLED", "false").lower() in {"1", "true", "yes"}
    adapters = publishing_adapter_status()
    return {
        "enabled": enabled,
        "running": _thread is not None and _thread.is_alive(),
        "poll_seconds": int(os.getenv("CREATOROS_PUBLISH_POLL_SECONDS", "15")),
        "youtube_configured": adapters["youtube"]["configured"],
        "mode": "youtube_private_only",
    }


def _run_once() -> bool:
    now = datetime.now(timezone.utc)
    # Recover abandoned leases, but never blindly resubmit: an interrupted upload
    # might have reached YouTube even if CreatorOS did not receive its response.
    publish_job_requeue_stale(
        (now - timedelta(minutes=30)).isoformat(), now.isoformat()
    )
    job = publish_job_claim_due(now.isoformat())
    if not job:
        return False
    try:
        upload_youtube_video(job["id"], privacy_status="private")
        log.info("Scheduled YouTube job %s uploaded successfully.", job["id"])
    except Exception as exc:
        publish_job_update(
            job["id"], "failed",
            error=f"{type(exc).__name__}: {str(exc)[:700]}",
        )
        log.exception("Scheduled YouTube upload failed for job %s.", job["id"])
    return True


def _loop() -> None:
    poll = max(5, min(300, int(os.getenv("CREATOROS_PUBLISH_POLL_SECONDS", "15"))))
    while not _stop.is_set():
        try:
            did_work = _run_once()
        except Exception:
            log.exception("Publishing worker iteration failed.")
            did_work = False
        if not did_work:
            _stop.wait(poll)


def start_worker() -> None:
    global _thread
    if os.getenv("CREATOROS_PUBLISH_WORKER_ENABLED", "false").lower() not in {"1", "true", "yes"}:
        log.info("Publishing worker disabled; set CREATOROS_PUBLISH_WORKER_ENABLED=true to enable.")
        return
    if not publishing_adapter_status()["youtube"]["configured"]:
        log.warning("Publishing worker not started: YouTube OAuth environment is incomplete.")
        return
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="creatoros-publisher", daemon=True)
    _thread.start()
    log.info("CreatorOS publishing worker started.")


def stop_worker() -> None:
    _stop.set()
    if _thread is not None and _thread.is_alive():
        _thread.join(timeout=5)
