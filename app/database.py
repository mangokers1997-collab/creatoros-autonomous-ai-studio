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
        CREATE TABLE IF NOT EXISTS content_packages (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            title TEXT NOT NULL,
            hook TEXT NOT NULL,
            description TEXT NOT NULL,
            script TEXT NOT NULL,
            storyboard_json TEXT NOT NULL,
            subtitles_srt TEXT NOT NULL,
            hashtags TEXT NOT NULL,
            language TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_packages_project ON content_packages(project_id);
        CREATE TABLE IF NOT EXISTS media_assets (
            id TEXT PRIMARY KEY,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL,
            media_type TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS render_jobs (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            package_id TEXT NOT NULL,
            image_asset_id TEXT,
            audio_asset_id TEXT,
            status TEXT NOT NULL,
            output_path TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            duration_seconds INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY(package_id) REFERENCES content_packages(id) ON DELETE CASCADE,
            FOREIGN KEY(image_asset_id) REFERENCES media_assets(id),
            FOREIGN KEY(audio_asset_id) REFERENCES media_assets(id)
        );
        CREATE INDEX IF NOT EXISTS idx_render_status ON render_jobs(status);
        CREATE TABLE IF NOT EXISTS render_scene_assets (
            id TEXT PRIMARY KEY,
            render_job_id TEXT NOT NULL,
            scene_index INTEGER NOT NULL,
            image_asset_id TEXT,
            caption TEXT NOT NULL DEFAULT '',
            visual_direction TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(render_job_id) REFERENCES render_jobs(id) ON DELETE CASCADE,
            FOREIGN KEY(image_asset_id) REFERENCES media_assets(id),
            UNIQUE(render_job_id, scene_index)
        );
        CREATE TABLE IF NOT EXISTS voice_jobs (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            package_id TEXT NOT NULL,
            status TEXT NOT NULL,
            audio_asset_id TEXT,
            subtitles_srt TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY(package_id) REFERENCES content_packages(id) ON DELETE CASCADE,
            FOREIGN KEY(audio_asset_id) REFERENCES media_assets(id)
        );
        CREATE INDEX IF NOT EXISTS idx_voice_jobs_status ON voice_jobs(status);
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


import json


def content_package_create(project_id: str, data: dict) -> dict | None:
    project = project_get(project_id)
    if not project:
        return None
    item = {
        "id": str(uuid4()),
        "project_id": project_id,
        **data,
        "storyboard_json": json.dumps(data["storyboard"], ensure_ascii=False),
        "hashtags": json.dumps(data["hashtags"], ensure_ascii=False),
        "generated_at": _now(),
    }
    with _connect() as conn:
        conn.execute(
            """INSERT INTO content_packages
            (id,project_id,title,hook,description,script,storyboard_json,subtitles_srt,hashtags,language,generated_at)
            VALUES (:id,:project_id,:title,:hook,:description,:script,:storyboard_json,:subtitles_srt,:hashtags,:language,:generated_at)""",
            item,
        )
    item["storyboard_json"] = data["storyboard"]
    item["hashtags"] = data["hashtags"]
    return item


def content_package_list(project_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM content_packages WHERE project_id=? ORDER BY generated_at DESC",
            (project_id,),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["storyboard_json"] = json.loads(item["storyboard_json"])
        item["hashtags"] = json.loads(item["hashtags"])
        result.append(item)
    return result


def media_asset_create(data: dict) -> dict:
    item = {"id": str(uuid4()), **data, "created_at": _now()}
    with _connect() as conn:
        conn.execute(
            """INSERT INTO media_assets
            (id,original_name,stored_name,media_type,mime_type,size_bytes,created_at)
            VALUES (:id,:original_name,:stored_name,:media_type,:mime_type,:size_bytes,:created_at)""",
            item,
        )
    return item


def media_asset_get(asset_id: str) -> dict | None:
    with _connect() as conn:
        return _dict(conn.execute(
            "SELECT * FROM media_assets WHERE id=?", (asset_id,)
        ).fetchone())


def media_asset_list(limit: int = 100) -> list[dict]:
    with _connect() as conn:
        return [dict(row) for row in conn.execute(
            "SELECT * FROM media_assets ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()]


def render_job_create(data: dict) -> dict:
    now = _now()
    item = {
        "id": str(uuid4()), **data, "status": "queued",
        "output_path": "", "error": "", "created_at": now, "updated_at": now,
    }
    with _connect() as conn:
        conn.execute(
            """INSERT INTO render_jobs
            (id,project_id,package_id,image_asset_id,audio_asset_id,status,output_path,error,duration_seconds,created_at,updated_at)
            VALUES (:id,:project_id,:package_id,:image_asset_id,:audio_asset_id,:status,:output_path,:error,:duration_seconds,:created_at,:updated_at)""",
            item,
        )
    return item


def render_job_update(job_id: str, status: str, output_path: str = "", error: str = "") -> dict | None:
    with _connect() as conn:
        cur = conn.execute(
            """UPDATE render_jobs SET status=?,output_path=?,error=?,updated_at=? WHERE id=?""",
            (status, output_path, error[:2000], _now(), job_id),
        )
        if not cur.rowcount:
            return None
        return _dict(conn.execute("SELECT * FROM render_jobs WHERE id=?", (job_id,)).fetchone())


def render_job_get(job_id: str) -> dict | None:
    with _connect() as conn:
        return _dict(conn.execute(
            "SELECT * FROM render_jobs WHERE id=?", (job_id,)
        ).fetchone())


def render_job_list(project_id: str | None = None, limit: int = 50) -> list[dict]:
    with _connect() as conn:
        if project_id:
            rows = conn.execute(
                "SELECT * FROM render_jobs WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM render_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]


def voice_job_create(data: dict) -> dict:
    now = _now()
    item = {"id": str(uuid4()), **data, "status": "queued", "audio_asset_id": None,
            "subtitles_srt": "", "error": "", "created_at": now, "updated_at": now}
    with _connect() as conn:
        conn.execute(
            """INSERT INTO voice_jobs
            (id,project_id,package_id,status,audio_asset_id,subtitles_srt,error,created_at,updated_at)
            VALUES (:id,:project_id,:package_id,:status,:audio_asset_id,:subtitles_srt,:error,:created_at,:updated_at)""",
            item,
        )
    return item


def voice_job_update(job_id: str, status: str, audio_asset_id: str | None = None,
                     subtitles_srt: str = "", error: str = "") -> dict | None:
    with _connect() as conn:
        cur = conn.execute(
            """UPDATE voice_jobs SET status=?,audio_asset_id=?,subtitles_srt=?,error=?,updated_at=? WHERE id=?""",
            (status, audio_asset_id, subtitles_srt, error[:2000], _now(), job_id),
        )
        if not cur.rowcount:
            return None
        return _dict(conn.execute("SELECT * FROM voice_jobs WHERE id=?", (job_id,)).fetchone())


def voice_job_get(job_id: str) -> dict | None:
    with _connect() as conn:
        return _dict(conn.execute("SELECT * FROM voice_jobs WHERE id=?", (job_id,)).fetchone())


def voice_job_list(project_id: str | None = None, limit: int = 50) -> list[dict]:
    with _connect() as conn:
        if project_id:
            rows = conn.execute("SELECT * FROM voice_jobs WHERE project_id=? ORDER BY created_at DESC LIMIT ?", (project_id, limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM voice_jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]


def render_scene_assets_replace(job_id: str, scenes: list[dict]) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM render_scene_assets WHERE render_job_id=?", (job_id,))
        for index, scene in enumerate(scenes):
            conn.execute(
                """INSERT INTO render_scene_assets
                (id,render_job_id,scene_index,image_asset_id,caption,visual_direction,created_at)
                VALUES (?,?,?,?,?,?,?)""",
                (str(uuid4()), job_id, index, scene.get("image_asset_id"),
                 scene.get("caption", ""), scene.get("visual_direction", ""), _now()),
            )


def render_scene_assets_list(job_id: str) -> list[dict]:
    with _connect() as conn:
        return [dict(row) for row in conn.execute(
            "SELECT * FROM render_scene_assets WHERE render_job_id=? ORDER BY scene_index",
            (job_id,),
        ).fetchall()]
