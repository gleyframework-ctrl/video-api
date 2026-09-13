import os
import uuid
import json
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Form
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import pipeline_video

app = FastAPI(title="AI Video Generator", version="7.2.0")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

def log(msg):
    print(f"[API] {msg}")

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    return HTMLResponse("<h1>Frontend not found. Please upload index.html to the root directory.</h1>")

@app.post("/upload")
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    language: str = Form("en"),
    cartesia_api_key: str = Form(...),       # <-- NEW: Get user's key
    cartesia_voice_id: str = Form(...)       # <-- NEW: Get user's voice ID
):
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    job_id = str(uuid.uuid4())[:8]
    pdf_path = f"{UPLOAD_DIR}/{job_id}.pdf"
    output_folder = f"{OUTPUT_DIR}/{job_id}"
    os.makedirs(output_folder, exist_ok=True)
    
    try:
        with open(pdf_path, "wb") as f:
            f.write(await file.read())
        
        slides_folder = f"{output_folder}/slides"
        os.makedirs(slides_folder, exist_ok=True)
        image_paths = pipeline_video.pdf_to_images(pdf_path, slides_folder)
        
        scripts_data = []
        for i, img_path in enumerate(image_paths, 1):
            slide_text = pipeline_video.extract_text_from_slide(pdf_path, i - 1)
            script = pipeline_video.generate_script(slide_text, language=language)
            scripts_data.append({"index": i, "image": img_path, "script": script or f"Script for slide {i}"})
        
        with open(f"{output_folder}/scripts.json", "w") as f:
            json.dump(scripts_data, f)
        
        with open(f"{output_folder}/config.json", "w") as f:
            json.dump({"language": language}, f)
        
        log(f"Job {job_id} started. Mode: Auto-AI with BYOK")
        
        output_video = f"{output_folder}/final_video.mp4"
        
        # PASS THE USER'S KEYS TO THE BACKGROUND TASK
        background_tasks.add_task(
            pipeline_video.render_from_scripts,
            output_folder,
            output_video,
            language,
            api_key=cartesia_api_key,
            voice_id=cartesia_voice_id
        )
        
        return JSONResponse({
            "job_id": job_id,
            "status": "processing",
            "slides": len(image_paths),
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
