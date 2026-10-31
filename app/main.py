from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Literal
from uuid import uuid4

from app.database import init_db, channel_create, channel_list, channel_delete
from app.database import project_create, project_list, project_get, project_update_status
from app.database import research_create, research_list, research_get, research_source_create
from app.database import content_package_list
from app.content_engine import generate_content_package

ChannelPlatform = Literal["youtube", "instagram", "facebook", "tiktok"]
ProjectStatus = Literal["idea", "research", "script", "storyboard", "ready_for_review", "approved", "rendering", "rendered", "scheduled", "published", "failed"]


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="CreatorOS API",
    description="Zero-budget-first API foundation for a multi-channel content studio.",
    version="0.4.0",
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
    return {"status": "ok", "service": "creatoros-api", "version": "0.4.0"}


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


@app.get("/api/v1/system/status")
def system_status():
    return {
        "phase": "content-intelligence-engine",
        "database": "sqlite",
        "ai_provider": "not_configured",
        "render_engine": "not_configured",
        "publishing": "disabled",
        "human_approval_required": True,
    }
