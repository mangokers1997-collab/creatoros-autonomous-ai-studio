"""Persistent SQLite-backed worker for production orchestrations."""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app import database
from app.production_orchestrator import run_production_orchestration
from app.resource_scheduler import resource_snapshot

log = logging.getLogger("creatoros.production_worker")
_stop = threading.Event()
_thread: threading.Thread | None = None
_worker_id = str(uuid4())
_active_id: str | None = None
_active_lock = threading.Lock()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def worker_status() -> dict:
    enabled = os.getenv("CREATOROS_PRODUCTION_WORKER_ENABLED", "true").lower() in {"1", "true", "yes"}
    with _active_lock:
        active = _active_id
    return {
        "enabled": enabled,
        "running": _thread is not None and _thread.is_alive(),
        "worker_id": _worker_id,
        "active_orchestration_id": active,
        "poll_seconds": max(2, min(60, int(os.getenv("CREATOROS_PRODUCTION_POLL_SECONDS", "5")))),
        "lease_seconds": max(30, min(600, int(os.getenv("CREATOROS_PRODUCTION_LEASE_SECONDS", "120")))),
        "queue": database.production_worker_snapshot(),
        "resources": resource_snapshot(),
    }


def _lease_heartbeat(orchestration_id: str, finished: threading.Event) -> None:
    interval = max(5, min(60, int(os.getenv("CREATOROS_PRODUCTION_HEARTBEAT_SECONDS", "20"))))
    lease_seconds = max(30, min(600, int(os.getenv("CREATOROS_PRODUCTION_LEASE_SECONDS", "120"))))
    while not finished.wait(interval):
        lease_until = (_utcnow() + timedelta(seconds=lease_seconds)).isoformat()
        try:
            if not database.production_orchestration_heartbeat(orchestration_id, _worker_id, lease_until):
                log.warning("Lost production orchestration lease %s.", orchestration_id)
                return
        except Exception:
            log.exception("Could not renew production orchestration lease %s.", orchestration_id)


def _run_once() -> bool:
    now = _utcnow()
    lease_seconds = max(30, min(600, int(os.getenv("CREATOROS_PRODUCTION_LEASE_SECONDS", "120"))))
    orchestration = database.production_orchestration_claim_next(
        _worker_id,
        (now + timedelta(seconds=lease_seconds)).isoformat(),
        now.isoformat(),
        max_attempts=3,
    )
    if not orchestration:
        return False
    orchestration_id = orchestration["id"]
    with _active_lock:
        global _active_id
        _active_id = orchestration_id
    heartbeat_done = threading.Event()
    heartbeat = threading.Thread(
        target=_lease_heartbeat, args=(orchestration_id, heartbeat_done),
        name="creatoros-production-heartbeat", daemon=True,
    )
    heartbeat.start()
    error = ""
    try:
        run_production_orchestration(orchestration_id)
    except Exception as exc:
        error = f"{type(exc).__name__}: {str(exc)[:1600]}"
        log.exception("Production orchestration %s failed.", orchestration_id)
    finally:
        heartbeat_done.set()
        heartbeat.join(timeout=2)
        database.production_orchestration_finish(orchestration_id, _worker_id, error)
        with _active_lock:
            _active_id = None
    return True


def _loop() -> None:
    poll = max(2, min(60, int(os.getenv("CREATOROS_PRODUCTION_POLL_SECONDS", "5"))))
    while not _stop.is_set():
        try:
            resources = resource_snapshot()
            if not resources["can_start_job"]:
                log.info("Production worker paused by resource guard: %s", resources["blocked_reasons"])
                _stop.wait(max(poll, 15))
                continue
            worked = _run_once()
        except Exception:
            log.exception("Production worker iteration failed.")
            worked = False
        if not worked:
            _stop.wait(poll)


def start_worker() -> None:
    global _thread
    if os.getenv("CREATOROS_PRODUCTION_WORKER_ENABLED", "true").lower() not in {"1", "true", "yes"}:
        log.info("Production worker disabled by CREATOROS_PRODUCTION_WORKER_ENABLED.")
        return
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="creatoros-production-worker", daemon=True)
    _thread.start()
    log.info("CreatorOS persistent production worker started.")


def stop_worker() -> None:
    _stop.set()
    if _thread is not None and _thread.is_alive():
        _thread.join(timeout=10)
