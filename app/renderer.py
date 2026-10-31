from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.database import (
    content_package_list, media_asset_get, project_get, render_job_get,
    render_job_update, render_scene_assets_list,
)

MEDIA_ROOT = Path(os.getenv("CREATOROS_MEDIA_DIR", "media")).resolve()
RENDER_ROOT = Path(os.getenv("CREATOROS_RENDER_DIR", "renders")).resolve()
FONT_FILE = os.getenv("CREATOROS_FONT_FILE", "")


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _asset_path(asset: dict | None) -> Path | None:
    if not asset:
        return None
    path = (MEDIA_ROOT / asset["stored_name"]).resolve()
    if MEDIA_ROOT not in path.parents or not path.is_file():
        return None
    return path


def _srt_time(seconds: float) -> str:
    millis = round(seconds * 1000)
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _make_srt(scenes: list[dict], duration: int) -> str:
    per_scene = duration / max(1, len(scenes))
    rows = []
    for index, scene in enumerate(scenes, 1):
        caption = (scene.get("caption") or "").strip()
        if not caption:
            continue
        start = (index - 1) * per_scene
        end = index * per_scene
        rows.extend([str(len(rows) // 4 + 1), f"{_srt_time(start)} --> {_srt_time(end)}", caption, ""])
    return "\n".join(rows)


def _escape_filter_path(path: Path) -> str:
    value = str(path.resolve()).replace("\\", "/")
    return value.replace(":", r"\\:").replace("'", r"\\'")


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

    scenes = render_scene_assets_list(job_id)
    if not scenes:
        scenes = [{"image_asset_id": job.get("image_asset_id"), "caption": "", "visual_direction": ""}]
    scene_images = []
    for scene in scenes:
        image = _asset_path(media_asset_get(scene["image_asset_id"])) if scene.get("image_asset_id") else None
        if scene.get("image_asset_id") and not image:
            render_job_update(job_id, "failed", error="A storyboard image asset file is missing.")
            return
        scene_images.append(image)
    audio = _asset_path(media_asset_get(job["audio_asset_id"])) if job.get("audio_asset_id") else None
    if job.get("audio_asset_id") and not audio:
        render_job_update(job_id, "failed", error="Audio asset file is missing.")
        return

    RENDER_ROOT.mkdir(parents=True, exist_ok=True)
    output = RENDER_ROOT / f"{job_id}.mp4"
    duration = max(8, min(int(job["duration_seconds"]), 180))
    render_job_update(job_id, "rendering")

    try:
        with tempfile.TemporaryDirectory(prefix="creatoros-story-") as temp_dir:
            temp = Path(temp_dir)
            clip_paths = []
            per_scene = duration / max(1, len(scenes))
            for index, (scene, image) in enumerate(zip(scenes, scene_images)):
                clip = temp / f"scene-{index:02d}.mp4"
                textfile = temp / f"scene-{index:02d}.txt"
                label = (scene.get("caption") or scene.get("visual_direction") or f"Scene {index + 1}").strip()
                textfile.write_text(label[:450], encoding="utf-8")
                seconds = max(1.0, per_scene)
                frames = max(30, round(seconds * 30))
                command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
                if image:
                    command += ["-loop", "1", "-framerate", "30", "-t", str(seconds), "-i", str(image)]
                else:
                    command += ["-f", "lavfi", "-i", f"color=c=0x151923:s=1080x1920:r=30:d={seconds}"]
                font_option = f":fontfile='{_escape_filter_path(Path(FONT_FILE))}'" if FONT_FILE and Path(FONT_FILE).is_file() else ""
                draw = (
                    f"scale=1200:2134:force_original_aspect_ratio=increase,"
                    f"crop=1200:2134,zoompan=z='min(zoom+0.0012,1.10)':d={frames}:s=1080x1920:fps=30,"
                    f"drawtext=textfile='{_escape_filter_path(textfile)}'{font_option}:"
                    "fontcolor=white:fontsize=48:line_spacing=12:"
                    "box=1:boxcolor=black@0.55:boxborderw=24:"
                    "x=(w-text_w)/2:y=h*0.72,format=yuv420p"
                )
                command += [
                    "-vf", draw, "-t", str(seconds), "-r", "30",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
                    "-an", str(clip),
                ]
                completed = subprocess.run(command, capture_output=True, text=True, timeout=600, check=False)
                if completed.returncode != 0:
                    raise RuntimeError((completed.stderr or "FFmpeg scene render failed.")[-1600:])
                clip_paths.append(clip)

            concat_file = temp / "concat.txt"
            concat_file.write_text("".join(f"file '{path.as_posix()}'\n" for path in clip_paths), encoding="utf-8")
            subtitle_file = temp / "captions.srt"
            subtitle_file.write_text(_make_srt(scenes, duration), encoding="utf-8")
            command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                       "-f", "concat", "-safe", "0", "-i", str(concat_file)]
            if audio:
                command += ["-i", str(audio)]
            filters = f"subtitles='{_escape_filter_path(subtitle_file)}':force_style='FontName=Arial,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H80000000,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=110'"
            command += ["-vf", filters, "-t", str(duration), "-c:v", "libx264", "-preset", "veryfast", "-crf", "24"]
            if audio:
                command += ["-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-b:a", "128k", "-shortest"]
            else:
                command += ["-an"]
            command += ["-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=900, check=False)
            if completed.returncode != 0:
                raise RuntimeError((completed.stderr or "FFmpeg final assembly failed. Check FFmpeg libass support.")[-1800:])
        render_job_update(job_id, "rendered", output_path=str(output))
    except subprocess.TimeoutExpired:
        render_job_update(job_id, "failed", error="Rendering exceeded the time limit.")
    except Exception as exc:
        render_job_update(job_id, "failed", error=str(exc))
