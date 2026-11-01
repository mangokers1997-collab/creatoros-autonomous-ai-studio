from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
import secrets
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, UploadFile, File, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Literal
from app import database
from app.auth import (SESSION_COOKIE, SESSION_DAYS, create_owner, get_session, init_auth_tables, login as auth_login, owner_exists, revoke_session)
from app.database import init_db, channel_create, channel_list, channel_delete, channel_get
from app.database import project_create, project_list, project_get, project_update_status
from app.database import research_create, research_list, research_get, research_source_create
from app.database import content_package_list, media_asset_create, media_asset_get, media_asset_list
from app.database import render_job_create, render_job_get, render_job_list, render_scene_assets_replace
from app.database import voice_job_create, voice_job_get, voice_job_list
from app.content_engine import generate_content_package
from app.renderer import MEDIA_ROOT, RENDER_ROOT, ffmpeg_available, run_render_job
from app.voice_engine import piper_available, run_voice_job
from app.database import trend_items_list
from app.trend_engine import fetch_google_trends, MARKETS
from app.intelligence_engine import analyze_content_opportunities, get_intelligence_reports
from app.strategy_engine import generate_strategy, get_strategy, list_strategies, update_strategy_item
from app.database import production_batch_create, production_batch_get, production_batch_list, production_batch_refresh
from app.database import production_orchestration_get
from app.pipeline_engine import run_production_batch, retry_production_batch_item
from app.production_orchestrator import create_production_orchestration, run_production_orchestration, get_production_orchestrations
from app.publishing_engine import (
    create_publish_draft, approve_publish_job, cancel_publish_job,
    list_publish_jobs, get_publish_job, publishing_adapter_status, retry_publish_job,
)
from app.platform_validation import validate_publish_metadata
from app.youtube_adapter import (
    start_youtube_connection, complete_youtube_connection,
    youtube_connection_status, upload_youtube_video,
)
from app.publishing_worker import start_worker, stop_worker, worker_status
from app.control_center import get_control_center
from app.performance_optimizer import build_optimization_report
from app.content_brain import build_content_brain_report, create_brain_strategy
from app.channel_orchestrator import build_channel_orchestrator_overview, create_multi_channel_strategy_plans
from app.script_engine import generate_script, list_scripts, get_script, update_script, delete_script
from app.script_voice_engine import available as script_voice_available, create_job as create_script_voice_job, get_job as get_script_voice_job, list_jobs as list_script_voice_jobs, run_job as run_script_voice_job, audio_path as script_voice_audio_path
from app.script_video_engine import create_job as create_script_video_job, get_job as get_script_video_job, list_jobs as list_script_video_jobs, run_job as run_script_video_job, video_path as script_video_path

ChannelPlatform = Literal["youtube", "instagram", "facebook", "tiktok"]
ProjectStatus = Literal["idea", "research", "script", "storyboard", "ready_for_review", "approved", "rendering", "rendered", "scheduled", "published", "failed"]


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    init_auth_tables()
    start_worker()
    try:
        yield
    finally:
        stop_worker()


app = FastAPI(
    title="CreatorOS API",
    description="Zero-budget-first API foundation for a multi-channel content studio.",
    version="1.4.0",
    lifespan=lifespan,
)

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
if WEB_ROOT.is_dir():
    app.mount("/dashboard", StaticFiles(directory=str(WEB_ROOT), html=True), name="dashboard")




class AuthCredentials(BaseModel):
    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=12, max_length=128)


class SetupCredentials(AuthCredentials):
    bootstrap_token: str = Field(min_length=32, max_length=256)


PUBLIC_AUTH_PATHS = {
    "/api/v1/auth/status", "/api/v1/auth/setup",
    "/api/v1/auth/login", "/api/v1/auth/logout",
    "/api/v1/oauth/youtube/callback",
}
PUBLIC_ROOT_PATHS = {"/", "/health", "/dashboard", "/dashboard/"}
COOKIE_SECURE = __import__("os").getenv("CREATOROS_COOKIE_SECURE", "false").lower() in {"1", "true", "yes"}


@app.middleware("http")
async def require_authenticated_session(request: Request, call_next):
    path = request.url.path
    if path in PUBLIC_AUTH_PATHS or path in PUBLIC_ROOT_PATHS:
        return await call_next(request)
    token = request.cookies.get(SESSION_COOKIE)
    user = get_session(token)
    if not user:
        if path.startswith("/api/"):
            return JSONResponse({"detail": "Authentication required."}, status_code=401)
        return JSONResponse({"detail": "Authentication required."}, status_code=401)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        # Require a custom same-origin header on cookie-authenticated mutations.
        if request.headers.get("x-creatoros-request") != "1":
            return JSONResponse({"detail": "CSRF protection rejected this request."}, status_code=403)
    request.state.user = user
    return await call_next(request)


def _set_session_cookie(response: JSONResponse, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE, value=token, httponly=True, secure=COOKIE_SECURE,
        samesite="strict", max_age=SESSION_DAYS * 24 * 60 * 60, path="/",
    )


@app.get("/api/v1/auth/status")
def auth_status():
    return {"setup_required": not owner_exists()}


