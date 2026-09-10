import os
import uuid
import json
import traceback
import time
from typing import List
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Form
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pipeline_video

app = FastAPI(title="AI Video Generator API", version="4.1.0")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

def log(msg): print(f"[API] {msg}")

def _update_status(status_file, status: str, progress: int = 0, **kwargs):
    with open(status_file, "w") as f: json.dump({"status": status, "progress": progress, **kwargs}, f)

def _write_config(output_folder, language):
    with open(f"{output_folder}/config.json", "w") as f: json.dump({"language": language}, f)

def _read_config(output_folder):
    config_path = f"{output_folder}/config.json"
    if not os.path.exists(config_path): return {"language": "en"}
    with open(config_path, "r") as f: return json.load(f)

def run_pipeline(pdf_path: str, job_id: str, mode: str, language: str):
    output_folder = f"{OUTPUT_DIR}/{job_id}"
    os.makedirs(output_folder, exist_ok=True)
    output_video = f"{output_folder}/final_video.mp4"
    status_file = f"{output_folder}/status.json"

    try:
        if mode == "review":
            _update_status(status_file, "generating_scripts", 20)
            pipeline_video.phase_script(pdf_path, output_folder, language=language)
            _update_status(status_file, "awaiting_review", 50, script_url=f"/script/{job_id}")
        else:
            _update_status(status_file, "processing", 0)
            _update_status(status_file, "generating", 50)
            
            # Run the pipeline
            pipeline_video.run_auto(pdf_path, output_video, output_folder, language=language)
            
            # FIX: Wait for file system to sync in Docker/Railway
            time.sleep(3)
            
            if not os.path.exists(output_video):
                raise Exception(f"Video file was not created at {output_video}")
            
            _update_status(status_file, "completed", 100, video_url=f"/download/{job_id}/final_video.mp4")
            log(f"Job {job_id} completed successfully!")

    except Exception as e:
        _update_status(status_file, "failed", 0, error=str(e))
        log(f"Job {job_id} failed: {e}\n{traceback.format_exc()}")

def run_render(job_id: str):
    output_folder = f"{OUTPUT_DIR}/{job_id}"
    output_video = f"{output_folder}/final_video.mp4"
    status_file = f"{output_folder}/status.json"
    cfg = _read_config(output_folder)
    
    try:
        _update_status(status_file, "rendering", 60)
        pipeline_video.phase_render(output_folder, output_video, language=cfg.get("language", "en"))
        
        # FIX: Wait for file system to sync
        time.sleep(3)
        
        if not os.path.exists(output_video):
            raise Exception(f"Video file was not created at {output_video}")
            
        _update_status(status_file, "completed", 100, video_url=f"/download/{job_id}/final_video.mp4")
        log(f"Job {job_id} render completed!")
    except Exception as e:
        _update_status(status_file, "failed", 0, error=str(e))
        log(f"Job {job_id} render failed: {e}")

@app.post("/upload")
async def upload_pdf(background_tasks: BackgroundTasks, file: UploadFile = File(...), mode: str = Form("auto"), language: str = Form("en")):
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    job_id = str(uuid.uuid4())[:8]
    pdf_path = f"{UPLOAD_DIR}/{job_id}.pdf"
    output_folder = f"{OUTPUT_DIR}/{job_id}"
    os.makedirs(output_folder, exist_ok=True)

    try:
        with open(pdf_path, "wb") as f: f.write(await file.read())
        _write_config(output_folder, language)
        log(f"Uploaded: {job_id}.pdf (mode={mode}, language={language})")
        background_tasks.add_task(run_pipeline, pdf_path, job_id, mode, language)
        return JSONResponse({"job_id": job_id, "status": "processing", "status_url": f"/status/{job_id}"})
    except Exception as e:
        if os.path.exists(pdf_path): os.remove(pdf_path)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload-manual")
