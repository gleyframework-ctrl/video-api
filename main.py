import os
import uuid
import json
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Form
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List
import pipeline_video

app = FastAPI(title="Video Generator API", version="6.0.0")

app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"]
)

UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

def log(msg):
    print(f"[API] {msg}")

@app.post("/create-video")
async def create_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    scripts: str = Form(...),
    language: str = Form("en")
):
    """
    Create video from PDF + your pre-written scripts
    
    scripts: JSON array like ["script for slide 1", "script for slide 2", ...]
    """
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files allowed")
    
    try:
        script_list = json.loads(scripts)
    except Exception:
        raise HTTPException(status_code=400, detail="scripts must be valid JSON array")
    
    if not isinstance(script_list, list):
        raise HTTPException(status_code=400, detail="scripts must be an array")
    
    job_id = str(uuid.uuid4())[:8]
    pdf_path = f"{UPLOAD_DIR}/{job_id}.pdf"
    output_folder = f"{OUTPUT_DIR}/{job_id}"
    os.makedirs(output_folder, exist_ok=True)
    
    try:
        # Save PDF
        with open(pdf_path, "wb") as f:
            f.write(await file.read())
        
        # Extract slides
        slides_folder = f"{output_folder}/slides"
        os.makedirs(slides_folder, exist_ok=True)
        image_paths = pipeline_video.pdf_to_images(pdf_path, slides_folder)
        
        # Create scripts data
        scripts_data = []
        for i, (img_path, script_text) in enumerate(zip(image_paths, script_list), 1):
            if i <= len(script_list):
                scripts_data.append({
                    "index": i,
                    "image": img_path,
                    "script": script_text
                })
        
        # Save scripts
        with open(f"{output_folder}/scripts.json", "w") as f:
            json.dump(scripts_data, f)
        
        # Save config
        with open(f"{output_folder}/config.json", "w") as f:
            json.dump({"language": language}, f)
        
        log(f"Creating video: {job_id} ({len(scripts_data)} slides)")
        
        # Start video generation
        output_video = f"{output_folder}/final_video.mp4"
        background_tasks.add_task(
            pipeline_video.render_from_scripts,
            output_folder,
            output_video,
            language
        )
        
        return JSONResponse({
            "job_id": job_id,
            "status": "processing",
            "slides": len(scripts_data),
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

@app.get("/download/{job_id}/final_video.mp4")
async def download_video(job_id: str):
    video_path = f"{OUTPUT_DIR}/{job_id}/final_video.mp4"
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(video_path, media_type="video/mp4", filename=f"video_{job_id}.mp4")

@app.get("/")
async def root():
    return {
        "service": "Video Generator API",
        "version": "6.0.0",
        "status": "running",
        "endpoint": "POST /create-video"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
