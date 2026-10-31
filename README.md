# CreatorOS — Autonomous AI Content Studio

Zero-budget-first workspace for planning, producing, reviewing, and publishing faceless content across multiple channels and target markets.

## Current milestone: Multi-market content strategy and calendar

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

## Scheduled Publishing Worker (opt-in MVP)

A lightweight background worker polls the persistent publishing queue and claims due jobs atomically. It currently supports **YouTube only**, and uploads scheduled videos with **private** visibility by default. A human must approve and schedule each job first. The worker is disabled by default.

### Enable

1. Complete the YouTube OAuth setup above and verify the channel connection.
2. Run a successful manual upload to a private test video first.
3. Set `CREATOROS_PUBLISH_WORKER_ENABLED=true` in the server environment.
4. Set `CREATOROS_PUBLISH_POLL_SECONDS=15` (allowed effective range: 5–300 seconds).
5. Run exactly one API process for a simple local deployment; SQLite atomic claims also reduce duplicate claims if multiple processes are used.
6. Check `GET /api/v1/publishing/worker` for enabled/running status.

When a due item is claimed, its status changes to `publishing`; successful uploads become `published`, and errors become `failed`. Failed jobs can be rescheduled through `POST /api/v1/publishing/jobs/{job_id}/retry` with a future timezone-aware `scheduled_at`.

**Important recovery behavior:** if a worker crashes during upload, the job is marked failed after a stale lease timeout. The remote platform may have received the video even if CreatorOS did not receive the response. Verify the YouTube channel before retrying to avoid duplicate posts. This MVP does not guarantee exactly-once delivery, does not publish to Meta/TikTok, and does not replace monitoring or a durable job queue. Keep the API host running continuously; a sleeping laptop or stopped server cannot publish on schedule.

New endpoints:
- `GET /api/v1/publishing/worker` — worker enabled/running status.
- `POST /api/v1/publishing/jobs/{job_id}/retry` — schedule a failed item for another attempt.

## YouTube OAuth & Manual Upload Adapter (MVP)

The backend contains a YouTube OAuth 2.0 connection flow and a resumable video upload endpoint. OAuth credentials are encrypted with Fernet and saved under `CREATOROS_TOKEN_DIR` (default `./secure_tokens`), which must remain private and outside version control. The signed OAuth state expires after ten minutes.

### Setup

