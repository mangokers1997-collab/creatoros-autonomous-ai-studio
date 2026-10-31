"""Piper TTS bridge for saved Script Studio drafts."""
import json, os, shutil, sqlite3, subprocess, tempfile, wave
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from app.database import DB_PATH, media_asset_create, media_asset_get
from app.script_engine import get_script
from app.voice_engine import PIPER_BIN, PIPER_MODEL, _concat_wav, build_srt

MEDIA_ROOT=Path(os.getenv("CREATOROS_MEDIA_DIR","media")).resolve()
def available():
 return bool(PIPER_MODEL and Path(PIPER_MODEL).is_file() and shutil.which(PIPER_BIN))
def _connect():
 DB_PATH.parent.mkdir(parents=True,exist_ok=True); c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row; return c
def _ensure():
 with _connect() as c:
  c.execute("""CREATE TABLE IF NOT EXISTS script_voice_jobs(
   id TEXT PRIMARY KEY,script_id TEXT NOT NULL,status TEXT NOT NULL,
   audio_asset_id TEXT,subtitles_srt TEXT NOT NULL DEFAULT '',
   error TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL)""")
def _row(r):
 return dict(r) if r else None
def create_job(script_id):
 script=get_script(script_id)
 if not script:return None
 _ensure(); now=datetime.now(timezone.utc).isoformat(); jid=str(uuid4())
 with _connect() as c:
  c.execute("INSERT INTO script_voice_jobs(id,script_id,status,created_at,updated_at) VALUES(?,?,?,?,?)",(jid,script_id,"queued",now,now))
 return get_job(jid)
def update_job(jid,status,audio_asset_id=None,subtitles_srt=None,error=None):
 _ensure(); now=datetime.now(timezone.utc).isoformat()
 with _connect() as c:
  c.execute("""UPDATE script_voice_jobs SET status=?,audio_asset_id=COALESCE(?,audio_asset_id),
   subtitles_srt=COALESCE(?,subtitles_srt),error=?,updated_at=? WHERE id=?""",
   (status,audio_asset_id,subtitles_srt,error or "",now,jid))
def get_job(jid):
 _ensure()
 with _connect() as c:return _row(c.execute("SELECT * FROM script_voice_jobs WHERE id=?",(jid,)).fetchone())
def list_jobs(limit=50):
 _ensure()
 with _connect() as c:return [_row(x) for x in c.execute("SELECT * FROM script_voice_jobs ORDER BY created_at DESC LIMIT ?",(limit,))]
def run_job(jid):
 job=get_job(jid)
 if not job:return
 if not available():
  update_job(jid,"failed",error="Piper or PIPER_MODEL is not configured. Install Piper and set PIPER_MODEL to a downloaded .onnx voice model."); return
 script=get_script(job["script_id"])
 if not script:
  update_job(jid,"failed",error="Saved script not found."); return
 content=script["content"]; scenes=content.get("scenes") or []
 chunks=[str(x.get("voiceover","")).strip() for x in scenes if str(x.get("voiceover","")).strip()]
 if not chunks: chunks=[str(content.get("full_voiceover","")).strip()]
 chunks=[x for x in chunks if x]
 if not chunks:
  update_job(jid,"failed",error="Script contains no voiceover text."); return
 update_job(jid,"generating")
 MEDIA_ROOT.mkdir(parents=True,exist_ok=True); final=MEDIA_ROOT/f"script-voice-{jid}.wav"
 try:
  with tempfile.TemporaryDirectory(prefix="creatoros-script-piper-") as td:
   temp=Path(td); segments=[]
   for i,chunk in enumerate(chunks):
    out=temp/f"scene-{i:04d}.wav"
    p=subprocess.run([PIPER_BIN,"--model",PIPER_MODEL,"--output_file",str(out)],input=chunk,text=True,capture_output=True,timeout=180,check=False)
    if p.returncode or not out.is_file():raise RuntimeError((p.stderr or "Piper synthesis failed.")[-1200:])
    segments.append(out)
   durations=_concat_wav(segments,final)
  srt=build_srt(chunks,durations)
  asset=media_asset_create({"original_name":f"creatoros-script-voice-{jid}.wav","stored_name":final.name,"media_type":"audio","mime_type":"audio/wav","size_bytes":final.stat().st_size})
  update_job(jid,"ready",asset["id"],srt)
 except subprocess.TimeoutExpired:
  final.unlink(missing_ok=True); update_job(jid,"failed",error="Piper synthesis timed out.")
 except Exception as exc:
  final.unlink(missing_ok=True); update_job(jid,"failed",error=str(exc))
def audio_path(jid):
 job=get_job(jid)
 if not job or job["status"]!="ready" or not job["audio_asset_id"]:return None
 asset=media_asset_get(job["audio_asset_id"])
 path=(MEDIA_ROOT/asset["stored_name"]).resolve() if asset else None
 return path if path and MEDIA_ROOT in path.parents and path.is_file() else None
