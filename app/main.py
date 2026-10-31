from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Literal
from uuid import uuid4

from app.database import init_db, channel_create, channel_list, channel_delete
from app.database import project_create, project_list, project_get, project_update_status

ChannelPlatform = Literal["youtube", "instagram", "facebook", "tiktok"]
ProjectStatus = Literal["idea", "research", "script", "storyboard", "ready_for_review", "approved", "rendering", "rendered", "scheduled", "published", "failed"]


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="CreatorOS API",
    description="Zero-budget-first API foundation for a multi-channel content studio.",
    version="0.2.0",
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


@app.get("/")
def root():
    return {"name": "CreatorOS API", "version": "0.2.0", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok", "service": "creatoros-api", "version": "0.2.0"}


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


@app.get("/api/v1/system/status")
def system_status():
    return {
        "phase": "database-and-content-workflow",
        "database": "sqlite",
        "ai_provider": "not_configured",
        "render_engine": "not_configured",
        "publishing": "disabled",
        "human_approval_required": True,
    }
