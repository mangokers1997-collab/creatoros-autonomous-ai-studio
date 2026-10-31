from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from secrets import compare_digest
from urllib.parse import urlencode

from cryptography.fernet import Fernet, InvalidToken
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import Flow

from app.database import channel_get, publish_job_get, publish_job_update, render_job_get
from app.renderer import RENDER_ROOT

YOUTUBE_SCOPE = "https://www.googleapis.com/auth/youtube.upload"


def _config() -> tuple[str, str, str, str]:
    values = (
        os.getenv("YOUTUBE_CLIENT_ID", "").strip(),
        os.getenv("YOUTUBE_CLIENT_SECRET", "").strip(),
        os.getenv("YOUTUBE_REDIRECT_URI", "").strip(),
        os.getenv("CREATOROS_FERNET_KEY", "").strip(),
    )
    if not all(values):
        raise RuntimeError("Configure YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REDIRECT_URI and CREATOROS_FERNET_KEY.")
    return values


def _cipher() -> Fernet:
    return Fernet(_config()[3].encode("ascii"))


def _token_dir() -> Path:
    root = Path(os.getenv("CREATOROS_TOKEN_DIR", "./secure_tokens")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _token_path(channel_id: str) -> Path:
    if not channel_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in channel_id):
        raise ValueError("Invalid channel identifier.")
    return _token_dir() / f"youtube_{channel_id}.token"


def _flow(state: str | None = None) -> Flow:
    client_id, client_secret, redirect_uri, _ = _config()
    config = {"web": {
        "client_id": client_id, "client_secret": client_secret,
        "redirect_uris": [redirect_uri],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }}
    flow = Flow.from_client_config(config, scopes=[YOUTUBE_SCOPE], state=state)
    flow.redirect_uri = redirect_uri
    return flow


def _state_secret() -> bytes:
    secret = os.getenv("CREATOROS_OAUTH_STATE_SECRET", "").encode("utf-8")
    if len(secret) < 32:
        raise RuntimeError("CREATOROS_OAUTH_STATE_SECRET must contain at least 32 characters.")
    return secret


def _make_state(channel_id: str) -> str:
    payload = json.dumps({"channel_id": channel_id, "expires": int(time.time()) + 600}, separators=(",", ":")).encode()
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    import hmac
    signature = hmac.new(_state_secret(), encoded.encode(), "sha256").hexdigest()
    return f"{encoded}.{signature}"


def _read_state(state: str) -> str:
    import hmac
    try:
        encoded, signature = state.split(".", 1)
        expected = hmac.new(_state_secret(), encoded.encode(), "sha256").hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("OAuth state signature is invalid.")
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if int(payload["expires"]) < int(time.time()):
            raise ValueError("OAuth state has expired. Start the connection again.")
        return str(payload["channel_id"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("OAuth state is invalid.") from exc


def start_youtube_connection(channel_id: str) -> dict:
    channel = channel_get(channel_id)
    if not channel or channel.get("platform") != "youtube":
        raise ValueError("Select an existing YouTube channel.")
    state = _make_state(channel_id)
    flow = _flow(state)
    url, _ = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true")
    return {"authorization_url": url, "expires_in_seconds": 600, "channel_id": channel_id}


def complete_youtube_connection(state: str, code: str) -> dict:
    channel_id = _read_state(state)
    flow = _flow(state)
    flow.fetch_token(code=code)
    token_json = flow.credentials.to_json().encode("utf-8")
    encrypted = _cipher().encrypt(token_json)
    _token_path(channel_id).write_bytes(encrypted)
    return {"connected": True, "platform": "youtube", "channel_id": channel_id}


def _credentials(channel_id: str) -> Credentials:
    path = _token_path(channel_id)
    if not path.is_file():
        raise ValueError("YouTube channel is not connected. Complete OAuth first.")
    try:
        token_json = _cipher().decrypt(path.read_bytes()).decode("utf-8")
        credentials = Credentials.from_authorized_user_info(json.loads(token_json), [YOUTUBE_SCOPE])
    except (InvalidToken, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Cannot decrypt saved YouTube credentials. Check CREATOROS_FERNET_KEY.") from exc
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        encrypted = _cipher().encrypt(credentials.to_json().encode("utf-8"))
        path.write_bytes(encrypted)
    if not credentials.valid:
        raise RuntimeError("YouTube credentials are invalid; reconnect this channel.")
    return credentials


def youtube_connection_status(channel_id: str) -> dict:
    channel = channel_get(channel_id)
    if not channel or channel.get("platform") != "youtube":
        raise ValueError("YouTube channel not found.")
    return {"channel_id": channel_id, "platform": "youtube", "connected": _token_path(channel_id).is_file()}


def upload_youtube_video(job_id: str, privacy_status: str = "private") -> dict:
    if privacy_status not in {"private", "unlisted", "public"}:
        raise ValueError("privacy_status must be private, unlisted, or public.")
    job = publish_job_get(job_id)
    if not job:
        raise ValueError("Publishing job not found.")
    if job.get("status") not in {"scheduled", "awaiting_approval"}:
        raise ValueError("Only approved or awaiting-approval jobs can be uploaded manually.")
    channel = channel_get(job["channel_id"])
    if not channel or channel.get("platform") != "youtube":
        raise ValueError("This job is not assigned to a YouTube channel.")
    render = render_job_get(job["render_job_id"])
    if not render or render.get("status") != "rendered":
        raise ValueError("A completed video render is required.")
    video_path = Path(render.get("output_path", "")).resolve()
    root = RENDER_ROOT.resolve()
    if root not in video_path.parents or not video_path.is_file():
        raise ValueError("Rendered video is missing or outside the render directory.")
    youtube = build("youtube", "v3", credentials=_credentials(job["channel_id"]), cache_discovery=False)
    body = {
        "snippet": {"title": job["title"][:100], "description": job.get("caption", "")[:5000], "categoryId": "22"},
        "status": {"privacyStatus": privacy_status, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(str(video_path), chunksize=8 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        _, response = request.next_chunk()
    video_id = response.get("id")
    if not video_id:
        raise RuntimeError("YouTube API did not return a video ID.")
    updated = publish_job_update(
        job_id, "published", platform_post_id=video_id,
        published_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        error="",
    )
    return {"job": updated, "video_id": video_id, "url": f"https://www.youtube.com/watch?v={video_id}", "privacy_status": privacy_status}
