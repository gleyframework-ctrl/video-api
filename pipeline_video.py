import os
import sys
import json
import subprocess
from openai import OpenAI
import requests
from pypdf import PdfReader
from PIL import Image
import io

def _get_nvidia_key():
    key = os.environ.get("NVIDIA_API_KEY")
    if not key: raise ValueError("NVIDIA_API_KEY is not set.")
    return key

def _get_cartesia_key():
    key = os.environ.get("CARTESIA_API_KEY")
    if not key: raise ValueError("CARTESIA_API_KEY is not set.")
    return key

CARTESIA_VOICE_ID = os.environ.get("CARTESIA_VOICE_ID", "aee2a343-ab30-430a-b50d-34eaec3dfba6")

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
                if pil_image.mode != 'RGB': pil_image = pil_image.convert('RGB')
                image_path = f"{output_folder}/slide_{i+1:02d}.png"
                pil_image.save(image_path, "PNG")
                image_paths.append(image_path)
                log(f"[OK] Extracted: {image_path}")
                image_found = True
                break
            except Exception as e:
                log(f"[WARN] Failed to extract image {i+1}: {e}")
        if not image_found:
            log(f"[WARN] No image on page {i+1}, creating placeholder")
            img = Image.new('RGB', (1920, 1080), color=(255, 255, 255))
            image_path = f"{output_folder}/slide_{i+1:02d}.png"
            img.save(image_path, "PNG")
            image_paths.append(image_path)
    return image_paths

def extract_text_from_slide(pdf_path, slide_index):
    try:
        reader = PdfReader(pdf_path)
        if slide_index < len(reader.pages):
            text = reader.pages[slide_index].extract_text()
            return text.strip() if text else f"Slide {slide_index + 1}"
    except Exception as e:
        log(f"[WARN] Could not extract text: {e}")
    return f"Slide {slide_index + 1}"

def generate_script(slide_text, language="en"):
    log("[AI] Writing script...")
    client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=_get_nvidia_key())
    prompt = f"Write a short, engaging spoken script (max 80 words) in {language} for this slide content: \"{slide_text}\". Output ONLY the raw spoken text."
    try:
        completion = client.chat.completions.create(model="meta/llama-3.2-11b-vision-instruct", messages=[{"role": "user", "content": prompt}], temperature=0.7, max_tokens=300, timeout=300)
        script = completion.choices[0].message.content.strip()
        log("[OK] Script generated")
        return script
    except Exception as e:
        log(f"[ERROR] NVIDIA API error: {e}")
        return None

def generate_audio(script, output_path, language="en"):
    log("[AUDIO] Generating voice...")
    url = "https://api.cartesia.ai/tts/bytes"
    headers = {"Cartesia-Version": "2024-06-10", "X-API-Key": _get_cartesia_key(), "Content-Type": "application/json"}
    payload = {
        "model_id": "sonic-3", # sonic-3 supports Arabic and more languages
        "voice": {"mode": "id", "id": CARTESIA_VOICE_ID},
        "output_format": {"container": "mp3", "bit_rate": 128000, "sample_rate": 44100},
        "transcript": script,
        "language": language,
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        if response.status_code == 200:
            with open(output_path, "wb") as f: f.write(response.content)
            log(f"[OK] Audio saved: {output_path}")
            return output_path
        else:
            log(f"[ERROR] Cartesia error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        log(f"[ERROR] Cartesia request failed: {e}")
        return None

def get_audio_duration(audio_path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try: return float(result.stdout.strip())
    except ValueError: return 10.0

def create_clip(image_path, audio_path, duration, output_path):
    duration = max(duration, 0.5)
    cmd = ["ffmpeg", "-loop", "1", "-i", image_path, "-i", audio_path, "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-c:v", "libx264", "-t", str(duration + 0.5), "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-y", output_path]
    subprocess.run(cmd, capture_output=True)
    log(f"[OK] Clip saved: {output_path}")
    return output_path

def concat_clips(clip_paths, output_path):
    list_path = "filelist.txt"
    with open(list_path, "w") as f:
        for clip in clip_paths: f.write(f"file '{clip}'\n")
    cmd = ["ffmpeg", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", "-y", output_path]
    subprocess.run(cmd, capture_output=True)
    os.remove(list_path)
    log(f"[OK] Final video created: {output_path}")
    return output_path

def phase_script(pdf_path, job_dir, language="en"):
    slides_folder = f"{job_dir}/slides"
    image_paths = pdf_to_images(pdf_path, slides_folder)
    scripts_data = []
    for i, img_path in enumerate(image_paths, 1):
        slide_text = extract_text_from_slide(pdf_path, i - 1)
        script = generate_script(slide_text, language=language)
        if not script: script = f"Let's take a look at slide {i}."
        scripts_data.append({"index": i, "image": img_path, "script": script})
    
    with open(f"{job_dir}/scripts.json", "w") as f: json.dump(scripts_data, f)
    log(f"[OK] {len(scripts_data)} scripts saved")
    return True

def phase_render(job_dir, output_video, language="en"):
    with open(f"{job_dir}/scripts.json", "r") as f: scripts_data = json.load(f)
    temp_audio_dir = f"{job_dir}/temp_audio"
    temp_clips_dir = f"{job_dir}/temp_clips"
    os.makedirs(temp_audio_dir, exist_ok=True)
    os.makedirs(temp_clips_dir, exist_ok=True)
    
    clips = []
    for entry in scripts_data:
        i, script, image_path = entry["index"], entry["script"], entry["image"]
        audio_path = f"{temp_audio_dir}/slide_{i:02d}.mp3"
        audio_file = generate_audio(script, audio_path, language=language)
        if not audio_file: continue
        duration = get_audio_duration(audio_file)
        clip_path = f"{temp_clips_dir}/clip_{i:02d}.mp4"
        clip = create_clip(image_path, audio_file, duration, clip_path)
        if clip: clips.append(clip)
        
    if not clips:
        log("[ERROR] No clips created")
        return False
        
    os.makedirs(os.path.dirname(output_video) or ".", exist_ok=True)
    concat_clips(clips, output_video)
    return True

def run_auto(pdf_path, output_video, job_dir, language="en"):
    if not phase_script(pdf_path, job_dir, language=language): return False
    return phase_render(job_dir, output_video, language=language)
