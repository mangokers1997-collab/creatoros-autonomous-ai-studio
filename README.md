# CreatorOS — Autonomous AI Content Studio

A zero-budget-first workspace for planning, producing, reviewing, and publishing faceless content across multiple channels and target markets.

## Current milestone: Foundation API

This repository starts with a small FastAPI backend. It is deliberately provider-neutral: AI research, script generation, media rendering, and platform publishing will be added behind adapters so the project can use free/local tools first.

### Planned modules

- Multi-channel and market configuration
- Research briefs and source tracking
- Content ideas, scripts, storyboards, subtitles, and translations
- Production jobs and render status
- Human review and publishing queue
- Platform adapters (YouTube, Instagram, Facebook, TikTok)
- Analytics ingestion and reporting

## Run locally

Requires Python 3.10+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs for the API explorer.

## Zero-budget operating rules

- Prefer local/open-source models and local FFmpeg rendering.
- Do not assume hosted AI APIs, cloud GPU rendering, or unlimited free quotas.
- Store credentials in environment variables; never commit tokens or OAuth secrets.
- Keep publishing disabled until each platform's OAuth scopes, app review, and account permissions are configured.
- Require human approval before publishing by default.
- Use licensed media and add original research, commentary, or storytelling value.

## Roadmap

1. Foundation API and health endpoint.
2. Persistent database and channel management.
3. Research and content-planning workflow.
4. Script/storyboard generation with pluggable local/hosted providers.
5. Local rendering pipeline (FFmpeg).
6. Platform publishing adapters and analytics.
7. Scheduling, retries, audit logs, and multi-workspace support.

## Status

Early scaffold only. It does not yet generate videos, connect social accounts, or publish posts.
