@app.post("/upload")
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    language: str = Form("en"),
    cartesia_api_key: str = Form(...),
    cartesia_voice_id: str = Form(...)
):
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files allowed")
    
    # Validate Cartesia API key format
    api_key = cartesia_api_key.strip()
    if not api_key.startswith('sk_'):
        raise HTTPException(status_code=400, detail="Invalid Cartesia API key format. Must start with 'sk_'")
    
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
            "message": f"Video generation started for {len(image_paths)} slides"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        log(f"Error in upload: {str(e)}")
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")