# CreatorOS — Autonomous AI Content Studio

Zero-budget-first workspace for planning, producing, reviewing, and publishing faceless content across multiple channels and target markets.

## Current milestone: Local voice and video production foundation

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

## Research workspace

Research briefs are stored by topic, niche, target market, language, audience, goal, seed keywords, competitor references, and notes. Source records can be attached with a title, optional URL, source type, and observation. This is a structured research notebook; it does not yet fetch live trends or scrape competitor channels.

## Content Intelligence Engine (template-based MVP)

Generate a first-draft content package for an existing project. The engine creates a hook, title, description, narration script, five-scene storyboard, SRT subtitles, and hashtag suggestions. It currently uses deterministic templates in English and Indonesian; it is not an LLM, live research service, translation engine, or fact-checker. Review and customize every draft before publishing.

- `POST /api/v1/projects/{id}/generate-package` — generate and store a package.
- `GET /api/v1/projects/{id}/packages` — list saved packages for a project.

## Local Video Production Engine (MVP)

The rendering API assembles a portrait 1080x1920 MP4 from one still background image (or a generated dark background) and an optional uploaded voiceover. It also writes the package's SRT subtitle file beside the MP4. The subtitle file is currently a sidecar and is not burned into the video. This first renderer does not yet create motion graphics, multiple storyboard scenes, or AI-generated footage.

Install FFmpeg separately and ensure the `ffmpeg` executable is available on PATH. FFmpeg is a system dependency and is not installed by pip. Upload media through the API; JPG, PNG, and WEBP images and MP3, WAV, AAC, M4A/MP4 audio, and OGG audio are supported up to 20 MB per file.

- `POST /api/v1/assets/upload` — upload an image or voiceover file (multipart form field: `file`).
- `GET /api/v1/assets` — list uploaded media assets.
- `POST /api/v1/projects/{id}/render` — queue a render using a saved package.
- `GET /api/v1/renders/{job_id}` — check render status.
- `GET /api/v1/renders/{job_id}/download` — download completed MP4.

Render requests accept `package_id`, optional `image_asset_id`, optional `audio_asset_id`, and `duration_seconds` (8–180). If FFmpeg is missing, the render job is marked failed with an installation hint. The API uses FastAPI background tasks; for sustained production workloads, replace this with a dedicated worker queue.

## Local AI Voice & Timed Subtitle Engine

CreatorOS can generate narration locally using Piper TTS. Install Piper, download a compatible ONNX voice model, and configure environment variables:

- `PIPER_BIN` — Piper executable name or path (default: `piper`).
- `PIPER_MODEL` — absolute path to the downloaded `.onnx` voice model.

This is offline after the executable and model are installed. Voice availability and quality depend on the selected model; Indonesian and English require compatible models. Models are not bundled in this repository and must be downloaded separately. Check each model's license before commercial use.

- `POST /api/v1/projects/{project_id}/packages/{package_id}/voice` — queue local narration synthesis.
- `GET /api/v1/voice-jobs/{job_id}` — check synthesis status.
- `GET /api/v1/voice-jobs/{job_id}/audio` — download generated WAV.
- `GET /api/v1/voice-jobs/{job_id}/subtitles` — download SRT subtitles timed from the duration of each generated narration chunk.

The engine synthesizes paragraph-sized chunks and measures their actual WAV durations for subtitle timing. This is chunk-level timing, not word-level forced alignment. The service reports a failed job if Piper or its model is not configured; it does not silently call a paid cloud API.

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
| POST | `/api/v1/projects/{id}/generate-package` | Generate a first-draft content package |
| GET | `/api/v1/projects/{id}/packages` | List saved content packages |
| GET / POST | `/api/v1/research` | List or create research briefs |
| GET | `/api/v1/research/{id}` | Get a research brief with its sources |
| POST | `/api/v1/research/{id}/sources` | Attach a source and observation |

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
4. [x] Research briefs and source tracking.
5. [x] First-draft script/storyboard/subtitle generation (template-based MVP).
6. [x] Basic local FFmpeg portrait renderer (single background + optional voiceover).
7. [ ] Platform publishing adapters and analytics.
8. [ ] Scheduling, retries, audit logs, and multi-workspace support.

## Current limitations

This is an early backend. LLM-based generation, live trend retrieval, multi-scene motion editing, social account connections, scheduling, and actual publishing are not implemented yet.
