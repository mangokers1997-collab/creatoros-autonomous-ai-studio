"""Create consistent, copy-ready prompts from a saved storyboard."""
from app.script_engine import get_script

def build_visual_prompt_pack(script_id):
    script=get_script(script_id)
    if not script:return None
    content=script.get("content") or {}
    scenes=content.get("scenes") or []
    title=script.get("title","")
    language=script.get("language","en")
    style="cinematic realistic photography, natural lighting, coherent color grading, detailed environment"
    continuity="Maintain the same main character identity, age range, hairstyle, clothing palette, and visual style across every scene. Do not add text, logos, watermarks, or subtitles."
    prompts=[]
    for index,scene in enumerate(scenes,1):
        direction=str(scene.get("visual_direction") or scene.get("visual") or scene.get("purpose") or title).strip()
        prompts.append({"scene_number":index,"visual_direction":direction,"prompt":f"{style}. Scene {index} for the story '{title}'. Depict: {direction}. {continuity}","negative_prompt":"text, captions, watermark, logo, distorted anatomy, extra fingers, duplicate people, low resolution, blurry subject","aspect_ratio":"9:16","continuity_note":continuity})
    return {"script_id":script_id,"title":title,"language":language,"scene_count":len(prompts),"character_reference_prompt":f"Create one reusable character reference for '{title}'. Define consistent face, hairstyle, clothing, age appearance, and color palette. {continuity}","scenes":prompts,"usage_note":"Prompts are text only. Paste into a locally hosted image model or another image tool. Review generated images and check model/output licenses."}
