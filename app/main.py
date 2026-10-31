from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import Literal
from uuid import uuid4

app = FastAPI(
    title="CreatorOS API",
    description="Zero-budget-first API foundation for a multi-channel content studio.",
    version="0.1.0",
)

ChannelPlatform = Literal["youtube", "instagram", "facebook", "tiktok"]


class ChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    platform: ChannelPlatform
    target_market: str = Field(default="US", min_length=2, max_length=40)
    language: str = Field(default="en", min_length=2, max_length=12)
    niche: str = Field(default="general", max_length=80)


class Channel(ChannelCreate):
    id: str


# Temporary in-memory store; replaced by SQLite persistence in the next milestone.
channels: dict[str, Channel] = {}


@app.get("/")
def root():
    return {"name": "CreatorOS API", "version": "0.1.0", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok", "service": "creatoros-api"}


@app.get("/api/v1/channels", response_model=list[Channel])
def list_channels():
    return list(channels.values())


@app.post("/api/v1/channels", response_model=Channel, status_code=201)
def create_channel(payload: ChannelCreate):
    channel = Channel(id=str(uuid4()), **payload.model_dump())
    channels[channel.id] = channel
    return channel


@app.delete("/api/v1/channels/{channel_id}")
def delete_channel(channel_id: str):
    removed = channels.pop(channel_id, None)
    return {"deleted": removed is not None, "id": channel_id}


@app.get("/api/v1/system/status")
def system_status():
    return {
        "phase": "foundation",
        "database": "in-memory (temporary)",
        "ai_provider": "not_configured",
        "render_engine": "not_configured",
        "publishing": "disabled",
        "human_approval_required": True,
    }
