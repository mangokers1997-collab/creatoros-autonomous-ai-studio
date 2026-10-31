"""Technical quality checks for rendered Script Studio videos."""
import json, shutil, subprocess
from pathlib import Path
from app.script_video_engine import get_job, video_path
from app.script_engine import get_script
from app.script_voice_engine import get_job as get_voice_job

def inspect_video(job_id):
    job=get_job(job_id)
    if not job:
        return None
    if job.get("status")!="ready":
        return {"job_id":job_id,"status":"not_ready","passed":False,"checks":[{"name":"Render status","passed":False,"detail":"Video rendering has not completed."}]}
    path=video_path(job_id)
    if not path:
        return {"job_id":job_id,"status":"missing_file","passed":False,"checks":[{"name":"Video file","passed":False,"detail":"The rendered MP4 file is missing."}]}
    checks=[]
    def add(name,passed,detail,required=True):
        checks.append({"name":name,"passed":bool(passed),"required":required,"detail":detail})
    add("File size",path.stat().st_size>1024,f"{path.stat().st_size} bytes")
    ffprobe=shutil.which("ffprobe")
    if not ffprobe:
        add("Media metadata",False,"ffprobe is not installed; install FFmpeg including ffprobe.")
        return {"job_id":job_id,"status":"failed","passed":False,"checks":checks,"file_size_bytes":path.stat().st_size}
    try:
        result=subprocess.run([ffprobe,"-v","error","-show_entries","format=duration,format_name:stream=codec_type,codec_name,width,height,sample_rate","-of","json",str(path)],capture_output=True,text=True,timeout=30,check=False)
        if result.returncode:
            add("MP4 integrity",False,(result.stderr or "ffprobe could not read this file.")[-800:])
            return {"job_id":job_id,"status":"failed","passed":False,"checks":checks,"file_size_bytes":path.stat().st_size}
        data=json.loads(result.stdout or "{}")
        streams=data.get("streams") or []
        video=next((x for x in streams if x.get("codec_type")=="video"),None)
        audio=next((x for x in streams if x.get("codec_type")=="audio"),None)
        duration=float((data.get("format") or {}).get("duration") or 0)
        add("MP4 integrity",bool(video and duration>0),"Container metadata is readable." if video and duration>0 else "No valid video stream or duration.")
        add("Portrait resolution",bool(video and video.get("width")==1080 and video.get("height")==1920),f"{video.get('width')}×{video.get('height')}" if video else "Video stream missing.")
        add("Video codec",bool(video and video.get("codec_name")=="h264"),video.get("codec_name","missing") if video else "missing")
        add("Audio track",bool(audio),f"{audio.get('codec_name')} audio stream" if audio else "No audio stream detected.")
        add("Duration",duration>=1 and duration<=600,f"{duration:.1f} seconds")
        voice=get_voice_job(job.get("voice_job_id"))
        add("Subtitle source",bool(voice and str(voice.get("subtitles_srt","")).strip()),"Source SRT exists; this does not visually verify caption readability.")
        script=get_script(job.get("script_id"))
        expected=(script or {}).get("content",{}).get("estimated_duration_seconds")
        if expected:
            delta=abs(duration-float(expected))
            add("Duration vs script",delta<=max(8,float(expected)*0.25),f"Rendered {duration:.1f}s; script estimate {expected}s.",required=False)
        passed=all(x["passed"] for x in checks if x.get("required",True))
        return {"job_id":job_id,"status":"passed" if passed else "failed","passed":passed,"duration_seconds":round(duration,2),"width":video.get("width") if video else None,"height":video.get("height") if video else None,"video_codec":video.get("codec_name") if video else None,"audio_codec":audio.get("codec_name") if audio else None,"file_size_bytes":path.stat().st_size,"checks":checks,"review_note":"Automated checks cannot judge storytelling, image rights, visual quality, factual accuracy, or subtitle readability. Preview the full video before publishing."}
    except subprocess.TimeoutExpired:
        add("Media metadata",False,"ffprobe timed out.")
        return {"job_id":job_id,"status":"failed","passed":False,"checks":checks}
    except (ValueError,OSError) as exc:
        add("Media metadata",False,str(exc)[:800])
        return {"job_id":job_id,"status":"failed","passed":False,"checks":checks}
