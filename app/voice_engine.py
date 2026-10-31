from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

from app.database import (
    content_package_list,
    media_asset_create,
    project_get,
    voice_job_get,
    voice_job_update,
)

MEDIA_ROOT = Path(os.getenv("CREATOROS_MEDIA_DIR", "media")).resolve()
PIPER_BIN = os.getenv("PIPER_BIN", "piper")
PIPER_MODEL = os.getenv("PIPER_MODEL", "")


def piper_available() -> bool:
    return bool(PIPER_MODEL and Path(PIPER_MODEL).is_file() and shutil.which(PIPER_BIN))


def split_narration(text: str) -> list[str]:
    return [part.strip() for part in text.replace("\r", "").splitlines() if part.strip()]


def _srt_time(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def build_srt(chunks: list[str], durations: list[float], gap: float = 0.18) -> str:
    entries = []
    cursor = 0.0
    for index, (chunk, duration) in enumerate(zip(chunks, durations), start=1):
        start = cursor
        end = start + max(0.05, duration)
        entries.extend([str(index), f"{_srt_time(start)} --> {_srt_time(end)}", chunk, ""])
        cursor = end + gap
    return "\n".join(entries)


def _concat_wav(files: list[Path], output: Path) -> list[float]:
    durations = []
    params = None
    with wave.open(str(output), "wb") as target:
        for path in files:
            with wave.open(str(path), "rb") as source:
                current = source.getparams()
                if params is None:
                    params = current
                    target.setparams(params)
                elif (current.nchannels, current.sampwidth, current.framerate, current.comptype) != (
                    params.nchannels, params.sampwidth, params.framerate, params.comptype
                ):
                    raise RuntimeError("Piper generated inconsistent WAV formats.")
                frames = source.readframes(source.getnframes())
                target.writeframes(frames)
                durations.append(source.getnframes() / float(source.getframerate()))
                silence_frames = int(source.getframerate() * 0.18)
                target.writeframes(b"\x00" * silence_frames * source.getnchannels() * source.getsampwidth())
    return durations


def run_voice_job(job_id: str) -> None:
    job = voice_job_get(job_id)
    if not job:
        return
    if not piper_available():
        voice_job_update(
            job_id, "failed",
            error="Piper or PIPER_MODEL is not configured. Install Piper and set PIPER_MODEL to a downloaded .onnx voice model.",
        )
        return
    project = project_get(job["project_id"])
    packages = content_package_list(job["project_id"])
    package = next((item for item in packages if item["id"] == job["package_id"]), None)
    if not project or not package:
        voice_job_update(job_id, "failed", error="Project or content package not found.")
        return

    chunks = split_narration(package["script"])
    if not chunks:
        voice_job_update(job_id, "failed", error="The content package has no narration text.")
        return

    voice_job_update(job_id, "generating")
    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    final_path = MEDIA_ROOT / f"voice-{job_id}.wav"
    try:
        with tempfile.TemporaryDirectory(prefix="creatoros-piper-") as temp_dir:
            temp = Path(temp_dir)
            segment_files = []
            for index, chunk in enumerate(chunks):
                segment = temp / f"segment-{index:04d}.wav"
                command = [PIPER_BIN, "--model", PIPER_MODEL, "--output_file", str(segment)]
                completed = subprocess.run(
                    command, input=chunk, text=True, capture_output=True, timeout=180, check=False
                )
                if completed.returncode != 0 or not segment.is_file():
                    raise RuntimeError((completed.stderr or "Piper failed to synthesize narration.")[-1600:])
                segment_files.append(segment)
            durations = _concat_wav(segment_files, final_path)
        subtitles = build_srt(chunks, durations)
        asset = media_asset_create({
            "original_name": f"creatoros-voice-{job_id}.wav",
            "stored_name": final_path.name,
            "media_type": "audio",
            "mime_type": "audio/wav",
            "size_bytes": final_path.stat().st_size,
        })
        voice_job_update(job_id, "ready", audio_asset_id=asset["id"], subtitles_srt=subtitles)
    except subprocess.TimeoutExpired:
        final_path.unlink(missing_ok=True)
        voice_job_update(job_id, "failed", error="Piper synthesis timed out.")
    except Exception as exc:
        final_path.unlink(missing_ok=True)
        voice_job_update(job_id, "failed", error=str(exc))
