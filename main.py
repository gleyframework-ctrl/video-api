import os
import uuid
import json
import subprocess
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

# ==========================================
#  FASTAPI APP INITIALIZATION
# ==========================================
app = FastAPI(
    title="AI Video Generator API",
    description="Convert PDF slides to videos with cloned voice narration",
    version="2.0.0"
)

# CORS Configuration
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

# Create directories
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

def log(msg):
    """Logging helper"""
    print(f"[API] {msg}")

# ==========================================
# 🧠 BACKGROUND TASK: RUN THE PIPELINE
# ==========================================
def run_pipeline(pdf_path: str, job_id: str):
    """Run the video generation pipeline as a background task"""
    
    output_folder = f"{OUTPUT_DIR}/{job_id}"
    os.makedirs(output_folder, exist_ok=True)
    
    output_video = f"{output_folder}/final_video.mp4"
    status_file = f"{output_folder}/status.json"
    
    def update_status(status: str, progress: int = 0, **kwargs):
        """Helper to update status file"""
        data = {"status": status, "progress": progress, **kwargs}
        with open(status_file, "w") as f:
            json.dump(data, f)
        log(f"Job {job_id}: {status} ({progress}%)")
    
    try:
        # Status: Started
        update_status("processing", 0)
        
        # Find pipeline script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(script_dir, "pipeline_video.py")
        
        if not os.path.exists(script_path):
            raise Exception(f"Pipeline script not found: {script_path}")
        
        log(f"Running pipeline: {script_path}")
        
        # Status: Generating
        update_status("generating", 50)
        
        # Run pipeline
        cmd = ["python", script_path, pdf_path, output_video]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )
        
        # Check for errors
        if result.returncode != 0:
            error_msg = result.stderr.strip() or "Unknown error"
            raise Exception(f"Pipeline failed: {error_msg}")
        
        # Verify video was created
        if not os.path.exists(output_video):
            raise Exception("Video file was not created by pipeline")
        
        # Get file size
        file_size_mb = os.path.getsize(output_video) / (1024 * 1024)
        
        # Status: Completed
        update_status(
            "completed",
            100,
            video_url=f"/download/{job_id}/final_video.mp4",
            file_size_mb=round(file_size_mb, 2)
        )
        
        log(f"Job {job_id} completed successfully!")
        
    except subprocess.TimeoutExpired:
        update_status("failed", 0, error="Pipeline timed out (10 min limit)")
        log(f"Job {job_id} timed out")
        
    except Exception as e:
        update_status("failed", 0, error=str(e))
        log(f"Job {job_id} failed: {e}")

# ==========================================
# 📤 API ENDPOINT: UPLOAD PDF
# ==========================================
@app.post("/upload")
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """
    Upload a PDF file to start video generation.
    
    Returns:
        job_id: Unique identifier for tracking
        status_url: Endpoint to check progress
    """
    
    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are allowed"
        )
    
    # Generate unique job ID
    job_id = str(uuid.uuid4())[:8]
    pdf_path = f"{UPLOAD_DIR}/{job_id}.pdf"
    
    try:
        # Save uploaded file
        with open(pdf_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        file_size_kb = len(content) / 1024
        log(f"Uploaded: {job_id}.pdf ({file_size_kb:.1f} KB)")
        
        # Start background processing
        background_tasks.add_task(run_pipeline, pdf_path, job_id)
        
        return JSONResponse({
            "job_id": job_id,
            "status": "processing",
            "message": "Video generation started",
            "status_url": f"/status/{job_id}",
            "estimated_time": "2-5 minutes"
        })
        
    except Exception as e:
        # Clean up on error
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
#  API ENDPOINT: CHECK STATUS
# ==========================================
@app.get("/status/{job_id}")
async def get_status(job_id: str):
    """
    Get the status of a video generation job.
    
    Status values:
    - processing: Just started
    - generating: AI is working
    - completed: Ready to download
    - failed: Something went wrong
    """
    
    status_file = f"{OUTPUT_DIR}/{job_id}/status.json"
    
    if not os.path.exists(status_file):
        raise HTTPException(
            status_code=404,
            detail="Job not found. Upload a PDF first."
        )
    
    try:
        with open(status_file, "r") as f:
            status = json.load(f)
        
        return JSONResponse(status)
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid status file")

# ==========================================
#  API ENDPOINT: DOWNLOAD VIDEO
# ==========================================
@app.get("/download/{job_id}/final_video.mp4")
async def download_video(job_id: str):
    """
    Download the generated video file.
    Only available when status is 'completed'.
    """
    
    video_path = f"{OUTPUT_DIR}/{job_id}/final_video.mp4"
    
    if not os.path.exists(video_path):
        # Check if job exists
        status_file = f"{OUTPUT_DIR}/{job_id}/status.json"
        if os.path.exists(status_file):
            with open(status_file, "r") as f:
                status = json.load(f)
            if status.get("status") == "failed":
                raise HTTPException(
                    status_code=400,
                    detail=f"Video generation failed: {status.get('error')}"
                )
        raise HTTPException(
            status_code=404,
            detail="Video not found. Check status endpoint."
        )
    
    return FileResponse(
        video_path,
        media_type="video/mp4",
        filename=f"video_{job_id}.mp4",
        headers={
            "Content-Disposition": f"attachment; filename=video_{job_id}.mp4"
        }
    )

# ==========================================
# 🗑️ API ENDPOINT: DELETE JOB (Cleanup)
# ==========================================
@app.delete("/job/{job_id}")
async def delete_job(job_id: str):
    """Delete a job and all associated files"""
    
    job_folder = f"{OUTPUT_DIR}/{job_id}"
    pdf_file = f"{UPLOAD_DIR}/{job_id}.pdf"
    
    deleted = 0
    
    if os.path.exists(job_folder):
        import shutil
        shutil.rmtree(job_folder)
        deleted += 1
    
    if os.path.exists(pdf_file):
        os.remove(pdf_file)
        deleted += 1
    
    return JSONResponse({
        "message": f"Deleted {deleted} items",
        "job_id": job_id
    })

# ==========================================
#  ROOT ENDPOINT (Health Check)
# ==========================================
@app.get("/")
async def root():
    """API health check and documentation"""
    
    return {
        "service": "AI Video Generator API",
        "version": "2.0.0",
        "status": "running",
        "features": [
            "PDF to video conversion",
            "AI script generation (NVIDIA Llama 3.2)",
            "Voice cloning (Cartesia Sonic-2)",
            "Automated video assembly"
        ],
        "endpoints": {
            "upload": "POST /upload - Upload PDF file",
            "status": "GET /status/{job_id} - Check job status",
            "download": "GET /download/{job_id}/final_video.mp4 - Download video",
            "delete": "DELETE /job/{job_id} - Delete job files"
        },
        "docs": "/docs"
    }

# ==========================================
# 🚀 RUN THE APP
# ==========================================
if __name__ == "__main__":
    import uvicorn
    
    # Get port from environment or default to 8000
    port = int(os.environ.get("PORT", 8000))
    
    log(f"Starting server on port {port}...")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
