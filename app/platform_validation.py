from __future__ import annotations

from datetime import datetime, timezone

PLATFORM_LIMITS = {
    "youtube": {"title_max": 100, "caption_max": 5000, "requires_oauth": True},
    "instagram": {"title_max": 100, "caption_max": 2200, "requires_oauth": True},
    "facebook": {"title_max": 100, "caption_max": 63206, "requires_oauth": True},
    "tiktok": {"title_max": 150, "caption_max": 2200, "requires_oauth": True},
}

def validate_publish_metadata(platform: str, title: str, caption: str) -> dict:
    key = (platform or "").lower()
    if key not in PLATFORM_LIMITS:
        raise ValueError("Unsupported publishing platform.")
    limits = PLATFORM_LIMITS[key]
    errors = []
    if not title.strip():
        errors.append("Title or post text is required.")
    if len(title) > limits["title_max"]:
        errors.append(f"Title exceeds {limits['title_max']} characters.")
    if len(caption) > limits["caption_max"]:
        errors.append(f"Caption exceeds {limits['caption_max']} characters.")
    return {"valid": not errors, "platform": key, "errors": errors,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "limits": limits}
