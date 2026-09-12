from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import os
import uuid
import subprocess
import time
from pathlib import Path
import fitz  # PyMuPDF for PDF processing

app = FastAPI()

# Create output directories
os.makedirs("outputs", exist_ok=True)

@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    job_id = str(uuid.uuid4())[:8]
    job_dir = Path(f"outputs/{job_id}")
    job_dir.mkdir(parents=True, exist_ok=True)
    
    # Save uploaded PDF
    pdf_path = job_dir / file.filename
    with open(pdf_path, "wb") as f:
        f.write(await file.read())
    
    # Extract slides
    extract_slides(pdf_path, job_dir)
    
    return {"job_id": job_id, "status": "processing"}

def extract_slides(pdf_path, job_dir):
    doc = fitz.open(pdf_path)
    slides_dir = job_dir / "slides"
    slides_dir.mkdir(exist_ok=True)
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        pix.save(str(slides_dir / f"slide_{page_num+1:02d}.png"))
    
    doc.close()
    return len(doc)

@app.get("/status/{job_id}")
async def get_status(job_id: str):
    # Check if video exists
    video_path = Path(f"outputs/{job_id}/final_video.mp4")
    if video_path.exists():
        return {"status": "completed", "job_id": job_id}
    return {"status": "processing", "job_id": job_id}

@app.get("/download/{job_id}/final_video.mp4")
async def download_video(job_id: str):
    video_path = Path(f"outputs/{job_id}/final_video.mp4")
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(str(video_path), media_type="video/mp4")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
