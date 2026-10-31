from __future__ import annotations

from app.database import content_package_create, project_get


def _clean(value: str) -> str:
    return (value or "").strip().rstrip(".")


def generate_content_package(project_id: str) -> dict | None:
    project = project_get(project_id)
    if not project:
        return None

    title = _clean(project["title"])
    niche = _clean(project["niche"]) or "general"
    brief = _clean(project["brief"])
    market = project["target_market"]
    language = project["language"].lower().split("-")[0]
    is_id = language in {"id", "ind"}

    if is_id:
        hook = f"Kenapa {title.lower()} penting untuk dipahami?"
        intro = f"Hari ini kita membahas {title.lower()} dalam konteks {niche.lower()}."
        value = f"Pahami tiga hal utama: masalah yang dihadapi, langkah yang bisa dicoba, dan kesalahan yang perlu dihindari."
        close = "Simpan video ini dan bagikan kepada orang yang mungkin membutuhkannya."
        disclaimer = "Sesuaikan saran dengan situasi dan lakukan pemeriksaan fakta sebelum publikasi."
        scene_texts = [
            ("Pembuka", hook, "Tampilkan judul besar dan visual pemantik yang relevan."),
            ("Konteks", intro, "Gunakan footage pendukung berlisensi atau visual buatan sendiri."),
            ("Poin utama", value, "Tampilkan tiga poin singkat sebagai teks di layar."),
            ("Contoh", brief or f"Berikan contoh nyata yang relevan dengan {market}.", "Gunakan ilustrasi atau demonstrasi sederhana."),
            ("Penutup", close, "Tampilkan ajakan bertindak tanpa klaim berlebihan."),
        ]
        description = f"{intro} {value} {close}"
        hashtags = ["#" + niche.replace(" ", ""), "#" + market.replace(" ", ""), "#Edukasi", "#Shorts"]
    else:
        hook = f"What should you know about {title.lower()}?"
        intro = f"In this video, we explore {title.lower()} through the lens of {niche.lower()}."
        value = "Focus on three useful points: the problem, practical steps to consider, and common mistakes to avoid."
        close = "Save this video and share it with someone who may find it useful."
        disclaimer = "Adapt the guidance to your circumstances and fact-check all claims before publishing."
        scene_texts = [
            ("Hook", hook, "Show a clear title and a relevant opening visual."),
            ("Context", intro, "Use licensed supporting footage or original visuals."),
            ("Key points", value, "Display three concise points on screen."),
            ("Example", brief or f"Add a specific example relevant to {market}.", "Use a simple illustration or demonstration."),
            ("Close", close, "End with a clear, non-misleading call to action."),
        ]
        description = f"{intro} {value} {close}"
        hashtags = ["#" + niche.replace(" ", ""), "#" + market.replace(" ", ""), "#Education", "#Shorts"]

    script_parts = [hook, intro, value, scene_texts[3][1], close, disclaimer]
    script = "\n\n".join(script_parts)
    storyboard = []
    subtitle_lines = []
    for index, (label, narration, visual) in enumerate(scene_texts):
        start = index * 8
        end = start + 8
        storyboard.append({
            "scene": index + 1,
            "label": label,
            "duration_seconds": 8,
            "narration": narration,
            "visual_direction": visual,
            "on_screen_text": label if index else title,
        })
        subtitle_lines.extend([
            str(index + 1),
            f"00:00:{start:02d},000 --> 00:00:{end:02d},000",
            narration,
            "",
        ])
    subtitle_lines.extend([
        "6",
        "00:00:40,000 --> 00:00:48,000",
        disclaimer,
        "",
    ])
    data = {
        "title": title,
        "hook": hook,
        "description": description,
        "script": script,
        "storyboard": storyboard,
        "subtitles_srt": "\n".join(subtitle_lines),
        "hashtags": hashtags,
        "language": project["language"],
    }
    return content_package_create(project_id, data)
