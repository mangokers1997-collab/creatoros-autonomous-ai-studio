"""Publishing readiness gate for standard CreatorOS render jobs."""
from __future__ import annotations

import shutil
import subprocess
import json
from pathlib import Path

from app.database import channel_get, project_get, render_job_get, publish_job_list
from app.platform_validation import validate_publish_metadata


def inspect_publish_readiness(channel_id: str, project_id: str, render_job_id: str,
                              title: str, caption: str) -> dict:
    checks = []

    def add(name: str, passed: bool, detail: str, required: bool = True) -> None:
        checks.append({"name": name, "passed": bool(passed),
                       "required": required, "detail": str(detail)[:500]})

    channel = channel_get(channel_id)
    project = project_get(project_id)
    render = render_job_get(render_job_id)
    add("Channel exists", bool(channel), "Channel found." if channel else "Selected channel does not exist.")
    add("Project exists", bool(project), "Project found." if project else "Project does not exist.")
    add("Project-channel match", bool(channel and project and project.get("channel_id") == channel_id),
        "Project belongs to selected channel." if channel and project and project.get("channel_id") == channel_id else "Project must belong to selected channel.")
    add("Project approved", bool(project and project.get("status") in {"approved", "rendered"}),
        "Project is approved for publishing." if project and project.get("status") in {"approved", "rendered"} else "Project must be approved or rendered.")
    add("Render belongs to project", bool(render and render.get("project_id") == project_id),
        "Render belongs to selected project." if render and render.get("project_id") == project_id else "Render is missing or belongs to another project.")
    add("Render completed", bool(render and render.get("status") == "rendered"),
        "Render status is rendered." if render and render.get("status") == "rendered" else "Render must finish successfully.")
    metadata = validate_publish_metadata(channel.get("platform") if channel else "", title, caption)
    add("Publishing metadata", metadata["valid"], "; ".join(metadata["errors"]) or "Title and caption meet platform limits.")
    path = Path(render.get("output_path", "")) if render and render.get("output_path") else None
    file_ok = bool(path and path.is_file() and path.stat().st_size > 1024)
    add("Video file", file_ok, f"{path.stat().st_size} bytes." if file_ok else "Rendered video file is missing or too small.")
    if file_ok:
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            add("Media integrity", False, "ffprobe is unavailable; install FFmpeg including ffprobe.")
        else:
            try:
                probe = subprocess.run(
                    [ffprobe, "-v", "error", "-show_entries",
                     "format=duration,format_name:stream=codec_type,codec_name,width,height",
                     "-of", "json", str(path)],
                    capture_output=True, text=True, timeout=25, check=False,
                )
                data = json.loads(probe.stdout or "{}") if probe.returncode == 0 else {}
                streams = data.get("streams", [])
                video = next((x for x in streams if x.get("codec_type") == "video"), None)
                audio = next((x for x in streams if x.get("codec_type") == "audio"), None)
                duration = float((data.get("format") or {}).get("duration") or 0)
                add("Readable video stream", bool(video and duration > 0),
                    f"{duration:.1f}s; {video.get('codec_name', 'unknown') if video else 'no video stream'}.")
                add("Audio track", bool(audio), f"{audio.get('codec_name')} audio found." if audio else "No audio track detected.")
                add("Portrait dimensions", bool(video and video.get("width", 0) > video.get("height", 0) is False),
                    f"{video.get('width')}×{video.get('height')}" if video else "Video stream missing.", required=False)
            except (subprocess.TimeoutExpired, ValueError, OSError) as exc:
                add("Media integrity", False, f"ffprobe failed: {str(exc)[:300]}")
    else:
        add("Media integrity", False, "Cannot inspect media because the video file is unavailable.")
    recent = publish_job_list(channel_id=channel_id, limit=100) if channel else []
    duplicate = any(
        row.get("title", "").strip().casefold() == title.strip().casefold()
        and row.get("project_id") != project_id
        for row in recent
    )
    add("Duplicate title check", not duplicate,
        "No exact title match in recent channel drafts." if not duplicate else "An identical title already exists in recent drafts.",
        required=False)
    passed_required = all(x["passed"] for x in checks if x["required"])
    score = round(100 * sum(x["passed"] for x in checks) / max(1, len(checks)))
    return {
        "passed": passed_required,
        "status": "ready_for_human_review" if passed_required else "blocked",
        "score": score,
        "checks": checks,
        "warnings": [x["name"] for x in checks if not x["passed"] and not x["required"]],
        "human_review_required": True,
        "limitations": [
            "Automated checks cannot verify factual accuracy, copyright or asset licences, visual storytelling, audience suitability, or whether subtitles are readable.",
            "A passing result is not permission to publish automatically. A human must preview and approve the content.",
        ],
    }
