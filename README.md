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
