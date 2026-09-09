import os
import shutil
import uuid
import json
import subprocess
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import time
from pathlib import Path

# ==========================================
# 🚀 FASTAPI APP INITIALIZATION
# ==========================================
app = FastAPI(
    title="AI Video Generator API",
    description="Convert PDF slides to videos with cloned voice",
    version="1.0.0"
)

# CORS (allow frontend to call this API)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 📁 CONFIGURATION
# ==========================================
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ==========================================
# 🧠 BACKGROUND TASK: RUN THE PIPELINE
# ==========================================
def run_pipeline(pdf_path: str, job_id: str):
    """Run the video pipeline as a background task"""
    
    output_folder = f"{OUTPUT_DIR}/{job_id}"
    os.makedirs(output_folder, exist_ok=True)
    
    output_video = f"{output_folder}/final_video.mp4"
    status_file = f"{output_folder}/status.json"
    
    try:
        # Update status: processing
        with open(status_file, "w") as f:
            json.dump({"status": "processing", "progress": 0}, f)
        
        # Run the pipeline
        script_path = os.path.join(os.path.dirname(__file__), "pipeline_video.py")
        
        cmd = ["python", script_path, pdf_path, output_video]
        
        with open(status_file, "w") as f:
            json.dump({"status": "generating", "progress": 50}, f)
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise Exception(f"Pipeline failed: {result.stderr}")
        
        if not os.path.exists(output_video):
            raise Exception("Video file was not created")
        
        with open(status_file, "w") as f:
            json.dump({
                "status": "completed",
                "video_url": f"/download/{job_id}/final_video.mp4",
                "progress": 100
            }, f)
            
    except Exception as e:
        with open(status_file, "w") as f:
            json.dump({
                "status": "failed",
                "error": str(e)
            }, f)

# ==========================================
# 📤 API ENDPOINT: UPLOAD PDF
# ==========================================
@app.post("/upload")
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """Upload a PDF and start video generation"""
    
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    job_id = str(uuid.uuid4())[:8]
    
    pdf_path = f"{UPLOAD_DIR}/{job_id}.pdf"
    with open(pdf_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    background_tasks.add_task(run_pipeline, pdf_path, job_id)
    
    return JSONResponse({
        "job_id": job_id,
        "status": "processing",
        "message": "Video generation started",
        "status_url": f"/status/{job_id}"
    })

# ==========================================
# 📊 API ENDPOINT: CHECK STATUS
# ==========================================
@app.get("/status/{job_id}")
async def get_status(job_id: str):
    """Get the status of a video generation job"""
    
    status_file = f"{OUTPUT_DIR}/{job_id}/status.json"
    
    if not os.path.exists(status_file):
        raise HTTPException(status_code=404, detail="Job not found")
    
    with open(status_file, "r") as f:
        status = json.load(f)
    
    return JSONResponse(status)

# ==========================================
# 📥 API ENDPOINT: DOWNLOAD VIDEO
# ==========================================
@app.get("/download/{job_id}/final_video.mp4")
async def download_video(job_id: str):
    """Download the generated video"""
    
    video_path = f"{OUTPUT_DIR}/{job_id}/final_video.mp4"
    
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video not found")
    
    return FileResponse(
        video_path,
        media_type="video/mp4",
        filename=f"video_{job_id}.mp4"
    )

# ==========================================
# 🏠 ROOT ENDPOINT (Health Check)
# ==========================================
@app.get("/")
async def root():
    return {
        "service": "AI Video Generator API",
        "status": "running",
        "endpoints": {
            "upload": "POST /upload",
            "status": "GET /status/{job_id}",
            "download": "GET /download/{job_id}/final_video.mp4"
        }
    }

# ==========================================
# 🚀 RUN THE APP
# ==========================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
