"""Evidence-aware recommendations from recorded channel metrics."""
from collections import defaultdict


def build_optimization_report(records: list[dict]) -> dict:
    if not records:
        return {
            "status": "insufficient_data",
            "message": "Belum ada metrik yang terhubung ke video publikasi. Hubungkan laporan metrik dengan publishing job agar analisis per konten tersedia.",
            "sample_size": 0, "top_videos": [], "format_performance": [],
            "niche_performance": [], "recommendations": [
                {"priority": "high", "title": "Hubungkan metrik ke video", "reason": "Pilih publishing job saat mencatat laporan performa."},
                {"priority": "medium", "title": "Kumpulkan sampel yang sebanding", "reason": "Catat metrik pada rentang waktu yang konsisten untuk beberapa video."}
            ], "caveats": ["Belum cukup data untuk menyimpulkan pola atau menyarankan pemenang."]
        }

    def aggregate(key):
        groups = defaultdict(lambda: {"items": 0, "views": 0, "watch_time_minutes": 0.0,
                                       "likes": 0, "comments": 0, "shares": 0,
                                       "subscribers_gained": 0})
        for row in records:
            name = (row.get(key) or "Unspecified").strip() or "Unspecified"
            g = groups[name]
            g["items"] += 1
            for field in ("views", "watch_time_minutes", "likes", "comments", "shares", "subscribers_gained"):
                g[field] += row.get(field) or 0
        result = []
        for name, g in groups.items():
            views = g["views"]
            g["engagement_rate"] = round((g["likes"] + g["comments"] + g["shares"]) / views * 100, 2) if views else 0
            g["average_views"] = round(views / g["items"], 1)
            g["label"] = name
            result.append(g)
        return sorted(result, key=lambda x: (x["average_views"], x["engagement_rate"]), reverse=True)

    ranked = sorted(records, key=lambda x: (x.get("views") or 0, x.get("engagement_rate") or 0), reverse=True)
    formats = aggregate("format")
    niches = aggregate("niche")
    total_views = sum(r.get("views") or 0 for r in records)
    total_engagements = sum((r.get("likes") or 0) + (r.get("comments") or 0) + (r.get("shares") or 0) for r in records)
    recommendations = []
    if len(records) >= 3:
        top = ranked[0]
        recommendations.append({
            "priority": "high", "title": "Pelajari struktur video dengan views tertinggi",
            "reason": f'"{top.get("title") or "Video teratas"}" mencatat {top.get("views") or 0:,} views. Tinjau hook, topik, dan penyajiannya; satu hasil belum membuktikan penyebab keberhasilan.',
            "action": "Buat satu variasi orisinal untuk diuji, bukan menyalin video."
        })
    if formats:
        best = formats[0]
        recommendations.append({
            "priority": "medium", "title": f"Uji format {best['label']}",
            "reason": f"Format ini memiliki rata-rata {best['average_views']:,.1f} views dari {best['items']} video yang tercatat.",
            "action": "Bandingkan dengan format lain pada periode dan distribusi yang setara."
        })
    if total_views and total_engagements / total_views < 0.02:
        recommendations.append({
            "priority": "medium", "title": "Perkuat ajakan interaksi yang relevan",
            "reason": "Engagement gabungan tercatat di bawah 2% terhadap views.",
            "action": "Uji pertanyaan spesifik atau ajakan menyimpan konten yang benar-benar berguna."
        })
    if len(records) < 5:
        recommendations.append({
            "priority": "high", "title": "Tambah sampel sebelum mengubah strategi besar",
            "reason": f"Hanya {len(records)} video memiliki metrik terhubung; sampel masih kecil.",
            "action": "Kumpulkan setidaknya lima hingga sepuluh video dengan periode pengukuran serupa."
        })
    if not recommendations:
        recommendations.append({
            "priority": "medium", "title": "Lanjutkan eksperimen terukur",
            "reason": "Belum terlihat sinyal yang cukup kuat untuk perubahan besar.",
            "action": "Uji satu perubahan pada hook atau angle, lalu bandingkan hasilnya."
        })
    return {
        "status": "ready" if len(records) >= 5 else "early_signal",
        "sample_size": len(records),
        "totals": {"views": total_views, "engagements": total_engagements,
                   "engagement_rate": round(total_engagements / total_views * 100, 2) if total_views else 0},
        "top_videos": [{k: r.get(k) for k in ("project_id","title","niche","format","channel_name","published_at","views","engagement_rate","metric_snapshots")} for r in ranked[:10]],
        "format_performance": formats[:10], "niche_performance": niches[:10],
        "recommendations": recommendations,
        "caveats": [
            "Analisis hanya memakai metrik yang ditautkan ke publishing job.",
            "Views dan engagement dipengaruhi waktu tayang, distribusi, ukuran audiens, dan faktor lain; korelasi bukan sebab-akibat.",
            "Perbandingan ideal memakai jendela pengukuran yang sama setelah publikasi."
        ]
    }
