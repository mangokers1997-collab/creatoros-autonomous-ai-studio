from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from app.database import (
    content_package_list,
    media_asset_get,
    project_get,
    render_job_get,
    render_job_update,
)

MEDIA_ROOT = Path(os.getenv("CREATOROS_MEDIA_DIR", "media")).resolve()
RENDER_ROOT = Path(os.getenv("CREATOROS_RENDER_DIR", "renders")).resolve()


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _asset_path(asset: dict | None) -> Path | None:
    if not asset:
        return None
    path = (MEDIA_ROOT / asset["stored_name"]).resolve()
    if MEDIA_ROOT not in path.parents or not path.is_file():
        return None
    return path


def run_render_job(job_id: str) -> None:
    job = render_job_get(job_id)
    if not job:
        return
    if not ffmpeg_available():
        render_job_update(job_id, "failed", error="FFmpeg was not found. Install FFmpeg and make sure it is on PATH.")
        return

    project = project_get(job["project_id"])
    packages = content_package_list(job["project_id"])
    package = next((item for item in packages if item["id"] == job["package_id"]), None)
    if not project or not package:
        render_job_update(job_id, "failed", error="Project or content package no longer exists.")
        return

    image = _asset_path(media_asset_get(job["image_asset_id"])) if job["image_asset_id"] else None
    audio = _asset_path(media_asset_get(job["audio_asset_id"])) if job["audio_asset_id"] else None
    if job["image_asset_id"] and not image:
        render_job_update(job_id, "failed", error="Image asset file is missing.")
        return
    if job["audio_asset_id"] and not audio:
        render_job_update(job_id, "failed", error="Audio asset file is missing.")
        return

    RENDER_ROOT.mkdir(parents=True, exist_ok=True)
    output = RENDER_ROOT / f"{job_id}.mp4"
    subtitle = RENDER_ROOT / f"{job_id}.srt"
    subtitle.write_text(package["subtitles_srt"], encoding="utf-8")

    duration = max(8, min(int(job["duration_seconds"]), 180))
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    if image:
        command += ["-loop", "1", "-framerate", "30", "-i", str(image)]
    else:
        command += ["-f", "lavfi", "-i", "color=c=0x151923:s=1080x1920:r=30"]
    if audio:
        command += ["-i", str(audio)]

    # Portrait 9:16 output. A still image is used as the background for this MVP.
    command += [
        "-t", str(duration),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,format=yuv420p",
        "-r", "30",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
    ]
    if audio:
        command += ["-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-b:a", "128k", "-shortest"]
    else:
        command += ["-an"]
    command += ["-movflags", "+faststart", str(output)]

    render_job_update(job_id, "rendering")
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=900, check=False)
        if completed.returncode != 0:
            message = (completed.stderr or "FFmpeg rendering failed.")[-1800:]
            render_job_update(job_id, "failed", error=message)
            return
        render_job_update(job_id, "rendered", output_path=str(output))
    except subprocess.TimeoutExpired:
        render_job_update(job_id, "failed", error="Rendering exceeded the 15-minute limit.")
    except Exception as exc:
        render_job_update(job_id, "failed", error=str(exc))
