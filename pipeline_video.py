import os
import sys
import json
import subprocess
import requests
from pypdf import PdfReader
from PIL import Image
import io

CARTESIA_API_KEY = os.environ.get("CARTESIA_API_KEY")
CARTESIA_VOICE_ID = os.environ.get("CARTESIA_VOICE_ID", "2a1938fe-6a4c-4fa0-86a7-dd585a5f7211")

if not CARTESIA_API_KEY:
    raise ValueError("Missing CARTESIA_API_KEY!")

def log(msg):
    print(msg)
    sys.stdout.flush()

def pdf_to_images(pdf_path, output_folder):
    os.makedirs(output_folder, exist_ok=True)
    reader = PdfReader(pdf_path)
    image_paths = []
    
    for i, page in enumerate(reader.pages):
        image_found = False
        for img in page.images:
            try:
                pil_image = Image.open(io.BytesIO(img.data))
                if pil_image.mode != 'RGB':
                    pil_image = pil_image.convert('RGB')
                image_path = f"{output_folder}/slide_{i+1:02d}.png"
                pil_image.save(image_path, "PNG")
                image_paths.append(image_path)
                log(f"[OK] Extracted: {image_path}")
                image_found = True
                break
            except Exception as e:
                log(f"[WARN] Failed: {e}")
        
        if not image_found:
            log(f"[WARN] Creating placeholder for slide {i+1}")
            img = Image.new('RGB', (1280, 720), color=(255, 255, 255))
            image_path = f"{output_folder}/slide_{i+1:02d}.png"
            img.save(image_path, "PNG")
            image_paths.append(image_path)
    
    return image_paths

def generate_audio(script, output_path, language="en"):
    log(f"[AUDIO] Generating: {output_path}")
    
    url = "https://api.cartesia.ai/tts/bytes"
    headers = {
        "Cartesia-Version": "2024-06-10",
        "X-API-Key": CARTESIA_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "model_id": "sonic-3",
        "voice": {"mode": "id", "id": CARTESIA_VOICE_ID},
        "output_format": {"container": "mp3", "bit_rate": 128000, "sample_rate": 44100},
        "transcript": script,
        "language": language,
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        if response.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(response.content)
            size = os.path.getsize(output_path)
            log(f"[OK] Audio saved: {output_path} ({size} bytes)")
            return output_path
        else:
            log(f"[ERROR] Cartesia: {response.status_code}")
            return None
    except Exception as e:
        log(f"[ERROR] {e}")
        return None

def get_audio_duration(audio_path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except:
        return 10.0

def create_clip(image_path, audio_path, duration, output_path):
    log(f"[CLIP] Creating...")
    duration = max(duration, 0.5)
    
    cmd = [
        "ffmpeg", "-loop", "1", "-i", image_path, "-i", audio_path,
        "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-t", str(duration + 0.5), "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-threads", "1",
        "-shortest", "-y", output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        log(f"[ERROR] FFmpeg failed")
        return None
    else:
        if os.path.exists(output_path):
            size = os.path.getsize(output_path)
            log(f"[OK] Clip saved: {output_path} ({size} bytes)")
            return output_path
        return None

def concat_clips(clip_paths, output_path):
    output_dir = os.path.dirname(output_path)
    os.makedirs(output_dir, exist_ok=True)
    list_path = os.path.join(output_dir, "filelist.txt")
    
    log(f"[CONCAT] Concatenating {len(clip_paths)} clips...")
    
    with open(list_path, "w") as f:
        for clip in clip_paths:
            abs_clip = os.path.abspath(clip)
            f.write(f"file '{abs_clip}'\n")
    
    cmd = [
        "ffmpeg", "-f", "concat", "-safe", "0", "-i", list_path,
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k", "-threads", "1",
        "-y", output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        log(f"[ERROR] Concat failed")
        if os.path.exists(list_path):
            os.remove(list_path)
        return False
    
    if os.path.exists(output_path):
        size = os.path.getsize(output_path)
        log(f"[OK] Final video: {output_path} ({size} bytes)")
        if os.path.exists(list_path):
            os.remove(list_path)
        return True
    return False

def render_from_scripts(job_dir, output_video, language="en"):
    status_file = f"{job_dir}/status.json"
    
    try:
        with open(f"{job_dir}/scripts.json", "r") as f:
            scripts_data = json.load(f)
        
        temp_audio_dir = f"{job_dir}/temp_audio"
        temp_clips_dir = f"{job_dir}/temp_clips"
        os.makedirs(temp_audio_dir, exist_ok=True)
        os.makedirs(temp_clips_dir, exist_ok=True)
        
        clips = []
        
        for entry in scripts_data:
            i = entry["index"]
            script = entry["script"]
            image_path = entry["image"]
            
            # Generate audio
            audio_path = f"{temp_audio_dir}/slide_{i:02d}.mp3"
            audio_file = generate_audio(script, audio_path, language)
            
            if not audio_file:
                continue
            
            # Get duration
            duration = get_audio_duration(audio_file)
            
            # Create clip
            clip_path = f"{temp_clips_dir}/clip_{i:02d}.mp4"
            clip = create_clip(image_path, audio_file, duration, clip_path)
            
            if clip:
                clips.append(clip)
        
        if not clips:
            log("[ERROR] No clips created")
            with open(status_file, "w") as f:
                json.dump({"status": "failed", "error": "No clips"}, f)
            return False
        
        # Concatenate
        success = concat_clips(clips, output_video)
        
        if success:
            with open(status_file, "w") as f:
                json.dump({
                    "status": "completed",
                    "progress": 100,
                    "video_url": f"/download/{os.path.basename(job_dir)}/final_video.mp4"
                }, f)
        else:
            with open(status_file, "w") as f:
                json.dump({"status": "failed"}, f)
        
        return success
        
    except Exception as e:
        log(f"[ERROR] {e}")
        with open(status_file, "w") as f:
            json.dump({"status": "failed", "error": str(e)}, f)
        return False
