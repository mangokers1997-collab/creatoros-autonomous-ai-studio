"""Free deterministic script and storytelling engine; no paid AI API required."""
import json, re, sqlite3
from datetime import datetime, timezone
from uuid import uuid4
from app.database import DB_PATH

LANG = {
 "id":{"hook":"Pernahkah kamu mengalami {topic}?","intro":"Mari kita pahami masalah ini dengan sederhana.","bridge":"Sekarang, lihat contoh yang dekat dengan kehidupan sehari-hari.","cta":"Simpan video ini dan bagikan kepada orang yang membutuhkan."},
 "en":{"hook":"Have you ever wondered about {topic}?","intro":"Let's break this down in a practical way.","bridge":"Here is how this appears in everyday life.","cta":"Save this video and share it with someone who may find it useful."},
 "ja":{"hook":"{topic}について考えたことはありますか？","intro":"このテーマを分かりやすく整理してみましょう。","bridge":"日常生活の例を見てみましょう。","cta":"役に立ったら保存して共有してください。"},
 "ar":{"hook":"هل فكرت من قبل في {topic}؟","intro":"دعونا نشرح الفكرة بطريقة بسيطة وعملية.","bridge":"إليك مثالاً من الحياة اليومية.","cta":"احفظ هذا الفيديو وشاركه مع من قد يستفيد منه。"}
}
STRUCTURES={
 "plot_twist":["Buka dengan pertanyaan yang memancing rasa ingin tahu.","Bangun ekspektasi dengan dua detail konkret.","Ungkap sudut pandang tak terduga yang tetap masuk akal.","Tutup dengan pelajaran dan ajakan bertindak."],
 "problem_solution":["Jelaskan masalah audiens.","Terangkan penyebab umum tanpa menyalahkan.","Berikan langkah solusi yang bisa dicoba.","Rangkum hasil yang realistis."],
 "listicle":["Sampaikan manfaat daftar sejak awal.","Jelaskan poin pertama dengan contoh.","Jelaskan poin berikutnya secara ringkas.","Pilih tindakan yang bisa dimulai hari ini."],
 "myth_busting":["Sebutkan anggapan populer yang akan diuji.","Jelaskan mengapa anggapan itu belum tentu benar.","Berikan konteks dan bukti yang perlu diperiksa.","Sampaikan kesimpulan bernuansa."],
 "case_study":["Perkenalkan situasi atau kasus secara anonim.","Jelaskan keputusan dan tantangannya.","Bahas hasil serta faktor yang memengaruhi.","Tarik pelajaran yang bisa diterapkan."]
}
def _connect():
 DB_PATH.parent.mkdir(parents=True,exist_ok=True)
 c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row; return c
def _ensure():
 with _connect() as c:
  c.execute("""CREATE TABLE IF NOT EXISTS generated_scripts(id TEXT PRIMARY KEY,title TEXT NOT NULL,topic TEXT NOT NULL,market TEXT NOT NULL,language TEXT NOT NULL,format TEXT NOT NULL,content_json TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)""")
def _row(r):
 if not r:return None
 d=dict(r); d["content"]=json.loads(d.pop("content_json")); return d
def generate_script(data):
 topic=re.sub(r"\s+"," ",str(data.get("topic",""))).strip()
 if len(topic)<3: raise ValueError("Topic must contain at least 3 characters.")
 lang=data.get("language","id")
 if lang not in LANG: raise ValueError("Unsupported language.")
 duration=int(data.get("duration_seconds",60))
 if not 15<=duration<=1800: raise ValueError("Duration must be 15–1800 seconds.")
 structure=data.get("structure","plot_twist")
 if structure not in STRUCTURES: raise ValueError("Unsupported narrative structure.")
 p=LANG[lang]; beats=STRUCTURES[structure]; count=max(3,min(8,round(duration/12)))
 hook=p["hook"].format(topic=topic); scenes=[]
 for i in range(count):
  beat=beats[min(i*len(beats)//count,len(beats)-1)]
  if i==0: voice=hook
  elif i==1: voice=p["intro"]
  elif i==count-2: voice=p["bridge"]
  elif i==count-1: voice=data.get("call_to_action") or p["cta"]
  else: voice=beat+" Topik yang dibahas: "+topic+"."
  start=round(duration*i/count); end=round(duration*(i+1)/count)
  scenes.append({"scene":i+1,"start_seconds":start,"end_seconds":end,"purpose":beat,"voiceover":voice,
   "on_screen_text":topic if i==0 else beat,"visual_direction":"Footage or original illustration relevant to "+topic+"; use licensed or self-created media.","editing_note":"Readable captions and purposeful cuts."})
 title=topic+": "+("panduan praktis" if lang=="id" else "a practical guide")
 content={"title":title,"hook":hook,"format":data.get("format","short"),"estimated_duration_seconds":duration,
  "audience":data.get("audience","general audience"),"niche":data.get("niche","general"),"market":data.get("market","ID"),
  "language":lang,"style":data.get("style","storytelling"),"structure":structure,"outline":beats,"scenes":scenes,
  "full_voiceover":"\n\n".join(s["voiceover"] for s in scenes),"caption":title+". "+hook,
  "call_to_action":data.get("call_to_action") or p["cta"],
  "hashtags":["#"+re.sub(r"[^\w]","",w) for w in (str(data.get("niche",""))+" "+topic).split()[:5] if w],
  "production_notes":["Deterministic template draft, not a language-model completion.","Verify claims and add original examples before publishing.","Use licensed or self-created visuals and music.","Review localization, pronunciation, and accessibility."],
  "fact_check_checklist":["Support factual claims with reliable sources.","Verify dates, statistics, names, and quotations.","Distinguish facts from opinion.","Document sources and media rights."],"source_notes":data.get("source_notes","")}
 now=datetime.now(timezone.utc).isoformat(); sid=str(uuid4()); _ensure()
 with _connect() as c:
  c.execute("INSERT INTO generated_scripts VALUES(?,?,?,?,?,?,?,?,?)",(sid,title,topic,content["market"],lang,content["format"],json.dumps(content,ensure_ascii=False),now,now))
 return {"id":sid,"title":title,"topic":topic,"market":content["market"],"language":lang,"format":content["format"],"content":content,"created_at":now,"updated_at":now,"engine":"template_fallback"}
def list_scripts(limit=50):
 _ensure()
 with _connect() as c:return [_row(r) for r in c.execute("SELECT * FROM generated_scripts ORDER BY created_at DESC LIMIT ?",(limit,))]
def get_script(sid):
 _ensure()
 with _connect() as c:return _row(c.execute("SELECT * FROM generated_scripts WHERE id=?",(sid,)).fetchone())
def update_script(sid,title,content):
 _ensure(); now=datetime.now(timezone.utc).isoformat()
 with _connect() as c:
  cur=c.execute("UPDATE generated_scripts SET title=?,content_json=?,updated_at=? WHERE id=?",(title,json.dumps(content,ensure_ascii=False),now,sid))
  return _row(c.execute("SELECT * FROM generated_scripts WHERE id=?",(sid,)).fetchone()) if cur.rowcount else None
def delete_script(sid):
 _ensure()
 with _connect() as c:return bool(c.execute("DELETE FROM generated_scripts WHERE id=?",(sid,)).rowcount)
