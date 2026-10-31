"""Create a simple vertical MP4 from a Script Studio voice job using local FFmpeg."""
import os, shutil, sqlite3, subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from app.database import DB_PATH, media_asset_create
from app.script_voice_engine import get_job as get_voice_job, audio_path as get_voice_audio
from app.script_engine import get_script

MEDIA_ROOT=Path(os.getenv("CREATOROS_MEDIA_DIR","media")).resolve()
def _db():
 DB_PATH.parent.mkdir(parents=True,exist_ok=True); c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row; return c
def _ensure():
 with _db() as c:
  c.execute("""CREATE TABLE IF NOT EXISTS script_video_jobs(
   id TEXT PRIMARY KEY,script_id TEXT NOT NULL,voice_job_id TEXT NOT NULL,
   status TEXT NOT NULL,video_asset_id TEXT,error TEXT NOT NULL DEFAULT '',
   created_at TEXT NOT NULL,updated_at TEXT NOT NULL)""")
def _row(r):return dict(r) if r else None
def create_job(script_id,voice_job_id):
 script=get_script(script_id); voice=get_voice_job(voice_job_id)
 if not script or not voice or voice.get("script_id")!=script_id:return None
 _ensure(); now=datetime.now(timezone.utc).isoformat(); jid=str(uuid4())
 with _db() as c:c.execute("INSERT INTO script_video_jobs(id,script_id,voice_job_id,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",(jid,script_id,voice_job_id,"queued",now,now))
 return get_job(jid)
def get_job(jid):
 _ensure()
 with _db() as c:return _row(c.execute("SELECT * FROM script_video_jobs WHERE id=?",(jid,)).fetchone())
def list_jobs(limit=50):
 _ensure()
 with _db() as c:return [_row(x) for x in c.execute("SELECT * FROM script_video_jobs ORDER BY created_at DESC LIMIT ?",(limit,))]
def _update(jid,status,asset_id=None,error=""):
 with _db() as c:c.execute("UPDATE script_video_jobs SET status=?,video_asset_id=COALESCE(?,video_asset_id),error=?,updated_at=? WHERE id=?",(status,asset_id,error[:2000],datetime.now(timezone.utc).isoformat(),jid))
def run_job(jid):
 job=get_job(jid)
 if not job:return
 if not shutil.which("ffmpeg"):_update(jid,"failed",error="FFmpeg is not installed or not on PATH.");return
 voice=get_voice_job(job["voice_job_id"]); audio=get_voice_audio(job["voice_job_id"]); script=get_script(job["script_id"])
 if not voice or voice.get("status")!="ready" or not audio or not script:
  _update(jid,"failed",error="A completed voice job and its saved script/audio are required.");return
 content=script["content"]; scenes=content.get("scenes") or []
 srt=voice.get("subtitles_srt","")
 if not srt.strip():_update(jid,"failed",error="Voice job has no subtitle data.");return
 MEDIA_ROOT.mkdir(parents=True,exist_ok=True); name=f"creatoros-video-{jid}.mp4"; output=MEDIA_ROOT/name
 _update(jid,"rendering")
 import tempfile
 try:
  with tempfile.TemporaryDirectory(prefix="creatoros-video-") as td:
   sub=Path(td)/"captions.srt"; sub.write_text(srt,encoding="utf-8")
   # Scene labels are timed against the generated audio; captions are burned in separately.
   duration=max(1,int(content.get("estimated_duration_seconds",60)))
   filters=[]
   for i,scene in enumerate(scenes[:12]):
    start=duration*i/max(1,len(scenes)); end=duration*(i+1)/max(1,len(scenes))
    label=str(scene.get("on_screen_text") or scene.get("purpose") or "").replace("\\"," ").replace("'","’").replace(":"," - ").replace("%"," percent")[:100]
    if label:
     filters.append(f"drawtext=text='{label}':fontcolor=white:fontsize=52:line_spacing=10:box=1:boxcolor=black@0.48:boxborderw=22:x=(w-text_w)/2:y=h*0.22:enable='between(t,{start:.2f},{end:.2f})'")
   sub_filter_path=str(sub).replace("\\","/").replace(":","\\:")
   filters.append(f"subtitles='{sub_filter_path}'")
   vf=",".join(filters)+",format=yuv420p"
   cmd=["ffmpeg","-y","-hide_banner","-loglevel","error","-f","lavfi","-i",f"color=c=0x172033:s=1080x1920:r=30:d={duration}","-i",str(audio),"-vf",vf,"-map","0:v:0","-map","1:a:0","-shortest","-r","30","-c:v","libx264","-preset","veryfast","-crf","25","-c:a","aac","-b:a","128k","-movflags","+faststart",str(output)]
   done=subprocess.run(cmd,capture_output=True,text=True,timeout=900,check=False)
   if done.returncode or not output.is_file():raise RuntimeError((done.stderr or "FFmpeg render failed")[-1800:])
  asset=media_asset_create({"original_name":name,"stored_name":name,"media_type":"video","mime_type":"video/mp4","size_bytes":output.stat().st_size})
  _update(jid,"ready",asset["id"])
 except subprocess.TimeoutExpired:
  output.unlink(missing_ok=True);_update(jid,"failed",error="Video rendering exceeded the 15-minute limit.")
 except Exception as exc:
  output.unlink(missing_ok=True);_update(jid,"failed",error=str(exc))
def video_path(jid):
 job=get_job(jid)
 if not job or job["status"]!="ready" or not job["video_asset_id"]:return None
 from app.database import media_asset_get
 asset=media_asset_get(job["video_asset_id"])
 p=(MEDIA_ROOT/asset["stored_name"]).resolve() if asset else None
 return p if p and MEDIA_ROOT in p.parents and p.is_file() else None
