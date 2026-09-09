import os
import uuid
import json
import subprocess
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="AI Video Generator API", version="1.0.0")

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

def run_pipeline(pdf_path: str, job_id: str):
    output_folder = f"{OUTPUT_DIR}/{job_id}"
    os.makedirs(output_folder, exist_ok=True)
    output_video = f"{output_folder}/final_video.mp4"
    status_file = f"{output_folder}/status.json"
    try:
        with open(status_file, "w") as f:
            json.dump({"status": "processing", "progress": 0}, f)
        script_path = os.path.join(os.path.dirname(__file__), "pipeline_video.py")
        cmd = ["python", script_path, pdf_path, output_video]
        with open(status_file, "w") as f:
            json.dump({"status": "generating", "progress": 50}, f)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise Exception(f"Pipeline failed: {result.stderr}")
        if not os.path.exists(output_video):
            raise Exception("Video file was not created")
        with open(status_file, "w") as f:
            json.dump({"status": "completed", "video_url": f"/download/{job_id}/final_video.mp4", "progress": 100}, f)
    except Exception as e:
        with open(status_file, "w") as f:
            json.dump({"status": "failed", "error": str(e)}, f)

@app.post("/upload")
async def upload_pdf(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    job_id = str(uuid.uuid4())[:8]
    pdf_path = f"{UPLOAD_DIR}/{job_id}.pdf"
    with open(pdf_path, "wb") as f:
        f.write(await file.read())
    background_tasks.add_task(run_pipeline, pdf_path, job_id)
    return JSONResponse({"job_id": job_id, "status": "processing", "status_url": f"/status/{job_id}"})

@app.get("/status/{job_id}")
async def get_status(job_id: str):
    status_file = f"{OUTPUT_DIR}/{job_id}/status.json"
    if not os.path.exists(status_file):
        raise HTTPException(status_code=404, detail="Job not found")
    with open(status_file, "r") as f:
        return JSONResponse(json.load(f))

@app.get("/download/{job_id}/final_video.mp4")
async def download_video(job_id: str):
    video_path = f"{OUTPUT_DIR}/{job_id}/final_video.mp4"
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(video_path, media_type="video/mp4", filename=f"video_{job_id}.mp4")

@app.get("/")
async def root():
    return {"service": "AI Video Generator API", "status": "running"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
