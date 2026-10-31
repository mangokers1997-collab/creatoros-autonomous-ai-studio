import json
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
        CREATE TABLE IF NOT EXISTS trend_items (
            id TEXT PRIMARY KEY,
            market TEXT NOT NULL,
            title TEXT NOT NULL,
            source TEXT NOT NULL,
            source_url TEXT NOT NULL DEFAULT '',
            traffic_label TEXT NOT NULL DEFAULT '',
            published_at TEXT NOT NULL DEFAULT '',
            niche TEXT NOT NULL DEFAULT '',
            relevance_score REAL NOT NULL DEFAULT 0,
            collected_at TEXT NOT NULL,
            UNIQUE(market, title, source)
        );
        CREATE INDEX IF NOT EXISTS idx_trends_market_score ON trend_items(market, relevance_score DESC);
        CREATE TABLE IF NOT EXISTS intelligence_reports (
            id TEXT PRIMARY KEY,
            market TEXT NOT NULL,
            niche TEXT NOT NULL,
            language TEXT NOT NULL,
            report_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_intelligence_market ON intelligence_reports(market, niche, created_at);
        CREATE TABLE IF NOT EXISTS strategy_plans (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            market TEXT NOT NULL,
            niche TEXT NOT NULL,
            language TEXT NOT NULL,
            channel_id TEXT,
            start_date TEXT NOT NULL,
            days INTEGER NOT NULL,
            videos_per_day INTEGER NOT NULL,
            plan_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(channel_id) REFERENCES channels(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_strategy_market ON strategy_plans(market,niche,created_at);
        CREATE TABLE IF NOT EXISTS strategy_items (
            id TEXT PRIMARY KEY,
            plan_id TEXT NOT NULL,
            day_number INTEGER NOT NULL,
            planned_date TEXT NOT NULL,
            slot INTEGER NOT NULL,
            topic TEXT NOT NULL,
            angle TEXT NOT NULL,
            title TEXT NOT NULL,
            hook TEXT NOT NULL,
            format TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'planned',
            project_id TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(plan_id) REFERENCES strategy_plans(id) ON DELETE CASCADE,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL,
            UNIQUE(plan_id,day_number,slot)
        );
        CREATE INDEX IF NOT EXISTS idx_strategy_items_plan ON strategy_items(plan_id,day_number,slot);
        CREATE TABLE IF NOT EXISTS production_batches (
            id TEXT PRIMARY KEY,
            strategy_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            total_items INTEGER NOT NULL DEFAULT 0,
            completed_items INTEGER NOT NULL DEFAULT 0,
            failed_items INTEGER NOT NULL DEFAULT 0,
            options_json TEXT NOT NULL DEFAULT '{}',
            error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(strategy_id) REFERENCES strategy_plans(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_batches_status ON production_batches(status,created_at);
        CREATE TABLE IF NOT EXISTS production_batch_items (
            id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL,
            strategy_item_id TEXT NOT NULL,
            project_id TEXT,
            package_id TEXT,
            voice_job_id TEXT,
            render_job_id TEXT,
            status TEXT NOT NULL DEFAULT 'queued',
            attempts INTEGER NOT NULL DEFAULT 0,
            error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(batch_id) REFERENCES production_batches(id) ON DELETE CASCADE,
            FOREIGN KEY(strategy_item_id) REFERENCES strategy_items(id) ON DELETE CASCADE,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_batch_items_batch ON production_batch_items(batch_id,status);
        CREATE TABLE IF NOT EXISTS publish_jobs (
            id TEXT PRIMARY KEY,
            channel_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            render_job_id TEXT NOT NULL,
            title TEXT NOT NULL,
            caption TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'awaiting_approval',
            scheduled_at TEXT,
            approved_at TEXT,
            published_at TEXT,
            platform_post_id TEXT,
            error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(channel_id) REFERENCES channels(id) ON DELETE CASCADE,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY(render_job_id) REFERENCES render_jobs(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_publish_schedule ON publish_jobs(status,scheduled_at);
        CREATE INDEX IF NOT EXISTS idx_publish_channel ON publish_jobs(channel_id,created_at);
        CREATE TABLE IF NOT EXISTS oauth_states (
            state TEXT PRIMARY KEY,
            channel_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(channel_id) REFERENCES channels(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS platform_credentials (
            channel_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            encrypted_credentials TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(channel_id,provider),
            FOREIGN KEY(channel_id) REFERENCES channels(id) ON DELETE CASCADE
        );
        """)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(publish_jobs)").fetchall()}
        if "attempts" not in columns:
            conn.execute("ALTER TABLE publish_jobs ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0")



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


def trend_items_upsert(items: list[dict]) -> int:
    if not items:
        return 0
    with _connect() as conn:
        for item in items:
            conn.execute(
                """INSERT INTO trend_items
                (id,market,title,source,source_url,traffic_label,published_at,niche,relevance_score,collected_at)
                VALUES (:id,:market,:title,:source,:source_url,:traffic_label,:published_at,:niche,:relevance_score,:collected_at)
                ON CONFLICT(market,title,source) DO UPDATE SET
                source_url=excluded.source_url, traffic_label=excluded.traffic_label,
                published_at=excluded.published_at, niche=excluded.niche,
                relevance_score=excluded.relevance_score, collected_at=excluded.collected_at""",
                item,
            )
    return len(items)


def trend_items_list(market: str | None = None, niche: str | None = None, limit: int = 100) -> list[dict]:
    clauses, params = [], []
    if market:
        clauses.append("market=?")
        params.append(market)
    if niche:
        clauses.append("niche=?")
        params.append(niche)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    with _connect() as conn:
        return [dict(row) for row in conn.execute(
            f"SELECT * FROM trend_items{where} ORDER BY relevance_score DESC, collected_at DESC LIMIT ?",
            params,
        ).fetchall()]


def intelligence_report_create(market: str, niche: str, language: str, report_json: str) -> dict:
    item = {"id": str(uuid4()), "market": market, "niche": niche,
            "language": language, "report_json": report_json, "created_at": _now()}
    with _connect() as conn:
        conn.execute(
            """INSERT INTO intelligence_reports
            (id,market,niche,language,report_json,created_at)
            VALUES (:id,:market,:niche,:language,:report_json,:created_at)""",
            item,
        )
    return item


def intelligence_report_list(market: str | None = None, niche: str | None = None, limit: int = 30) -> list[dict]:
    clauses, params = [], []
    if market:
        clauses.append("market=?")
        params.append(market)
    if niche:
        clauses.append("niche=?")
        params.append(niche)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    with _connect() as conn:
        return [dict(row) for row in conn.execute(
            f"SELECT * FROM intelligence_reports{where} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()]


def strategy_plan_create(data: dict, items: list[dict]) -> dict:
    now = _now()
    plan = {"id": str(uuid4()), **data, "created_at": now}
    with _connect() as conn:
        conn.execute(
            """INSERT INTO strategy_plans
            (id,name,market,niche,language,channel_id,start_date,days,videos_per_day,plan_json,created_at)
            VALUES (:id,:name,:market,:niche,:language,:channel_id,:start_date,:days,:videos_per_day,:plan_json,:created_at)""",
            plan,
        )
        for item in items:
            row = {"id": str(uuid4()), "plan_id": plan["id"], **item, "status": "planned",
                   "project_id": None, "created_at": now}
            conn.execute(
                """INSERT INTO strategy_items
                (id,plan_id,day_number,planned_date,slot,topic,angle,title,hook,format,status,project_id,created_at)
                VALUES (:id,:plan_id,:day_number,:planned_date,:slot,:topic,:angle,:title,:hook,:format,:status,:project_id,:created_at)""",
                row,
            )
    return strategy_plan_get(plan["id"])


def strategy_plan_get(plan_id: str) -> dict | None:
    with _connect() as conn:
        plan = _dict(conn.execute("SELECT * FROM strategy_plans WHERE id=?", (plan_id,)).fetchone())
        if not plan:
            return None
        try:
            plan["summary"] = json.loads(plan.pop("plan_json"))
        except (json.JSONDecodeError, TypeError):
            plan["summary"] = {}
        plan["items"] = [dict(row) for row in conn.execute(
            "SELECT * FROM strategy_items WHERE plan_id=? ORDER BY day_number,slot", (plan_id,)
        ).fetchall()]
        return plan


def strategy_plan_list(market: str | None = None, niche: str | None = None, limit: int = 30) -> list[dict]:
    clauses, params = [], []
    if market:
        clauses.append("market=?")
        params.append(market)
    if niche:
        clauses.append("niche=?")
        params.append(niche)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    with _connect() as conn:
        return [dict(row) for row in conn.execute(
            f"SELECT id,name,market,niche,language,channel_id,start_date,days,videos_per_day,created_at FROM strategy_plans{where} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()]


def strategy_item_update(item_id: str, status: str, project_id: str | None = None) -> dict | None:
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE strategy_items SET status=?,project_id=COALESCE(?,project_id) WHERE id=?",
            (status, project_id, item_id),
        )
        if not cur.rowcount:
            return None
        return _dict(conn.execute("SELECT * FROM strategy_items WHERE id=?", (item_id,)).fetchone())


def production_batch_create(strategy_id: str, strategy_items: list[dict], options: dict) -> dict:
    now = _now()
    batch = {"id": str(uuid4()), "strategy_id": strategy_id, "status": "queued",
             "total_items": len(strategy_items), "completed_items": 0, "failed_items": 0,
             "options_json": json.dumps(options, ensure_ascii=False), "error": "",
             "created_at": now, "updated_at": now}
    with _connect() as conn:
        conn.execute(
            """INSERT INTO production_batches
            (id,strategy_id,status,total_items,completed_items,failed_items,options_json,error,created_at,updated_at)
            VALUES (:id,:strategy_id,:status,:total_items,:completed_items,:failed_items,:options_json,:error,:created_at,:updated_at)""",
            batch,
        )
        for source in strategy_items:
            conn.execute(
                """INSERT INTO production_batch_items
                (id,batch_id,strategy_item_id,status,attempts,error,created_at,updated_at)
                VALUES (?,?,?,'queued',0,'',?,?)""",
                (str(uuid4()), batch["id"], source["id"], now, now),
            )
    return production_batch_get(batch["id"])


def production_batch_get(batch_id: str) -> dict | None:
    with _connect() as conn:
        batch = _dict(conn.execute("SELECT * FROM production_batches WHERE id=?", (batch_id,)).fetchone())
        if not batch:
            return None
        try:
            batch["options"] = json.loads(batch.pop("options_json"))
        except (json.JSONDecodeError, TypeError):
            batch["options"] = {}
        batch["items"] = [dict(row) for row in conn.execute(
            "SELECT * FROM production_batch_items WHERE batch_id=? ORDER BY created_at,id", (batch_id,)
        ).fetchall()]
        return batch


def production_batch_list(limit: int = 30) -> list[dict]:
    with _connect() as conn:
        ids = [row["id"] for row in conn.execute(
            "SELECT id FROM production_batches ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()]
    return [batch for batch_id in ids if (batch := production_batch_get(batch_id))]


def production_batch_item_update(item_id: str, status: str, **fields) -> dict | None:
    allowed = {"project_id", "package_id", "voice_job_id", "render_job_id", "attempts", "error"}
    updates = {key: value for key, value in fields.items() if key in allowed}
    updates["status"] = status
    updates["updated_at"] = _now()
    assignments = ", ".join(f"{key}=:{key}" for key in updates)
    updates["id"] = item_id
    with _connect() as conn:
        cur = conn.execute(f"UPDATE production_batch_items SET {assignments} WHERE id=:id", updates)
        if not cur.rowcount:
            return None
        return _dict(conn.execute("SELECT * FROM production_batch_items WHERE id=?", (item_id,)).fetchone())


def production_batch_refresh(batch_id: str) -> dict | None:
    with _connect() as conn:
        counts = conn.execute(
            """SELECT COUNT(*) total,
            SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) completed,
            SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) failed,
            SUM(CASE WHEN status IN ('queued','processing') THEN 1 ELSE 0 END) active
            FROM production_batch_items WHERE batch_id=?""", (batch_id,)
        ).fetchone()
        status = "processing" if counts["active"] else ("completed" if counts["failed"] == 0 else ("partial_failure" if counts["completed"] else "failed"))
        conn.execute(
            """UPDATE production_batches SET status=?,total_items=?,completed_items=?,failed_items=?,updated_at=? WHERE id=?""",
            (status, counts["total"] or 0, counts["completed"] or 0, counts["failed"] or 0, _now(), batch_id),
        )
    return production_batch_get(batch_id)


def production_batch_item_get(item_id: str) -> dict | None:
    with _connect() as conn:
        return _dict(conn.execute("SELECT * FROM production_batch_items WHERE id=?", (item_id,)).fetchone())


def publish_job_create(data: dict) -> dict:
    now = _now()
    item = {"id": str(uuid4()), **data, "status": "awaiting_approval",
            "scheduled_at": None, "approved_at": None, "published_at": None,
            "platform_post_id": None, "error": "", "created_at": now, "updated_at": now}
    with _connect() as conn:
        conn.execute(
            """INSERT INTO publish_jobs
            (id,channel_id,project_id,render_job_id,title,caption,status,scheduled_at,approved_at,published_at,platform_post_id,error,created_at,updated_at)
            VALUES (:id,:channel_id,:project_id,:render_job_id,:title,:caption,:status,:scheduled_at,:approved_at,:published_at,:platform_post_id,:error,:created_at,:updated_at)""",
            item,
        )
    return item


def publish_job_get(job_id: str) -> dict | None:
    with _connect() as conn:
        return _dict(conn.execute("SELECT * FROM publish_jobs WHERE id=?", (job_id,)).fetchone())


def publish_job_list(channel_id: str | None = None, status: str | None = None, limit: int = 50) -> list[dict]:
    clauses, params = [], []
    if channel_id:
        clauses.append("channel_id=?")
        params.append(channel_id)
    if status:
        clauses.append("status=?")
        params.append(status)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    with _connect() as conn:
        return [dict(row) for row in conn.execute(
            f"SELECT * FROM publish_jobs{where} ORDER BY COALESCE(scheduled_at,created_at) ASC LIMIT ?",
            params,
        ).fetchall()]


def publish_job_update(job_id: str, status: str, **fields) -> dict | None:
    allowed = {"scheduled_at", "approved_at", "published_at", "platform_post_id", "error"}
    updates = {key: value for key, value in fields.items() if key in allowed}
    updates.update({"status": status, "updated_at": _now(), "id": job_id})
    assignments = ", ".join(f"{key}=:{key}" for key in updates if key != "id")
    with _connect() as conn:
        cur = conn.execute(f"UPDATE publish_jobs SET {assignments} WHERE id=:id", updates)
        if not cur.rowcount:
            return None
        return _dict(conn.execute("SELECT * FROM publish_jobs WHERE id=?", (job_id,)).fetchone())


def oauth_state_create(state: str, channel_id: str, provider: str, expires_at: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO oauth_states(state,channel_id,provider,expires_at,created_at) VALUES(?,?,?,?,?)",
            (state, channel_id, provider, expires_at, _now()),
        )


def oauth_state_consume(state: str, provider: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM oauth_states WHERE state=? AND provider=? AND expires_at>?",
            (state, provider, _now()),
        ).fetchone()
        if not row:
            conn.execute("DELETE FROM oauth_states WHERE state=?", (state,))
            return None
        result = dict(row)
        conn.execute("DELETE FROM oauth_states WHERE state=?", (state,))
        return result


def platform_credential_save(channel_id: str, provider: str, encrypted_credentials: str) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO platform_credentials(channel_id,provider,encrypted_credentials,updated_at)
            VALUES(?,?,?,?) ON CONFLICT(channel_id,provider) DO UPDATE SET
            encrypted_credentials=excluded.encrypted_credentials,updated_at=excluded.updated_at""",
            (channel_id, provider, encrypted_credentials, _now()),
        )


def platform_credential_get(channel_id: str, provider: str) -> dict | None:
    with _connect() as conn:
        return _dict(conn.execute(
            "SELECT channel_id,provider,encrypted_credentials,updated_at FROM platform_credentials WHERE channel_id=? AND provider=?",
            (channel_id, provider),
        ).fetchone())


def platform_credential_delete(channel_id: str, provider: str) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM platform_credentials WHERE channel_id=? AND provider=?",
            (channel_id, provider),
        )
        return bool(cur.rowcount)


def publish_job_claim_due(now: str) -> dict | None:
    """Atomically claim one due scheduled job across worker processes."""
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """SELECT id FROM publish_jobs
            WHERE status='scheduled' AND scheduled_at IS NOT NULL AND scheduled_at<=?
            ORDER BY scheduled_at ASC LIMIT 1""", (now,)
        ).fetchone()
        if not row:
            return None
        job_id = row["id"]
        cur = conn.execute(
            """UPDATE publish_jobs SET status='publishing',attempts=attempts+1,
            error='',updated_at=? WHERE id=? AND status='scheduled'""",
            (now, job_id),
        )
        if cur.rowcount != 1:
            return None
        return _dict(conn.execute("SELECT * FROM publish_jobs WHERE id=?", (job_id,)).fetchone())


def publish_job_requeue_stale(cutoff: str, now: str) -> int:
    """Mark long-abandoned uploads failed; never blindly duplicate an uncertain upload."""
    with _connect() as conn:
        cur = conn.execute(
            """UPDATE publish_jobs SET status='failed',
            error='Worker lease expired; verify the YouTube channel before retrying.',
            updated_at=? WHERE status='publishing' AND updated_at<?""",
            (now, cutoff),
        )
        return cur.rowcount


def publish_job_retry(job_id: str, scheduled_at: str) -> dict | None:
    with _connect() as conn:
        cur = conn.execute(
            """UPDATE publish_jobs SET status='scheduled',scheduled_at=?,error='',
            updated_at=? WHERE id=? AND status='failed'""",
            (scheduled_at, _now(), job_id),
        )
        if not cur.rowcount:
            return None
        return _dict(conn.execute("SELECT * FROM publish_jobs WHERE id=?", (job_id,)).fetchone())
