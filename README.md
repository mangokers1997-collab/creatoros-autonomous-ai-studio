# CreatorOS — Autonomous AI Content Studio

Zero-budget-first workspace for planning, producing, reviewing, and publishing faceless content across multiple channels and target markets.

## Current milestone: Persistent data + content workflow API

The FastAPI backend now includes SQLite persistence, channel management, content project creation, project filtering, and workflow status updates.

### Run locally

Requires Python 3.10+.

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs for the interactive API explorer.

Set `CREATOROS_DB_PATH` to change the SQLite database file location. The default is `creatoros.db` in the project directory.

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Service health |
| GET | `/api/v1/system/status` | Integration status |
| GET / POST | `/api/v1/channels` | List or create channels |
| DELETE | `/api/v1/channels/{id}` | Delete a channel |
| GET / POST | `/api/v1/projects` | List or create content projects |
| GET | `/api/v1/projects/{id}` | Get one project |
| PATCH | `/api/v1/projects/{id}/status` | Move a project through workflow states |

Project workflow states: `idea`, `research`, `script`, `storyboard`, `ready_for_review`, `approved`, `rendering`, `rendered`, `scheduled`, `published`, `failed`.

## Zero-budget operating rules

- Prefer local/open-source models and local FFmpeg rendering.
- Do not assume hosted AI APIs, cloud GPU rendering, or unlimited free quotas.
- Store credentials in environment variables; never commit tokens or OAuth secrets.
- Publishing stays disabled until platform OAuth scopes, app review, and account permissions are configured.
- Human approval is required before publishing by default.
- Use licensed media and add original research, commentary, or storytelling value.

## Roadmap

1. [x] API foundation and health endpoint.
2. [x] SQLite persistence and channel management.
3. [x] Content project workflow and status tracking.
4. [ ] Research briefs and source tracking.
5. [ ] Script/storyboard generation with pluggable local/hosted providers.
6. [ ] Local rendering pipeline (FFmpeg).
7. [ ] Platform publishing adapters and analytics.
8. [ ] Scheduling, retries, audit logs, and multi-workspace support.

## Current limitations

This is an early backend. AI generation, live trend research, video rendering, social account connections, scheduling, and actual publishing are not implemented yet.
