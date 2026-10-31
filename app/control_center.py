from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.publishing_worker import worker_status
from app.publishing_engine import publishing_adapter_status
from app.renderer import ffmpeg_available
from app.voice_engine import piper_available
from app.youtube_adapter import youtube_connection_status


def _db_path() -> Path:
    return Path(os.getenv("CREATOROS_DB_PATH", "creatoros.db"))


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _count(conn: sqlite3.Connection, table: str, where: str = "", params: tuple = ()) -> int:
    # Table names are fixed internal constants at call sites, never request input.
    return int(conn.execute(f"SELECT COUNT(*) FROM {table} {where}", params).fetchone()[0])


def get_control_center() -> dict:
    path = _db_path()
    now = datetime.now(timezone.utc).isoformat()
    if not path.exists():
        return {
            "generated_at": now,
            "database": {"status": "not_initialized", "path": str(path)},
            "channels": {"total": 0, "by_platform": [], "items": []},
            "production": {"projects": 0, "renders": {}, "voice_jobs": {}, "batches": {}},
            "publishing": {"jobs": {}, "upcoming": [], "recent": []},
            "runtime": {"worker": worker_status(), "adapters": publishing_adapter_status(),
                        "ffmpeg_available": ffmpeg_available(), "piper_available": piper_available()},
        }

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        channel_items = _rows(conn, """
            SELECT c.id,c.name,c.platform,c.target_market,c.language,c.niche,c.created_at,
                   COUNT(DISTINCT p.id) AS project_count,
                   COUNT(DISTINCT CASE WHEN j.status='scheduled' THEN j.id END) AS scheduled_count,
                   COUNT(DISTINCT CASE WHEN j.status='published' THEN j.id END) AS published_count,
                   COUNT(DISTINCT CASE WHEN j.status='failed' THEN j.id END) AS failed_count
            FROM channels c
            LEFT JOIN projects p ON p.channel_id=c.id
            LEFT JOIN publish_jobs j ON j.channel_id=c.id
            GROUP BY c.id ORDER BY c.created_at DESC
        """)
        by_platform = _rows(conn, "SELECT platform,COUNT(*) AS count FROM channels GROUP BY platform ORDER BY platform")
        project_status = _rows(conn, "SELECT status,COUNT(*) AS count FROM projects GROUP BY status ORDER BY status")
        render_status = _rows(conn, "SELECT status,COUNT(*) AS count FROM render_jobs GROUP BY status ORDER BY status")
        voice_status = _rows(conn, "SELECT status,COUNT(*) AS count FROM voice_jobs GROUP BY status ORDER BY status")
        batch_status = _rows(conn, "SELECT status,COUNT(*) AS count FROM production_batches GROUP BY status ORDER BY status")
        publish_status = _rows(conn, "SELECT status,COUNT(*) AS count FROM publish_jobs GROUP BY status ORDER BY status")
        upcoming = _rows(conn, """
            SELECT j.id,j.title,j.status,j.scheduled_at,c.name AS channel_name,c.platform,
                   c.target_market,p.title AS project_title
            FROM publish_jobs j
            JOIN channels c ON c.id=j.channel_id
            LEFT JOIN projects p ON p.id=j.project_id
            WHERE j.status='scheduled' AND j.scheduled_at IS NOT NULL
            ORDER BY j.scheduled_at ASC LIMIT 12
        """)
        recent = _rows(conn, """
            SELECT j.id,j.title,j.status,j.updated_at,j.published_at,j.error,
                   c.name AS channel_name,c.platform
            FROM publish_jobs j JOIN channels c ON c.id=j.channel_id
            ORDER BY j.updated_at DESC LIMIT 12
        """)
        credentials = _rows(conn, "SELECT channel_id,provider,updated_at FROM platform_credentials")
        oauth_connected = {(item["channel_id"], item["provider"]): item["updated_at"] for item in credentials}
        for channel in channel_items:
            if channel["platform"] == "youtube":
                try:
                    connected = youtube_connection_status(channel["id"])["connected"]
                except (ValueError, RuntimeError):
                    connected = False
            else:
                connected = (channel["id"], channel["platform"]) in oauth_connected
            channel["connection"] = "connected" if connected else "not_connected"
            channel["credential_updated_at"] = oauth_connected.get((channel["id"], channel["platform"]))
        return {
            "generated_at": now,
            "database": {"status": "ready", "path": str(path)},
            "channels": {
                "total": len(channel_items),
                "by_platform": by_platform,
                "items": channel_items,
            },
            "production": {
                "projects": {"total": _count(conn, "projects"), "by_status": project_status},
                "renders": {"total": _count(conn, "render_jobs"), "by_status": render_status},
                "voice_jobs": {"total": _count(conn, "voice_jobs"), "by_status": voice_status},
                "batches": {"total": _count(conn, "production_batches"), "by_status": batch_status},
            },
            "publishing": {
                "total": _count(conn, "publish_jobs"),
                "by_status": publish_status,
                "upcoming": upcoming,
                "recent": recent,
            },
            "runtime": {
                "worker": worker_status(),
                "adapters": publishing_adapter_status(),
                "ffmpeg_available": ffmpeg_available(),
                "piper_available": piper_available(),
            },
        }
    finally:
        conn.close()
