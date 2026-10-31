"""Create a simple vertical MP4 from a Script Studio voice job using local FFmpeg."""
import os, shutil, sqlite3, subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from app.database import DB_PATH, media_asset_create, media_asset_get
from app.script_voice_engine import get_job as get_voice_job, audio_path as get_voice_audio
from app.script_engine import get_script

MEDIA_ROOT=Path(os.getenv("CREATOROS_MEDIA_DIR","media")).resolve()
def _db():
 DB_PATH.parent.mkdir(parents=True,exist_ok=True); c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row; return c
def _ensure():
 with _db() as c:
  c.execute("""CREATE TABLE IF NOT EXISTS script_video_jobs(
   id TEXT PRIMARY KEY,script_id TEXT NOT NULL,voice_job_id TEXT NOT NULL,
   status TEXT NOT NULL,video_asset_id TEXT,scene_asset_ids_json TEXT NOT NULL DEFAULT '[]',error TEXT NOT NULL DEFAULT '',
   created_at TEXT NOT NULL,updated_at TEXT NOT NULL)""")
  cols={r["name"] for r in c.execute("PRAGMA table_info(script_video_jobs)").fetchall()}
  if "scene_asset_ids_json" not in cols:
   c.execute("ALTER TABLE script_video_jobs ADD COLUMN scene_asset_ids_json TEXT NOT NULL DEFAULT '[]'")
def _row(r):
 if not r:return None
 item=dict(r)
 import json
 item["scene_asset_ids"]=json.loads(item.pop("scene_asset_ids_json","[]") or "[]")
 return item
def create_job(script_id,voice_job_id,scene_asset_ids=None):
 script=get_script(script_id); voice=get_voice_job(voice_job_id)
 if not script or not voice or voice.get("script_id")!=script_id:return None
 scene_asset_ids=list(scene_asset_ids or [])
 scenes=(script.get("content") or {}).get("scenes") or []
 if len(scene_asset_ids)>12 or (scene_asset_ids and len(scene_asset_ids)!=len(scenes)):return None
 for asset_id in scene_asset_ids:
  if asset_id:
   asset=media_asset_get(asset_id)
   if not asset or asset.get("media_type")!="image":return None
 _ensure(); now=datetime.now(timezone.utc).isoformat(); jid=str(uuid4())
 with _db() as c:c.execute("INSERT INTO script_video_jobs(id,script_id,voice_job_id,status,scene_asset_ids_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",(jid,script_id,voice_job_id,"queued",__import__("json").dumps(scene_asset_ids),now,now))
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
 asset_ids=job.get("scene_asset_ids") or []
 if asset_ids and len(asset_ids)!=len(scenes):_update(jid,"failed",error="Scene image mapping no longer matches the script.");return
 image_paths=[]
 for asset_id in asset_ids:
  if not asset_id:image_paths.append(None);continue
  asset=media_asset_get(asset_id)
  path=(MEDIA_ROOT/asset["stored_name"]).resolve() if asset else None
  if not asset or asset.get("media_type")!="image" or not path or MEDIA_ROOT not in path.parents or not path.is_file():
   _update(jid,"failed",error="A selected scene image is missing or invalid.");return
  image_paths.append(path)
 MEDIA_ROOT.mkdir(parents=True,exist_ok=True); name=f"creatoros-video-{jid}.mp4"; output=MEDIA_ROOT/name
 _update(jid,"rendering")
 import tempfile
 try:
  with tempfile.TemporaryDirectory(prefix="creatoros-video-") as td:
   temp=Path(td); sub=temp/"captions.srt"; sub.write_text(srt,encoding="utf-8")
   duration=max(1,int(content.get("estimated_duration_seconds",60)))
   count=max(1,len(scenes)); segment_duration=duration/count; clip_paths=[]
   for i in range(count):
    clip=temp/f"scene-{i:03d}.mp4"; source=image_paths[i] if i<len(image_paths) else None
    if source:
     video_input=["-loop","1","-framerate","30","-i",str(source)]
     vf="scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,format=yuv420p"
    else:
     video_input=["-f","lavfi","-i",f"color=c=0x172033:s=1080x1920:r=30:d={segment_duration:.3f}"]
     vf="format=yuv420p"
    cmd=["ffmpeg","-y","-hide_banner","-loglevel","error",*video_input,"-t",f"{segment_duration:.3f}","-vf",vf,"-an","-r","30","-c:v","libx264","-preset","veryfast","-crf","25","-pix_fmt","yuv420p",str(clip)]
    done=subprocess.run(cmd,capture_output=True,text=True,timeout=240,check=False)
    if done.returncode or not clip.is_file():raise RuntimeError((done.stderr or "FFmpeg scene render failed")[-1400:])
    clip_paths.append(clip)
   concat=temp/"concat.txt"
   concat.write_text("".join("file '"+p.as_posix()+"'\n" for p in clip_paths),encoding="utf-8")
   sub_filter_path=str(sub).replace("\\","/").replace(":","\\:")
   vf="subtitles='"+sub_filter_path+"',format=yuv420p"
   cmd=["ffmpeg","-y","-hide_banner","-loglevel","error","-f","concat","-safe","0","-i",str(concat),"-i",str(audio),"-vf",vf,"-map","0:v:0","-map","1:a:0","-shortest","-r","30","-c:v","libx264","-preset","veryfast","-crf","25","-c:a","aac","-b:a","128k","-movflags","+faststart",str(output)]
   done=subprocess.run(cmd,capture_output=True,text=True,timeout=900,check=False)
   if done.returncode or not output.is_file():raise RuntimeError((done.stderr or "FFmpeg final render failed")[-1800:])
  asset=media_asset_create({"original_name":name,"stored_name":name,"media_type":"video","mime_type":"video/mp4","size_bytes":output.stat().st_size})
  _update(jid,"ready",asset["id"])
 except subprocess.TimeoutExpired:
  output.unlink(missing_ok=True);_update(jid,"failed",error="Video rendering exceeded the time limit.")
 except Exception as exc:
  output.unlink(missing_ok=True);_update(jid,"failed",error=str(exc))

def video_path(jid):
 job=get_job(jid)
 if not job or job["status"]!="ready" or not job["video_asset_id"]:return None
 from app.database import media_asset_get
 asset=media_asset_get(job["video_asset_id"])
 p=(MEDIA_ROOT/asset["stored_name"]).resolve() if asset else None
 return p if p and MEDIA_ROOT in p.parents and p.is_file() else None