async def upload_manual(background_tasks: BackgroundTasks, slides: List[UploadFile] = File(...), scripts: str = Form(...), language: str = Form("en")):
    try:
        script_list = json.loads(scripts)
    except Exception:
        raise HTTPException(status_code=400, detail="scripts must be a JSON array of strings")
    
    if not isinstance(script_list, list) or len(script_list) != len(slides):
        raise HTTPException(status_code=400, detail="Number of slides must match number of scripts")

    job_id = str(uuid.uuid4())[:8]
    output_folder = f"{OUTPUT_DIR}/{job_id}"
    slides_folder = f"{output_folder}/slides"
    os.makedirs(slides_folder, exist_ok=True)

    scripts_data = []
    for i, (slide_file, script_text) in enumerate(zip(slides, script_list), 1):
        ext = os.path.splitext(slide_file.filename or "")[1] or ".png"
        image_path = f"{slides_folder}/slide_{i:02d}{ext}"
        with open(image_path, "wb") as f: f.write(await slide_file.read())
        scripts_data.append({"index": i, "image": image_path, "script": script_text})

    with open(f"{output_folder}/scripts.json", "w") as f: json.dump(scripts_data, f)
    _write_config(output_folder, language)

    status_file = f"{output_folder}/status.json"
    _update_status(status_file, "rendering", 60)
    log(f"Uploaded manual job: {job_id}")
    background_tasks.add_task(run_render, job_id)

    return JSONResponse({"job_id": job_id, "status": "rendering", "status_url": f"/status/{job_id}"})

@app.get("/status/{job_id}")
async def get_status(job_id: str):
    status_file = f"{OUTPUT_DIR}/{job_id}/status.json"
    if not os.path.exists(status_file): raise HTTPException(status_code=404, detail="Job not found")
    with open(status_file, "r") as f: return JSONResponse(json.load(f))

@app.get("/script/{job_id}")
async def get_script(job_id: str):
    scripts_file = f"{OUTPUT_DIR}/{job_id}/scripts.json"
    if not os.path.exists(scripts_file): raise HTTPException(status_code=404, detail="No scripts found")
    with open(scripts_file, "r") as f: return JSONResponse(json.load(f))

class SlideScript(BaseModel):
    index: int
    script: str

class ScriptSubmission(BaseModel):
    scripts: List[SlideScript]

@app.post("/script/{job_id}")
async def submit_script(job_id: str, submission: ScriptSubmission, background_tasks: BackgroundTasks):
    output_folder = f"{OUTPUT_DIR}/{job_id}"
    scripts_file = f"{output_folder}/scripts.json"
    if not os.path.exists(scripts_file): raise HTTPException(status_code=404, detail="Job not found")

    with open(scripts_file, "r") as f: scripts_data = json.load(f)
    edits = {s.index: s.script for s in submission.scripts}
    for entry in scripts_data:
        if entry["index"] in edits: entry["script"] = edits[entry["index"]]

    with open(scripts_file, "w") as f: json.dump(scripts_data, f)
    background_tasks.add_task(run_render, job_id)
    return JSONResponse({"job_id": job_id, "status": "rendering", "status_url": f"/status/{job_id}"})

@app.get("/download/{job_id}/final_video.mp4")
async def download_video(job_id: str):
    video_path = f"{OUTPUT_DIR}/{job_id}/final_video.mp4"
    if not os.path.exists(video_path): raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(video_path, media_type="video/mp4", filename=f"video_{job_id}.mp4")

@app.delete("/job/{job_id}")
async def delete_job(job_id: str):
    import shutil
    job_folder = f"{OUTPUT_DIR}/{job_id}"
    pdf_file = f"{UPLOAD_DIR}/{job_id}.pdf"
    deleted = 0
    if os.path.exists(job_folder): shutil.rmtree(job_folder); deleted += 1
    if os.path.exists(pdf_file): os.remove(pdf_file); deleted += 1
    return JSONResponse({"message": f"Deleted {deleted} items", "job_id": job_id})

@app.get("/")
async def root():
    return {"service": "AI Video Generator API", "version": "4.1.0", "status": "running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
