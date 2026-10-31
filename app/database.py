import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

DB_PATH = Path(os.getenv("CREATOROS_DB_PATH", "creatoros.db"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS channels (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            platform TEXT NOT NULL,
            target_market TEXT NOT NULL,
            language TEXT NOT NULL,
            niche TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            niche TEXT NOT NULL,
            target_market TEXT NOT NULL,
            language TEXT NOT NULL,
            format TEXT NOT NULL,
            channel_id TEXT,
            brief TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'idea',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(channel_id) REFERENCES channels(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
        CREATE INDEX IF NOT EXISTS idx_projects_channel ON projects(channel_id);
        CREATE TABLE IF NOT EXISTS research_briefs (
            id TEXT PRIMARY KEY,
            topic TEXT NOT NULL,
            niche TEXT NOT NULL,
            target_market TEXT NOT NULL,
            language TEXT NOT NULL,
            audience TEXT NOT NULL DEFAULT '',
            goal TEXT NOT NULL DEFAULT '',
            keywords TEXT NOT NULL DEFAULT '',
            competitors TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS research_sources (
            id TEXT PRIMARY KEY,
            brief_id TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL DEFAULT '',
            source_type TEXT NOT NULL DEFAULT 'article',
            observation TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(brief_id) REFERENCES research_briefs(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_research_market ON research_briefs(target_market);
        """)


def _dict(row):
    return dict(row) if row else None


def channel_create(data: dict) -> dict:
    item = {"id": str(uuid4()), **data, "created_at": _now()}
    with _connect() as conn:
        conn.execute(
            """INSERT INTO channels
            (id,name,platform,target_market,language,niche,created_at)
            VALUES (:id,:name,:platform,:target_market,:language,:niche,:created_at)""",
            item,
        )
    return item


def channel_list() -> list[dict]:
    with _connect() as conn:
        return [dict(row) for row in conn.execute(
            "SELECT * FROM channels ORDER BY created_at DESC"
        ).fetchall()]


def channel_get(channel_id: str) -> dict | None:
    with _connect() as conn:
        return _dict(conn.execute(
            "SELECT * FROM channels WHERE id=?", (channel_id,)
        ).fetchone())


def channel_delete(channel_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM channels WHERE id=?", (channel_id,))
        return cur.rowcount > 0


def project_create(data: dict) -> dict:
    now = _now()
    item = {
        "id": str(uuid4()), **data, "status": "idea",
        "created_at": now, "updated_at": now,
    }
    with _connect() as conn:
        conn.execute(
            """INSERT INTO projects
            (id,title,niche,target_market,language,format,channel_id,brief,status,created_at,updated_at)
            VALUES (:id,:title,:niche,:target_market,:language,:format,:channel_id,:brief,:status,:created_at,:updated_at)""",
            item,
        )
    return item


def project_list(status: str | None = None, channel_id: str | None = None, limit: int = 50) -> list[dict]:
    clauses, params = [], []
    if status:
        clauses.append("status=?")
        params.append(status)
    if channel_id:
        clauses.append("channel_id=?")
        params.append(channel_id)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM projects{where} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(row) for row in rows]


def project_get(project_id: str) -> dict | None:
    with _connect() as conn:
        return _dict(conn.execute(
            "SELECT * FROM projects WHERE id=?", (project_id,)
        ).fetchone())


def project_update_status(project_id: str, status: str) -> dict | None:
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE projects SET status=?, updated_at=? WHERE id=?",
            (status, _now(), project_id),
        )
        if not cur.rowcount:
            return None
        return _dict(conn.execute(
            "SELECT * FROM projects WHERE id=?", (project_id,)
        ).fetchone())


def research_create(data: dict) -> dict:
    item = {"id": str(uuid4()), **data, "created_at": _now()}
    with _connect() as conn:
        conn.execute(
            """INSERT INTO research_briefs
            (id,topic,niche,target_market,language,audience,goal,keywords,competitors,notes,created_at)
            VALUES (:id,:topic,:niche,:target_market,:language,:audience,:goal,:keywords,:competitors,:notes,:created_at)""",
            item,
        )
    return {**item, "sources": []}


def research_list(target_market: str | None = None, niche: str | None = None, limit: int = 50) -> list[dict]:
    clauses, params = [], []
    if target_market:
        clauses.append("target_market=?")
        params.append(target_market)
    if niche:
        clauses.append("niche=?")
        params.append(niche)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM research_briefs{where} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(row) for row in rows]


def research_get(brief_id: str) -> dict | None:
    with _connect() as conn:
        row = _dict(conn.execute(
            "SELECT * FROM research_briefs WHERE id=?", (brief_id,)
        ).fetchone())
        if not row:
            return None
        row["sources"] = [dict(source) for source in conn.execute(
            "SELECT * FROM research_sources WHERE brief_id=? ORDER BY created_at DESC",
            (brief_id,),
        ).fetchall()]
        return row


def research_source_create(brief_id: str, data: dict) -> dict | None:
    if not research_get(brief_id):
        return None
    item = {"id": str(uuid4()), "brief_id": brief_id, **data, "created_at": _now()}
    with _connect() as conn:
        conn.execute(
            """INSERT INTO research_sources
            (id,brief_id,title,url,source_type,observation,created_at)
            VALUES (:id,:brief_id,:title,:url,:source_type,:observation,:created_at)""",
            item,
        )
    return item