@app.post("/api/v1/auth/setup")
def auth_setup(payload: SetupCredentials):
    expected = __import__("os").getenv("CREATOROS_SETUP_TOKEN", "")
    if len(expected) < 32 or not secrets.compare_digest(payload.bootstrap_token, expected):
        raise HTTPException(status_code=403, detail="Invalid or missing first-run setup token.")
    try:
        user, token = create_owner(payload.username, payload.password)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    response = JSONResponse({"user": user, "message": "Owner account created."})
    _set_session_cookie(response, token)
    return response


@app.post("/api/v1/auth/login")
def auth_login_route(payload: AuthCredentials):
    try:
        result = auth_login(payload.username, payload.password)
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    if not result:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    user, token = result
    response = JSONResponse({"user": user, "message": "Signed in."})
    _set_session_cookie(response, token)
    return response


@app.post("/api/v1/auth/logout")
def auth_logout(request: Request):
    revoke_session(request.cookies.get(SESSION_COOKIE))
    response = JSONResponse({"message": "Signed out."})
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=COOKIE_SECURE, samesite="strict")
    return response


@app.get("/api/v1/auth/me")
def auth_me(request: Request):
    return {"user": request.state.user}


class ChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    platform: ChannelPlatform
    target_market: str = Field(default="US", min_length=2, max_length=40)
    language: str = Field(default="en", min_length=2, max_length=12)
    niche: str = Field(default="general", max_length=80)


class ProjectCreate(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    niche: str = Field(default="general", max_length=80)
    target_market: str = Field(default="US", min_length=2, max_length=40)
    language: str = Field(default="en", min_length=2, max_length=12)
    format: Literal["short", "long"] = "short"
    channel_id: str | None = None
    brief: str = Field(default="", max_length=4000)


class ProjectStatusUpdate(BaseModel):
    status: ProjectStatus


class ResearchBriefCreate(BaseModel):
    topic: str = Field(min_length=3, max_length=180)
    niche: str = Field(default="general", max_length=80)
    target_market: str = Field(default="US", min_length=2, max_length=40)
    language: str = Field(default="en", min_length=2, max_length=12)
    audience: str = Field(default="", max_length=300)
    goal: str = Field(default="", max_length=300)
    keywords: str = Field(default="", max_length=1500, description="Comma-separated seed keywords")
    competitors: str = Field(default="", max_length=1500, description="Comma-separated competitor names or channels")
    notes: str = Field(default="", max_length=4000)


class RenderRequest(BaseModel):
    package_id: str
    image_asset_id: str | None = None
    audio_asset_id: str | None = None
    duration_seconds: int = Field(default=48, ge=8, le=180)
    scene_asset_ids: list[str | None] = Field(default_factory=list, max_length=12)


class TrendRefreshRequest(BaseModel):
    market: str = Field(default="US", min_length=2, max_length=2)
    niche: str = Field(default="", max_length=80)
    keywords: list[str] = Field(default_factory=list, max_length=20)


class IntelligenceRequest(BaseModel):
    market: str = Field(default="US", min_length=2, max_length=2)
    niche: str = Field(default="personal finance", min_length=2, max_length=80)
    language: str = Field(default="", max_length=12)
    seed_keywords: list[str] = Field(default_factory=list, max_length=30)
    competitor_queries: list[str] = Field(default_factory=list, max_length=5)


class ContentBrainRequest(BaseModel):
    market: str = Field(default="ID", min_length=2, max_length=2)
    niche: str = Field(default="personal finance", min_length=2, max_length=80)
    language: str = Field(default="", max_length=12)
    channel_id: str | None = None
    limit: int = Field(default=12, ge=1, le=90)


class ContentBrainPlanRequest(BaseModel):
    market: str = Field(default="ID", min_length=2, max_length=2)
    niche: str = Field(default="personal finance", min_length=2, max_length=80)
    language: str = Field(default="id", max_length=12)
    channel_id: str | None = None
    start_date: str = Field(default_factory=lambda: __import__("datetime").date.today().isoformat())
    days: int = Field(default=30, ge=1, le=90)
    videos_per_day: int = Field(default=1, ge=1, le=5)


class MultiChannelStrategyRequest(BaseModel):
    channel_ids: list[str] = Field(min_length=1, max_length=25)
    start_date: str = Field(default_factory=lambda: __import__("datetime").date.today().isoformat())
    days: int = Field(default=30, ge=1, le=90)
    videos_per_day: int = Field(default=1, ge=1, le=5)


class StrategyGenerateRequest(BaseModel):
    market: str = Field(default="US", min_length=2, max_length=2)
    niche: str = Field(default="personal finance", min_length=2, max_length=80)
    language: str = Field(default="en", max_length=12)
    channel_id: str | None = None
    start_date: str = Field(default_factory=lambda: __import__("datetime").date.today().isoformat())
    days: int = Field(default=30, ge=1, le=90)
    videos_per_day: int = Field(default=1, ge=1, le=5)


class StrategyItemUpdate(BaseModel):
    status: Literal["planned", "in_progress", "ready_for_review", "approved", "skipped", "published"] = "planned"
    project_id: str | None = None


class ExperimentCreateRequest(BaseModel):
    strategy_item_id: str
    hypothesis: str = Field(min_length=8, max_length=500)
    variant_b_title: str = Field(min_length=3, max_length=100)
    variant_b_hook: str = Field(min_length=3, max_length=300)


class ExperimentMetricRequest(BaseModel):
    views: int = Field(default=0, ge=0, le=1000000000)
    likes: int = Field(default=0, ge=0, le=1000000000)
    comments: int = Field(default=0, ge=0, le=1000000000)
    shares: int = Field(default=0, ge=0, le=1000000000)
    watch_time_minutes: float = Field(default=0, ge=0, le=100000000000)
    sample_count: int = Field(default=1, ge=1, le=1000000)


class ExperimentEvaluateRequest(BaseModel):
    minimum_views: int = Field(default=100, ge=10, le=1000000)


class ExperimentPromoteRequest(BaseModel):
    variant_id: str


class ProductionOrchestrationRequest(BaseModel):
    strategy_ids: list[str] = Field(min_length=1, max_length=25)
    max_items: int = Field(default=5, ge=1, le=5)
    generate_voice: bool = True
    render_video: bool = True
    duration_seconds: int = Field(default=48, ge=8, le=180)


class ProductionBatchRequest(BaseModel):
    strategy_id: str
    max_items: int = Field(default=5, ge=1, le=5)
    generate_voice: bool = True
    render_video: bool = True
    duration_seconds: int = Field(default=48, ge=8, le=180)


class YouTubeUploadRequest(BaseModel):
    privacy_status: Literal["private", "unlisted", "public"] = "private"


class PublishMetadataValidationRequest(BaseModel):
    platform: ChannelPlatform
    title: str = Field(default="", max_length=1000)
    caption: str = Field(default="", max_length=70000)


class PublishDraftRequest(BaseModel):
    channel_id: str
    project_id: str
    render_job_id: str
    title: str = Field(min_length=1, max_length=100)
    caption: str = Field(default="", max_length=5000)


class PublishApprovalRequest(BaseModel):
    scheduled_at: str = Field(min_length=20, max_length=40)


class ScriptGenerateRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=180)
    niche: str = Field(default="general", min_length=2, max_length=80)
    market: str = Field(default="ID", min_length=2, max_length=2)
    language: Literal["id", "en", "ja", "ar"] = "id"
    audience: str = Field(default="pemula", max_length=180)
    format: Literal["short", "long"] = "short"
    duration_seconds: int = Field(default=60, ge=15, le=1800)
    style: Literal["educational", "storytelling", "motivational", "documentary"] = "storytelling"
    structure: Literal["problem_solution", "plot_twist", "listicle", "myth_busting", "case_study"] = "plot_twist"
    call_to_action: str = Field(default="Ikuti untuk konten berikutnya.", max_length=300)
    source_notes: str = Field(default="", max_length=2000)


class ScriptUpdateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    content: dict


class ResearchSourceCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    url: str = Field(default="", max_length=1000)
    source_type: Literal["article", "video", "report", "forum", "other"] = "article"
    observation: str = Field(default="", max_length=2000)


@app.get("/")
def root():
    return {"name": "CreatorOS API", "version": "1.4.0", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok", "service": "creatoros-api", "version": "1.4.0"}


@app.get("/api/v1/orchestrator/overview")
def channel_orchestrator_overview():
    return build_channel_orchestrator_overview()


@app.post("/api/v1/orchestrator/strategy-plans", status_code=201)
def orchestrate_channel_strategies(payload: MultiChannelStrategyRequest):
    try:
        return create_multi_channel_strategy_plans(
            payload.channel_ids, payload.start_date,
            payload.days, payload.videos_per_day,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/api/v1/channels")
def list_channels():
    return channel_list()


@app.post("/api/v1/channels", status_code=201)
def create_channel(payload: ChannelCreate):
    return channel_create(payload.model_dump())


@app.delete("/api/v1/channels/{channel_id}")
def delete_channel(channel_id: str):
    removed = channel_delete(channel_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Channel not found")
    return {"deleted": True, "id": channel_id}


@app.get("/api/v1/projects")
def list_projects(
    status: ProjectStatus | None = None,
    channel_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    return project_list(status=status, channel_id=channel_id, limit=limit)


@app.post("/api/v1/projects", status_code=201)
def create_project(payload: ProjectCreate):
    if payload.channel_id:
        from app.database import channel_get
        if not channel_get(payload.channel_id):
            raise HTTPException(status_code=404, detail="Channel not found")
    return project_create(payload.model_dump())


@app.get("/api/v1/projects/{project_id}")
def get_project(project_id: str):
    project = project_get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.patch("/api/v1/projects/{project_id}/status")
def update_project_status(project_id: str, payload: ProjectStatusUpdate):
    project = project_update_status(project_id, payload.status)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.get("/api/v1/research")
def list_research(
    target_market: str | None = None,
    niche: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    return research_list(target_market=target_market, niche=niche, limit=limit)


@app.post("/api/v1/research", status_code=201)
def create_research(payload: ResearchBriefCreate):
    return research_create(payload.model_dump())


@app.get("/api/v1/research/{brief_id}")
def get_research(brief_id: str):
    brief = research_get(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail="Research brief not found")
    return brief


@app.post("/api/v1/research/{brief_id}/sources", status_code=201)
def add_research_source(brief_id: str, payload: ResearchSourceCreate):
    source = research_source_create(brief_id, payload.model_dump())
    if not source:
        raise HTTPException(status_code=404, detail="Research brief not found")
    return source


@app.post("/api/v1/scripts/generate", status_code=201)
def create_generated_script(payload: ScriptGenerateRequest):
    try:
        return generate_script(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/api/v1/scripts")
def list_generated_scripts(limit: int = Query(default=50, ge=1, le=200)):
    return list_scripts(limit=limit)


@app.get("/api/v1/scripts/{script_id}")
def get_generated_script(script_id: str):
    script = get_script(script_id)
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
    return script


@app.patch("/api/v1/scripts/{script_id}")
def update_generated_script(script_id: str, payload: ScriptUpdateRequest):
    script = update_script(script_id, payload.title, payload.content)
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
    return script


@app.delete("/api/v1/scripts/{script_id}")
def delete_generated_script(script_id: str):
    if not delete_script(script_id):
        raise HTTPException(status_code=404, detail="Script not found")
    return {"deleted": True, "id": script_id}



@app.post("/api/v1/scripts/{script_id}/voice", status_code=202)
def create_script_voice(script_id: str, background_tasks: BackgroundTasks):
    job = create_script_voice_job(script_id)
    if not job:
        raise HTTPException(status_code=404, detail="Saved script not found")
    background_tasks.add_task(run_script_voice_job, job["id"])
    return {**job, "piper_available": script_voice_available()}


@app.get("/api/v1/script-voice-jobs")
def list_script_voice(limit: int = Query(default=50, ge=1, le=200)):
    return list_script_voice_jobs(limit)


@app.get("/api/v1/script-voice-jobs/{job_id}")
def get_script_voice(job_id: str):
    job = get_script_voice_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Voice job not found")
    return job


@app.get("/api/v1/script-voice-jobs/{job_id}/audio")
def download_script_voice(job_id: str):
    job = get_script_voice_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Voice job not found")
    path = script_voice_audio_path(job_id)
    if not path:
        raise HTTPException(status_code=409 if job["status"] != "ready" else 404, detail="Audio is not ready or file is missing")
    return FileResponse(path, media_type="audio/wav", filename=f"creatoros-script-voice-{job_id}.wav")


@app.get("/api/v1/script-voice-jobs/{job_id}/subtitles")
def download_script_voice_subtitles(job_id: str):
    job = get_script_voice_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Voice job not found")
    if job["status"] != "ready":
        raise HTTPException(status_code=409, detail="Subtitles are not ready")
    from fastapi.responses import Response
    return Response(content=job["subtitles_srt"], media_type="application/x-subrip",
        headers={"Content-Disposition": f'attachment; filename="creatoros-script-{job_id}.srt"'})



@app.post("/api/v1/scripts/{script_id}/video", status_code=202)
def create_script_video(script_id: str, payload: dict, background_tasks: BackgroundTasks):
    voice_job_id = str(payload.get("voice_job_id", ""))
    scene_asset_ids = payload.get("scene_asset_ids", [])
    if not isinstance(scene_asset_ids, list) or len(scene_asset_ids) > 12:
        raise HTTPException(status_code=422, detail="scene_asset_ids must be a list with at most 12 entries")
    motion_preset = str(payload.get('motion_preset', 'cinematic'))
    if motion_preset not in {'cinematic', 'gentle_zoom', 'pan_left', 'pan_right', 'static'}:
        raise HTTPException(status_code=422, detail='Unsupported motion preset')
    job = create_script_video_job(script_id, voice_job_id, scene_asset_ids, motion_preset)
    if not job:
        raise HTTPException(status_code=400, detail="Matching script, voice job, and valid image assets are required")
    background_tasks.add_task(run_script_video_job, job["id"])
    return {**job, "ffmpeg_available": ffmpeg_available()}



@app.get("/api/v1/scripts/{script_id}/visual-prompts")
def get_script_visual_prompts(script_id: str):
    from app.visual_prompt_engine import build_visual_prompt_pack
    result = build_visual_prompt_pack(script_id)
    if not result:
        raise HTTPException(status_code=404, detail="Script not found")
    return result


@app.get("/api/v1/script-video-jobs")
def list_script_video_jobs(limit: int = Query(default=50, ge=1, le=200)):
    return list_script_video_jobs(limit)


@app.get("/api/v1/script-video-jobs/{job_id}")
def get_script_video_job(job_id: str):
    job = get_script_video_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Video job not found")
    return job



@app.get("/api/v1/script-video-jobs/{job_id}/quality")
def inspect_script_video_quality(job_id: str):
    from app.video_quality_engine import inspect_video
    result = inspect_video(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Video job not found")
    return result


@app.get("/api/v1/script-video-jobs/{job_id}/download")
def download_script_video(job_id: str):
    job = get_script_video_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Video job not found")
    path = script_video_path(job_id)
    if not path:
        raise HTTPException(status_code=409 if job["status"] != "ready" else 404, detail="Video is not ready or file is missing")
    return FileResponse(path, media_type="video/mp4", filename=f"creatoros-{job_id}.mp4")


@app.get("/api/v1/trends/markets")
def list_trend_markets():
    return [{"code": code, "name": name} for code, name in MARKETS.items()]


@app.post("/api/v1/trends/refresh")
def refresh_trends(payload: TrendRefreshRequest):
    try:
        return fetch_google_trends(payload.market, payload.niche, payload.keywords)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.get("/api/v1/trends")
def list_trends(
    market: str | None = None,
    niche: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    return trend_items_list(market=market, niche=niche, limit=limit)


@app.post("/api/v1/intelligence/analyze")
def analyze_intelligence(payload: IntelligenceRequest):
    try:
        return analyze_content_opportunities(
            payload.market, payload.niche, payload.language,
            payload.seed_keywords, payload.competitor_queries,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/api/v1/intelligence/reports")
def list_intelligence_reports(
    market: str | None = None,
    niche: str | None = None,
    limit: int = Query(default=30, ge=1, le=100),
):
    return get_intelligence_reports(market=market, niche=niche, limit=limit)


@app.post("/api/v1/content-brain/analyze")
def content_brain_analyze(payload: ContentBrainRequest):
    try:
        return build_content_brain_report(
            payload.market, payload.niche, payload.language,
            payload.channel_id, payload.limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/v1/content-brain/strategy", status_code=201)
def content_brain_strategy(payload: ContentBrainPlanRequest):
    if payload.channel_id:
        channel = channel_get(payload.channel_id)
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        if channel["target_market"].upper() != payload.market.upper():
            raise HTTPException(status_code=422, detail="Channel market does not match requested market")
    try:
        return create_brain_strategy(
            payload.market, payload.niche, payload.language, payload.channel_id,
            payload.start_date, payload.days, payload.videos_per_day,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/v1/strategies/generate", status_code=201)
def create_strategy(payload: StrategyGenerateRequest):
    if payload.channel_id:
        from app.database import channel_get
        channel = channel_get(payload.channel_id)
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        if channel["target_market"].upper() != payload.market.upper():
            raise HTTPException(status_code=422, detail="Channel target market does not match strategy market")
    try:
        return generate_strategy(
            payload.market, payload.niche, payload.language, payload.channel_id,
            payload.start_date, payload.days, payload.videos_per_day,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/api/v1/strategies")
def list_strategy_plans(
    market: str | None = None,
    niche: str | None = None,
    limit: int = Query(default=30, ge=1, le=100),
):
    return list_strategies(market=market, niche=niche, limit=limit)


@app.get("/api/v1/strategies/{plan_id}")
def get_strategy_plan(plan_id: str):
    plan = get_strategy(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Strategy plan not found")
    return plan


@app.patch("/api/v1/strategy-items/{item_id}")
def patch_strategy_item(item_id: str, payload: StrategyItemUpdate):
    if payload.project_id and not project_get(payload.project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    item = update_strategy_item(item_id, payload.status, payload.project_id)
    if not item:
        raise HTTPException(status_code=404, detail="Strategy item not found")
    return item


@app.post("/api/v1/experiments", status_code=201)
def create_content_experiment(payload: ExperimentCreateRequest):
    try:
        experiment = database.experiment_create(
            payload.strategy_item_id, payload.hypothesis,
            payload.variant_b_title, payload.variant_b_hook,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if not experiment:
        raise HTTPException(status_code=404, detail="Strategy item not found")
    return experiment


@app.get("/api/v1/experiments")
def list_content_experiments(limit: int = Query(default=50, ge=1, le=100)):
    return database.experiment_list(limit=limit)


@app.post("/api/v1/experiments/variants/{variant_id}/metrics")
def record_experiment_metrics(variant_id: str, payload: ExperimentMetricRequest):
    row = database.experiment_variant_record(variant_id, payload.model_dump())
    if not row:
        raise HTTPException(status_code=404, detail="Experiment variant not found")
    return row


@app.post("/api/v1/experiments/{experiment_id}/evaluate")
def evaluate_content_experiment(experiment_id: str, payload: ExperimentEvaluateRequest):
    result = database.experiment_evaluate(experiment_id, payload.minimum_views)
    if not result:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return result


@app.post("/api/v1/experiments/{experiment_id}/promote")
def promote_experiment_winner(experiment_id: str, payload: ExperimentPromoteRequest):
    try:
        result = database.experiment_promote_winner(experiment_id, payload.variant_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if not result:
        raise HTTPException(status_code=404, detail="Experiment or variant not found")
    return result


@app.post("/api/v1/production-orchestrations", status_code=202)
def create_production_orchestration_route(payload: ProductionOrchestrationRequest, background_tasks: BackgroundTasks):
    try:
        orchestration = create_production_orchestration(
            payload.strategy_ids, payload.max_items,
            payload.generate_voice, payload.render_video, payload.duration_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    background_tasks.add_task(run_production_orchestration, orchestration["id"])
    return orchestration


@app.get("/api/v1/production-orchestrations")
def list_production_orchestrations(limit: int = Query(default=30, ge=1, le=100)):
    return get_production_orchestrations(limit)


@app.get("/api/v1/production-orchestrations/{orchestration_id}")
def get_production_orchestration_route(orchestration_id: str):
    orchestration = production_orchestration_get(orchestration_id)
    if not orchestration:
        raise HTTPException(status_code=404, detail="Production orchestration not found")
    return orchestration


@app.post("/api/v1/production-batches", status_code=202)
def create_production_batch(payload: ProductionBatchRequest, background_tasks: BackgroundTasks):
    plan = get_strategy(payload.strategy_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Strategy plan not found")
    candidates = [item for item in plan["items"] if item["status"] in {"planned", "in_progress"}]
    candidates = candidates[:payload.max_items]
    if not candidates:
        raise HTTPException(status_code=409, detail="No planned strategy items are available for production.")
    batch = production_batch_create(payload.strategy_id, candidates, {
        "generate_voice": payload.generate_voice,
        "render_video": payload.render_video,
        "duration_seconds": payload.duration_seconds,
    })
    background_tasks.add_task(run_production_batch, batch["id"])
    return batch


@app.get("/api/v1/production-batches")
def list_production_batches(limit: int = Query(default=30, ge=1, le=100)):
    return production_batch_list(limit=limit)


@app.get("/api/v1/production-batches/{batch_id}")
def get_production_batch(batch_id: str):
    batch = production_batch_get(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Production batch not found")
    return batch


@app.post("/api/v1/production-batch-items/{item_id}/retry", status_code=202)
def retry_production_item(item_id: str, background_tasks: BackgroundTasks):
    batch = retry_production_batch_item(item_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Failed batch item not found")
    background_tasks.add_task(run_production_batch, batch["id"])
    return batch


@app.get("/api/v1/oauth/youtube/connect")
def youtube_oauth_connect(channel_id: str):
    try:
        return start_youtube_connection(channel_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/api/v1/oauth/youtube/callback")
def youtube_oauth_callback(state: str, code: str | None = None, error: str | None = None):
    if error:
        raise HTTPException(status_code=400, detail="Google authorization was not completed.")
    if not code:
        raise HTTPException(status_code=400, detail="Authorization code is missing.")
    try:
        return complete_youtube_connection(state, code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"YouTube OAuth exchange failed: {str(exc)[:400]}")


@app.get("/api/v1/oauth/youtube/status/{channel_id}")
def youtube_oauth_status(channel_id: str):
    try:
        return youtube_connection_status(channel_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/api/v1/publishing/jobs/{job_id}/upload-youtube")
def youtube_upload(job_id: str, payload: YouTubeUploadRequest):
    try:
        return upload_youtube_video(job_id, payload.privacy_status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"YouTube upload failed: {str(exc)[:500]}")


@app.post("/api/v1/publishing/validate-metadata")
def validate_publishing_metadata(payload: PublishMetadataValidationRequest):
    return validate_publish_metadata(payload.platform, payload.title, payload.caption)


@app.post("/api/v1/publishing/drafts", status_code=201)
def create_publishing_draft(payload: PublishDraftRequest):
    try:
        return create_publish_draft(
            payload.channel_id, payload.project_id, payload.render_job_id,
            payload.title, payload.caption,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/api/v1/publishing/jobs")
def list_publishing_jobs(
    channel_id: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    return list_publish_jobs(channel_id=channel_id, status=status, limit=limit)


@app.get("/api/v1/publishing/jobs/{job_id}")
def get_publishing_job(job_id: str):
    job = get_publish_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Publishing job not found")
    return job


@app.post("/api/v1/publishing/jobs/{job_id}/approve")
def approve_publishing_job(job_id: str, payload: PublishApprovalRequest):
    try:
        job = approve_publish_job(job_id, payload.scheduled_at)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not job:
        raise HTTPException(status_code=409, detail="Job is not awaiting approval.")
    return job


@app.post("/api/v1/publishing/jobs/{job_id}/cancel")
def cancel_publishing_job(job_id: str):
    job = cancel_publish_job(job_id)
    if not job:
        raise HTTPException(status_code=409, detail="Job cannot be cancelled in its current state.")
    return job


@app.post("/api/v1/publishing/jobs/{job_id}/retry")
def retry_publishing_job(job_id: str, payload: PublishApprovalRequest):
    try:
        job = retry_publish_job(job_id, payload.scheduled_at)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not job:
        raise HTTPException(status_code=409, detail="Only failed jobs can be rescheduled.")
    return job


@app.get("/api/v1/publishing/worker")
def get_publishing_worker_status():
    return worker_status()


@app.get("/api/v1/publishing/adapters")
def get_publishing_adapters():
    return publishing_adapter_status()


@app.post("/api/v1/projects/{project_id}/generate-package", status_code=201)
def generate_project_package(project_id: str):
    package = generate_content_package(project_id)
    if not package:
        raise HTTPException(status_code=404, detail="Project not found")
    return package


@app.get("/api/v1/projects/{project_id}/packages")
def list_project_packages(project_id: str):
    if not project_get(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return content_package_list(project_id)


@app.post("/api/v1/assets/upload", status_code=201)
async def upload_asset(file: UploadFile = File(...)):
    content_type = (file.content_type or "").lower()
    image_types = {"image/jpeg", "image/png", "image/webp"}
    audio_types = {"audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/mp4", "audio/aac", "audio/ogg"}
    if content_type not in image_types | audio_types:
        raise HTTPException(status_code=415, detail="Supported files: JPG, PNG, WEBP, MP3, WAV, AAC, M4A/MP4 audio, or OGG.")
    data = await file.read(20 * 1024 * 1024 + 1)
    if not data or len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File must be between 1 byte and 20 MB.")
    media_type = "image" if content_type in image_types else "audio"
    extension = Path(file.filename or "upload.bin").suffix.lower()
    allowed_extensions = {".jpg", ".jpeg", ".png", ".webp"} if media_type == "image" else {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".mp4"}
    if extension not in allowed_extensions:
        raise HTTPException(status_code=415, detail="File extension does not match supported media types.")
    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4()}{extension}"
    (MEDIA_ROOT / stored_name).write_bytes(data)
    return media_asset_create({
        "original_name": (file.filename or "upload")[:255],
        "stored_name": stored_name,
        "media_type": media_type,
        "mime_type": content_type,
        "size_bytes": len(data),
    })


@app.get("/api/v1/assets")
def list_assets():
    return media_asset_list()


@app.post("/api/v1/projects/{project_id}/render", status_code=202)
def create_render(project_id: str, payload: RenderRequest, background_tasks: BackgroundTasks):
    if not project_get(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    packages = content_package_list(project_id)
    if not any(item["id"] == payload.package_id for item in packages):
        raise HTTPException(status_code=404, detail="Content package not found for this project")
    image = media_asset_get(payload.image_asset_id) if payload.image_asset_id else None
    audio = media_asset_get(payload.audio_asset_id) if payload.audio_asset_id else None
    if payload.image_asset_id and (not image or image["media_type"] != "image"):
        raise HTTPException(status_code=400, detail="image_asset_id must reference an uploaded image")
    if payload.audio_asset_id and (not audio or audio["media_type"] != "audio"):
        raise HTTPException(status_code=400, detail="audio_asset_id must reference uploaded audio")
    job = render_job_create({
        "project_id": project_id,
        "package_id": payload.package_id,
        "image_asset_id": payload.image_asset_id,
        "audio_asset_id": payload.audio_asset_id,
        "duration_seconds": payload.duration_seconds,
    })
    scenes = packages[[item["id"] for item in packages].index(payload.package_id)].get("storyboard_json", [])
    if not scenes:
        scenes = [{"on_screen_text": payload.package_id, "narration": "", "visual_direction": ""}]
    if len(scenes) > 12:
        raise HTTPException(status_code=400, detail="A maximum of 12 storyboard scenes is supported.")
    if payload.scene_asset_ids and len(payload.scene_asset_ids) != len(scenes):
        raise HTTPException(status_code=400, detail="scene_asset_ids must contain one entry per storyboard scene.")
    scene_rows = []
    for index, scene in enumerate(scenes):
        asset_id = payload.scene_asset_ids[index] if payload.scene_asset_ids else payload.image_asset_id
        scene_image = media_asset_get(asset_id) if asset_id else None
        if asset_id and (not scene_image or scene_image["media_type"] != "image"):
            raise HTTPException(status_code=400, detail=f"Scene {index + 1} image must reference an uploaded image.")
        scene_rows.append({
            "image_asset_id": asset_id,
            "caption": scene.get("narration") or scene.get("on_screen_text") or "",
            "visual_direction": scene.get("visual_direction") or "",
        })
    render_scene_assets_replace(job["id"], scene_rows)
    background_tasks.add_task(run_render_job, job["id"])
    return {**job, "ffmpeg_available": ffmpeg_available()}


@app.post("/api/v1/projects/{project_id}/packages/{package_id}/voice", status_code=202)
def create_voice(project_id: str, package_id: str, background_tasks: BackgroundTasks):
    if not project_get(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    if not any(item["id"] == package_id for item in content_package_list(project_id)):
        raise HTTPException(status_code=404, detail="Content package not found")
    job = voice_job_create({"project_id": project_id, "package_id": package_id})
    background_tasks.add_task(run_voice_job, job["id"])
    return {**job, "piper_available": piper_available()}


@app.get("/api/v1/voice-jobs")
def list_voice_jobs(project_id: str | None = None, limit: int = Query(default=50, ge=1, le=200)):
    return voice_job_list(project_id=project_id, limit=limit)


@app.get("/api/v1/voice-jobs/{job_id}")
def get_voice_job(job_id: str):
    job = voice_job_get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Voice job not found")
    return job


@app.get("/api/v1/voice-jobs/{job_id}/audio")
def download_voice_audio(job_id: str):
    job = voice_job_get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Voice job not found")
    if job["status"] != "ready" or not job["audio_asset_id"]:
        raise HTTPException(status_code=409, detail="Voice audio is not ready")
    asset = media_asset_get(job["audio_asset_id"])
    path = (MEDIA_ROOT / asset["stored_name"]).resolve() if asset else None
    if not path or MEDIA_ROOT not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Voice audio file not found")
    return FileResponse(path, media_type="audio/wav", filename=f"creatoros-voice-{job_id}.wav")


@app.get("/api/v1/voice-jobs/{job_id}/subtitles")
def download_voice_subtitles(job_id: str):
    job = voice_job_get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Voice job not found")
    if job["status"] != "ready":
        raise HTTPException(status_code=409, detail="Voice subtitles are not ready")
    from fastapi.responses import Response
    return Response(
        content=job["subtitles_srt"],
        media_type="application/x-subrip",
        headers={"Content-Disposition": f'attachment; filename="creatoros-{job_id}.srt"'},
    )


@app.get("/api/v1/renders")
def list_renders(project_id: str | None = None, limit: int = Query(default=50, ge=1, le=200)):
    return render_job_list(project_id=project_id, limit=limit)


@app.get("/api/v1/renders/{job_id}")
def get_render(job_id: str):
    job = render_job_get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Render job not found")
    return job


@app.get("/api/v1/renders/{job_id}/download")
def download_render(job_id: str):
    job = render_job_get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Render job not found")
    if job["status"] != "rendered" or not job["output_path"]:
        raise HTTPException(status_code=409, detail="Render is not ready")
    output = Path(job["output_path"]).resolve()
    if RENDER_ROOT not in output.parents or not output.is_file():
        raise HTTPException(status_code=404, detail="Rendered file not found")
    return FileResponse(output, media_type="video/mp4", filename=f"creatoros-{job_id}.mp4")


@app.get("/api/v1/control-center")
def control_center():
    return get_control_center()


@app.get("/api/v1/system/status")
def system_status():
    return {
        "phase": "unified-control-center-api",
        "database": "sqlite",
        "ai_provider": "local_piper_available" if piper_available() else "local_piper_not_configured",
        "render_engine": "ffmpeg_available" if ffmpeg_available() else "ffmpeg_not_installed",
        "publishing": "youtube_oauth_adapter_and_opt_in_worker_foundation",
        "human_approval_required": True,
    }


class ChannelMetricCreate(BaseModel):
    channel_id: str = Field(min_length=1, max_length=80)
    publish_job_id: str | None = Field(default=None, max_length=80)
    metric_date: str = Field(min_length=10, max_length=10, pattern=r"^\d{4}-\d{2}-\d{2}$")
    views: int = Field(default=0, ge=0, le=2_000_000_000)
    watch_time_minutes: float = Field(default=0, ge=0, le=1_000_000_000)
    likes: int = Field(default=0, ge=0, le=2_000_000_000)
    comments: int = Field(default=0, ge=0, le=2_000_000_000)
    shares: int = Field(default=0, ge=0, le=2_000_000_000)
    subscribers_gained: int = Field(default=0, ge=-2_000_000_000, le=2_000_000_000)
    revenue_amount: float = Field(default=0, ge=0, le=1_000_000_000)
    revenue_currency: str = Field(default="USD", min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    source: Literal["manual", "youtube_api", "platform_api", "import"] = "manual"
    notes: str = Field(default="", max_length=1000)



@app.get("/api/v1/analytics/optimization")
def analytics_optimization(channel_id: str | None = None):
    if channel_id and not channel_get(channel_id):
        raise HTTPException(status_code=404, detail="Channel not found")
    records = database.channel_performance_records(channel_id=channel_id, limit=500)
    return build_optimization_report(records)

@app.get("/api/v1/analytics/summary")
def analytics_summary(channel_id: str | None = None):
    if channel_id and not channel_get(channel_id):
        raise HTTPException(status_code=404, detail="Channel not found")
    return database.channel_analytics_summary(channel_id)


@app.get("/api/v1/analytics/metrics")
def analytics_metrics(channel_id: str | None = None, limit: int = Query(default=100, ge=1, le=500)):
    if channel_id and not channel_get(channel_id):
        raise HTTPException(status_code=404, detail="Channel not found")
    return database.channel_metric_list(channel_id, limit)


@app.post("/api/v1/analytics/metrics", status_code=201)
def create_analytics_metric(payload: ChannelMetricCreate):
    if not channel_get(payload.channel_id):
        raise HTTPException(status_code=404, detail="Channel not found")
    if payload.publish_job_id:
        from app.database import publish_job_get
        job = publish_job_get(payload.publish_job_id)
        if not job or job["channel_id"] != payload.channel_id:
            raise HTTPException(status_code=422, detail="Publishing job does not belong to this channel")
    try:
        from datetime import date
        date.fromisoformat(payload.metric_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="metric_date must be a valid YYYY-MM-DD date")
    return database.channel_metric_create(payload.model_dump())
