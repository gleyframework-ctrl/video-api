import os
import uuid
import json
import subprocess
from typing import List
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Form
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(
    title="AI Video Generator API",
    description="Convert PDF slides to videos with cloned voice narration",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


def log(msg):
    print(f"[API] {msg}")


def _script_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "pipeline_video.py")


def _update_status(status_file, status: str, progress: int = 0, **kwargs):
    data = {"status": status, "progress": progress, **kwargs}
    with open(status_file, "w") as f:
        json.dump(data, f)


def run_pipeline(pdf_path: str, job_id: str, mode: str):
    output_folder = f"{OUTPUT_DIR}/{job_id}"
    os.makedirs(output_folder, exist_ok=True)
    output_video = f"{output_folder}/final_video.mp4"
    status_file = f"{output_folder}/status.json"

    try:
        script_path = _script_path()
        if not os.path.exists(script_path):
            raise Exception(f"Pipeline script not found: {script_path}")

        if mode == "review":
            _update_status(status_file, "generating_scripts", 20)
            cmd = ["python", script_path, "script", pdf_path, output_folder]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                raise Exception(f"Script generation failed: {result.stderr}")
            _update_status(status_file, "awaiting_review", 50, script_url=f"/script/{job_id}")
            log(f"Job {job_id}: awaiting customer script review")
        else:
            _update_status(status_file, "processing", 0)
            _update_status(status_file, "generating", 50)
            cmd = ["python", script_path, "auto", pdf_path, output_video, output_folder]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                raise Exception(f"Pipeline failed: {result.stderr}")
            if not os.path.exists(output_video):
                raise Exception("Video file was not created")
            _update_status(status_file, "completed", 100, video_url=f"/download/{job_id}/final_video.mp4")
            log(f"Job {job_id} completed successfully!")

    except subprocess.TimeoutExpired:
        _update_status(status_file, "failed", 0, error="Pipeline timed out")
    except Exception as e:
        _update_status(status_file, "failed", 0, error=str(e))
        log(f"Job {job_id} failed: {e}")


def run_render(job_id: str):
    output_folder = f"{OUTPUT_DIR}/{job_id}"
    output_video = f"{output_folder}/final_video.mp4"
    status_file = f"{output_folder}/status.json"
    try:
        _update_status(status_file, "rendering", 60)
        cmd = ["python", _script_path(), "render", output_folder, output_video]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise Exception(f"Render failed: {result.stderr}")
        if not os.path.exists(output_video):
            raise Exception("Video file was not created")
        _update_status(status_file, "completed", 100, video_url=f"/download/{job_id}/final_video.mp4")
        log(f"Job {job_id} render completed!")
    except subprocess.TimeoutExpired:
        _update_status(status_file, "failed", 0, error="Render timed out")
    except Exception as e:
        _update_status(status_file, "failed", 0, error=str(e))
        log(f"Job {job_id} render failed: {e}")


@app.post("/upload")
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    mode: str = Form("auto"),
):
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    if mode not in ("auto", "review"):
        raise HTTPException(status_code=400, detail="mode must be 'auto' or 'review'")

    job_id = str(uuid.uuid4())[:8]
    pdf_path = f"{UPLOAD_DIR}/{job_id}.pdf"

    try:
        with open(pdf_path, "wb") as f:
            f.write(await file.read())
        log(f"Uploaded: {job_id}.pdf (mode={mode})")
        background_tasks.add_task(run_pipeline, pdf_path, job_id, mode)
        return JSONResponse({
            "job_id": job_id,
            "status": "processing",
            "mode": mode,
            "status_url": f"/status/{job_id}"
        })
    except Exception as e:
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/status/{job_id}")
async def get_status(job_id: str):
    status_file = f"{OUTPUT_DIR}/{job_id}/status.json"
    if not os.path.exists(status_file):
        raise HTTPException(status_code=404, detail="Job not found")
    with open(status_file, "r") as f:
        return JSONResponse(json.load(f))


@app.get("/script/{job_id}")
async def get_script(job_id: str):
    scripts_file = f"{OUTPUT_DIR}/{job_id}/scripts.json"
    if not os.path.exists(scripts_file):
        raise HTTPException(status_code=404, detail="No scripts found for this job (wrong mode, or not ready yet)")
    with open(scripts_file, "r") as f:
        return JSONResponse(json.load(f))


class SlideScript(BaseModel):
    index: int
    script: str


class ScriptSubmission(BaseModel):
    scripts: List[SlideScript]


@app.post("/script/{job_id}")
async def submit_script(job_id: str, submission: ScriptSubmission, background_tasks: BackgroundTasks):
    output_folder = f"{OUTPUT_DIR}/{job_id}"
    scripts_file = f"{output_folder}/scripts.json"
    if not os.path.exists(scripts_file):
        raise HTTPException(status_code=404, detail="Job not found or not in review mode")

    with open(scripts_file, "r") as f:
        scripts_data = json.load(f)

    edits = {s.index: s.script for s in submission.scripts}
    for entry in scripts_data:
        if entry["index"] in edits:
            entry["script"] = edits[entry["index"]]

    with open(scripts_file, "w") as f:
        json.dump(scripts_data, f)

    background_tasks.add_task(run_render, job_id)
    return JSONResponse({"job_id": job_id, "status": "rendering", "status_url": f"/status/{job_id}"})


@app.get("/download/{job_id}/final_video.mp4")
async def download_video(job_id: str):
    video_path = f"{OUTPUT_DIR}/{job_id}/final_video.mp4"
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(video_path, media_type="video/mp4", filename=f"video_{job_id}.mp4")


@app.delete("/job/{job_id}")
async def delete_job(job_id: str):
    import shutil
    job_folder = f"{OUTPUT_DIR}/{job_id}"
    pdf_file = f"{UPLOAD_DIR}/{job_id}.pdf"
    deleted = 0
    if os.path.exists(job_folder):
        shutil.rmtree(job_folder)
        deleted += 1
    if os.path.exists(pdf_file):
        os.remove(pdf_file)
        deleted += 1
    return JSONResponse({"message": f"Deleted {deleted} items", "job_id": job_id})


@app.get("/")
async def root():
    return {
        "service": "AI Video Generator API",
        "version": "3.0.0",
        "status": "running",
        "endpoints": {
            "upload": "POST /upload (form field: mode=auto|review)",
            "status": "GET /status/{job_id}",
            "get_scripts": "GET /script/{job_id}",
            "submit_scripts": "POST /script/{job_id}",
            "download": "GET /download/{job_id}/final_video.mp4",
            "delete": "DELETE /job/{job_id}"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