1. In Google Cloud Console, create a project and enable **YouTube Data API v3**.
2. Configure the OAuth consent screen and create an OAuth 2.0 client of type **Web application**.
3. Add the exact `YOUTUBE_REDIRECT_URI` to the authorized redirect URIs.
4. Copy `.env.example` to `.env` and set `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, and `YOUTUBE_REDIRECT_URI`.
5. Generate `CREATOROS_FERNET_KEY` with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
6. Set `CREATOROS_OAUTH_STATE_SECRET` to a random secret of at least 32 characters. Keep both secrets stable across restarts. Set `CREATOROS_TOKEN_DIR=./secure_tokens`.
7. Install dependencies with `pip install -r requirements.txt` and start the API.
8. Create a CreatorOS channel with platform `youtube`. Call `GET /api/v1/oauth/youtube/connect?channel_id=YOUR_CHANNEL_ID`, open the returned authorization URL, and complete Google consent.
9. Check `GET /api/v1/oauth/youtube/status/YOUR_CHANNEL_ID`.
10. Create a publishing draft linked to a completed render, approve it, then call `POST /api/v1/publishing/jobs/YOUR_JOB_ID/upload-youtube` with `{"privacy_status":"private"}`.

### Endpoints

- `GET /api/v1/oauth/youtube/connect?channel_id=...` — begin authorization.
- `GET /api/v1/oauth/youtube/callback` — Google OAuth callback.
- `GET /api/v1/oauth/youtube/status/{channel_id}` — connection status.
- `POST /api/v1/publishing/jobs/{job_id}/upload-youtube` — manually upload a rendered MP4.

Upload visibility defaults to **private**. Use `unlisted` or `public` only when deliberately requested. The adapter uses the `youtube.upload` scope and resumable upload chunks. It does not automatically execute scheduled jobs or publish to Instagram, Facebook, or TikTok. Google may require consent-screen test-user configuration, app verification, and quota eligibility. Review every video, media license, claims, and platform policy before upload.

Never commit `.env`, OAuth client secrets, Fernet keys, state-signing secrets, or the `secure_tokens/` directory.

## Multi-platform Publishing Metadata Validation

Before a post is placed in the publishing queue, CreatorOS can validate basic title and caption lengths against platform-specific limits for YouTube, Instagram, Facebook, and TikTok.

- `POST /api/v1/publishing/validate-metadata` — validate platform, title, and caption metadata.

Example:

```json
{
  "platform": "youtube",
  "title": "A practical budgeting guide",
  "caption": "Three steps to build a realistic monthly budget."
}
```

This is metadata validation only. It does not connect accounts, upload media, guarantee platform acceptance, or replace checking current platform policies.

## Publishing Queue & Scheduling Foundation (MVP)

Create a publishing draft linked to a channel, approved project, and completed rendered video. Drafts enter `awaiting_approval`; a human must approve them with an ISO-8601 future timestamp that includes a timezone. The queue persists schedule metadata and supports filtering, inspection, approval, and cancellation. This release does **not** upload to social platforms yet; adapter status reports the missing OAuth/app-review prerequisites honestly.

- `POST /api/v1/publishing/drafts` — create a draft queue item.
- `GET /api/v1/publishing/jobs` — list queue items; optional `channel_id` and `status` filters.
- `GET /api/v1/publishing/jobs/{job_id}` — inspect one item.
- `POST /api/v1/publishing/jobs/{job_id}/approve` — approve and schedule with `scheduled_at`, e.g. `2026-11-01T10:00:00+07:00`.
- `POST /api/v1/publishing/jobs/{job_id}/cancel` — cancel an unprocessed item.
- `GET /api/v1/publishing/adapters` — inspect platform integration readiness.

A scheduled item is a persisted schedule, not an automatic upload. Platform upload adapters, OAuth consent/token storage, token refresh, background scheduler/worker, and platform review are still future work. Never store secrets in Git; configure them through environment variables or a secure secret manager.

## Production Automation & Batch Pipeline (MVP)

Turn saved strategy calendar entries into content projects and draft packages in sequential batches of up to five. Each item creates a project, generates its script/storyboard/subtitles package, and can optionally synthesize local voice with Piper and render a portrait MP4 with FFmpeg. If a requested local dependency is unavailable, the item is marked failed with a diagnostic; retry it after fixing the setup. Rendering without supplied images uses the renderer's generated background. The pipeline never publishes automatically.

- `POST /api/v1/production-batches` — queue up to five planned items from a strategy.
- `GET /api/v1/production-batches` — list batches.
- `GET /api/v1/production-batches/{batch_id}` — inspect batch and item statuses.
- `POST /api/v1/production-batch-items/{item_id}/retry` — retry a failed item.

Example request:

```json
{
  "strategy_id": "YOUR_STRATEGY_ID",
  "max_items": 5,
  "generate_voice": true,
  "render_video": true,
  "duration_seconds": 48
}
```

The batch worker runs sequentially through FastAPI background tasks, suitable for a small local MVP only. It is not a durable distributed queue: a process restart can interrupt work. Use a dedicated worker/queue such as RQ or Celery before production-scale runs. Voice and video depend on Piper plus a licensed voice model, and FFmpeg with the subtitles/libass filter. Human review remains mandatory before upload.

## AI Content Strategy Engine (30-day planner)

Generate and persist a 1–90 day content calendar using saved trend items and saved intelligence reports, with an evergreen fallback when no research data exists. The MVP creates up to five short-form content briefs per day, each with a topic, angle, title, and localized hook. It can associate a plan with a channel. It is a deterministic planning engine, not an LLM or a performance prediction system.

- `POST /api/v1/strategies/generate` — generate and save a calendar.
- `GET /api/v1/strategies` — list saved plans.
- `GET /api/v1/strategies/{plan_id}` — read a plan and all calendar items.
- `PATCH /api/v1/strategy-items/{item_id}` — update an item's workflow status and optionally link a project.

Example request:

```json
{
  "market": "US",
  "niche": "personal finance",
  "language": "en",
  "start_date": "2026-11-01",
  "days": 30,
  "videos_per_day": 1
}
```

Supported strategy languages include English, Indonesian, Japanese, and Arabic. Topic sources are labeled in the plan summary. Validate all ideas and claims before production; the calendar does not promise reach, monetization, or revenue.

## Competitor & Keyword Intelligence (MVP)

The intelligence endpoint clusters seed keywords with saved Google Trends titles and creates a prioritized idea list using transparent text heuristics. It can optionally query public YouTube video search results by market when `YOUTUBE_DATA_API_KEY` is configured. No API key is required for clustering saved trends and seed terms.

- `POST /api/v1/intelligence/analyze` — create and save an intelligence report.
- `GET /api/v1/intelligence/reports?market=US&niche=personal%20finance` — list saved reports.

Example request:

```json
{
  "market": "US",
  "niche": "personal finance",
  "language": "en",
  "seed_keywords": ["budgeting", "saving money", "credit score"],
  "competitor_queries": ["personal finance for beginners", "budgeting tips"]
}
```

Set `YOUTUBE_DATA_API_KEY` in the server environment to enable optional public video search. The YouTube Data API has quota limits; keep query counts small and never commit the key. Search results are samples, not a complete channel audit. This MVP does not calculate keyword volume, difficulty, CPM, RPM, or estimated revenue. Scores are heuristic prioritization aids, not market facts.

## Content Research Automation (free RSS MVP)

CreatorOS can fetch the public Google Trends Trending Now RSS feed for supported markets (US, GB, CA, AU, JP, AE, IN, ID), parse trend titles, approximate traffic labels, publication dates and source links, then persist results in SQLite. A lightweight heuristic score combines the traffic bucket with optional niche/keyword text matches. This is a prioritization hint, not a search-volume metric, virality prediction, or ad-revenue estimate.

- `GET /api/v1/trends/markets` — list supported market codes.
- `POST /api/v1/trends/refresh` — fetch and save a market feed. JSON example: `{"market":"US","niche":"personal finance","keywords":["budget","saving"]}`.
- `GET /api/v1/trends?market=US&niche=personal%20finance` — read saved trend items.

This RSS source is public and requires no API key, but it is not a guaranteed uptime service. Fetches require outbound internet access from the CreatorOS host. Keep refresh frequency modest and cache results; do not scrape restricted pages or infer private user data. Google Trends RSS supplies only a limited set of currently trending searches and approximate traffic labels.

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

Render requests accept `package_id`, optional `image_asset_id`, optional `audio_asset_id`, `duration_seconds` (8–180), and optional `scene_asset_ids`. If FFmpeg is missing, the render job is marked failed with an installation hint. The API uses FastAPI background tasks; for sustained production workloads, replace this with a dedicated worker queue.

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

## Visual Story Engine (multi-scene MVP)

The renderer now creates one short clip per storyboard scene, applies a gentle Ken Burns-style zoom, overlays each scene's narration/visual direction, concatenates the clips, and burns scene-timed SRT captions into the final portrait MP4. Upload one image per scene with `scene_asset_ids`; if omitted, the general `image_asset_id` is reused for every scene, or generated dark backgrounds are used. A storyboard scene is represented by the saved content package.

Render request fields: `package_id`, optional `image_asset_id`, optional `audio_asset_id`, `duration_seconds`, and optional `scene_asset_ids` (one ID or null per storyboard scene). Up to 12 scenes are supported. For burned-in subtitles, FFmpeg must include the subtitles/libass filter. Set `CREATOROS_FONT_FILE` to a font file path if a suitable font is not available on the host. This is motion editing from supplied still images, not generative AI video or character motion control.

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
| GET | `/api/v1/trends/markets` | List supported trend markets |
| POST | `/api/v1/trends/refresh` | Fetch and store a public RSS trend feed |
| GET | `/api/v1/trends` | List stored trend signals |
| POST | `/api/v1/intelligence/analyze` | Cluster keywords and optionally search public YouTube videos |
| GET | `/api/v1/intelligence/reports` | List saved intelligence reports |
| POST | `/api/v1/strategies/generate` | Generate and save a content calendar |
| GET | `/api/v1/strategies` | List strategy plans |
| GET | `/api/v1/strategies/{plan_id}` | Get plan and calendar items |
| PATCH | `/api/v1/strategy-items/{item_id}` | Update a calendar item's status |
| POST | `/api/v1/production-batches` | Queue up to five strategy items for production |
| GET | `/api/v1/production-batches` | List production batches |
| GET | `/api/v1/production-batches/{batch_id}` | Get batch progress and item details |
| POST | `/api/v1/production-batch-items/{item_id}/retry` | Retry a failed production item |
| POST | `/api/v1/publishing/validate-metadata` | Validate title and caption lengths per platform |
| POST | `/api/v1/publishing/drafts` | Create a publishing draft linked to a rendered video |
| GET | `/api/v1/publishing/jobs` | List publishing queue items |
| GET | `/api/v1/publishing/jobs/{job_id}` | Get a publishing job |
| POST | `/api/v1/publishing/jobs/{job_id}/approve` | Approve and schedule a publishing job |
| POST | `/api/v1/publishing/jobs/{job_id}/cancel` | Cancel an unprocessed publishing job |
| GET | `/api/v1/publishing/adapters` | Check platform adapter readiness |
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
6. [x] Local FFmpeg portrait renderer with multi-scene zoom, text overlays, and burned-in captions.
7. [ ] Platform publishing adapters and analytics.
8. [ ] Scheduling, retries, audit logs, and multi-workspace support.

## Current limitations

This is an early backend. LLM-based generation, keyword volume, difficulty, and advanced competitor enrichment, AI-generated footage and character motion control, social account connections, scheduling, and actual publishing are not implemented yet.
