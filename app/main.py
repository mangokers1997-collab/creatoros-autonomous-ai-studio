from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Literal
from app.database import init_db, channel_create, channel_list, channel_delete
from app.database import project_create, project_list, project_get, project_update_status
from app.database import research_create, research_list, research_get, research_source_create
from app.database import content_package_list, media_asset_create, media_asset_get, media_asset_list
from app.database import render_job_create, render_job_get, render_job_list
from app.database import voice_job_create, voice_job_get, voice_job_list
from app.content_engine import generate_content_package
from app.renderer import MEDIA_ROOT, RENDER_ROOT, ffmpeg_available, run_render_job
from app.voice_engine import piper_available, run_voice_job

ChannelPlatform = Literal["youtube", "instagram", "facebook", "tiktok"]
ProjectStatus = Literal["idea", "research", "script", "storyboard", "ready_for_review", "approved", "rendering", "rendered", "scheduled", "published", "failed"]


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="CreatorOS API",
    description="Zero-budget-first API foundation for a multi-channel content studio.",
    version="0.6.0",
    lifespan=lifespan,
)


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


class ResearchSourceCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    url: str = Field(default="", max_length=1000)
    source_type: Literal["article", "video", "report", "forum", "other"] = "article"
    observation: str = Field(default="", max_length=2000)


@app.get("/")
def root():
    return {"name": "CreatorOS API", "version": "0.3.0", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok", "service": "creatoros-api", "version": "0.6.0"}


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


@app.get("/api/v1/system/status")
def system_status():
    return {
        "phase": "local-voice-and-video-production",
        "database": "sqlite",
        "ai_provider": "local_piper_available" if piper_available() else "local_piper_not_configured",
        "render_engine": "ffmpeg_available" if ffmpeg_available() else "ffmpeg_not_installed",
        "publishing": "disabled",
        "human_approval_required": True,
    }
