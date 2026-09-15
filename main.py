from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Form
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import uuid
import json
import shutil
import pipeline_video
from auth import router as auth_router
from supabase_client import supabase

# Initialize FastAPI app
app = FastAPI(title="AI Video Studio", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include authentication routes
app.include_router(auth_router)

# Create necessary directories
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

def log(msg):
    print(f"[API] {msg}")

@app.get("/")
async def serve_frontend():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>AI Video Studio</h1>")

@app.post("/upload")
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    language: str = Form("en"),
    cartesia_api_key: str = Form(...),
    cartesia_voice_id: str = Form(...),
    user_id: str = Form(None)
):
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files allowed")
    
    api_key = cartesia_api_key.strip()
    if not api_key.startswith('sk_'):
        raise HTTPException(status_code=400, detail="Invalid Cartesia API key format")
    
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
        
        if not image_paths:
            raise HTTPException(status_code=400, detail="No slides extracted from PDF")
        
        scripts_data = []
        for i, img_path in enumerate(image_paths, 1):
            slide_text = pipeline_video.extract_text_from_slide(pdf_path, i - 1)
            script = pipeline_video.generate_script(slide_text, language=language)
            scripts_data.append({"index": i, "image": img_path, "script": script or f"Script {i}"})
        
        with open(f"{output_folder}/scripts.json", "w") as f:
            json.dump(scripts_data, f)
        
        log(f"Job {job_id} started with {len(image_paths)} slides")
        
        if user_id:
            try:
                supabase.table("videos").insert({
                    "user_id": user_id,
                    "job_id": job_id,
                    "status": "processing",
                    "slides_count": len(image_paths),
                    "language": language,
                    "title": file.filename
                }).execute()
            except Exception as db_error:
                print(f"Database error: {db_error}")
        
        output_video = f"{output_folder}/final_video.mp4"
        background_tasks.add_task(
            pipeline_video.render_from_scripts,
            output_folder,
            output_video,
            language,
            api_key=api_key,
            voice_id=cartesia_voice_id.strip()
        )
        
        return JSONResponse({
            "job_id": job_id,
            "status": "processing",
            "slides": len(image_paths),
            "message": f"Video generation started"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        log(f"Error: {str(e)}")
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.get("/download/{job_id}/final_video.mp4")
async def download_video(job_id: str):
    video_path = f"{OUTPUT_DIR}/{job_id}/final_video.mp4"
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video not found")
    
    return FileResponse(video_path, media_type="video/mp4", filename=f"video_{job_id}.mp4")

@app.get("/video/{job_id}/status")
async def get_video_status(job_id: str):
    video_path = f"{OUTPUT_DIR}/{job_id}/final_video.mp4"
    status = "completed" if os.path.exists(video_path) else "processing"
    
    return JSONResponse({
        "job_id": job_id,
        "status": status,
        "download_url": f"/download/{job_id}/final_video.mp4" if status == "completed" else None
    })

@app.delete("/video/{job_id}")
async def delete_video(job_id: str, user_id: str):
    try:
        # 1. Delete from database
        supabase.table("videos").delete().eq("job_id", job_id).eq("user_id", user_id).execute()
        
        # 2. Delete files from server
        folder_path = f"{OUTPUT_DIR}/{job_id}"
        if os.path.exists(folder_path):
            shutil.rmtree(folder_path)
            
        return {"message": "Video deleted successfully"}
    except Exception as e:
        print(f"Error deleting video: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete video")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)