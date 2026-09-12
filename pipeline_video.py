import os
import sys
import json
import subprocess
from openai import OpenAI
import requests
from pypdf import PdfReader
from PIL import Image
import io

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY")
CARTESIA_API_KEY = os.environ.get("CARTESIA_API_KEY")
CARTESIA_VOICE_ID = os.environ.get("CARTESIA_VOICE_ID", "aee2a343-ab30-430a-b50d-34eaec3dfba6")

if not NVIDIA_API_KEY or not CARTESIA_API_KEY:
    raise ValueError("Missing API keys! Set NVIDIA_API_KEY and CARTESIA_API_KEY in Railway variables.")

LANGUAGE_NAMES = {
    "en": "English", "ar": "Arabic", "fr": "French", "es": "Spanish",
    "de": "German", "pt": "Portuguese", "zh": "Chinese", "ja": "Japanese",
    "ko": "Korean", "hi": "Hindi", "tr": "Turkish",
}

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
    log(f"[AI] Writing script with NVIDIA Llama 3.2 for language: {language}...")
    client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=NVIDIA_API_KEY)
    lang_name = LANGUAGE_NAMES.get(language, language)

    if language == "en":
        prompt = f"""
You are an expert video scriptwriter for professional coaching content.
AUDIENCE: Entrepreneurs and business professionals. TONE: Energetic, conversational, and authoritative.
PACING: Write for natural, measured speech delivery - not rushed, not slow.
Slide content: "{slide_text}"
TASK: Write a short, engaging spoken script (EXACTLY 60-80 words) in English.
STYLE REQUIREMENTS: Use clear, concise sentences (8-12 words each). Include natural pauses. Avoid complex jargon. Use active voice. No visual cues.
Output ONLY the raw spoken text - nothing else.
"""
    else:
        prompt = f"""
You are an expert video scriptwriter and translator for professional coaching content.
The slide content below may be written in any language, including English.
Slide content: "{slide_text}"
TASK: Write a short, engaging spoken script (EXACTLY 60-80 words) entirely in {lang_name}, using {lang_name} script/alphabet.
STYLE REQUIREMENTS: Use clear, concise sentences appropriate for {lang_name}. Write for comfortable, professional delivery speed. Avoid complex words. Use active voice. No visual cues. Do NOT include any English words or the original source text.
Output ONLY the {lang_name} spoken text - no English, no notes, no explanations, nothing else.
"""

    try:
        completion = client.chat.completions.create(
            model="meta/llama-3.2-11b-vision-instruct",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=300,
            timeout=300,
        )
        script = completion.choices[0].message.content.strip()
        log("[OK] Script generated")
        return script
    except Exception as e:
        log(f"[ERROR] NVIDIA API error: {e}")
        return None

def generate_audio(script, output_path, language="en"):
    log("[AUDIO] Generating cloned voice audio with Cartesia...")
    url = "https://api.cartesia.ai/tts/bytes"
    headers = {"Cartesia-Version": "2024-06-10", "X-API-Key": CARTESIA_API_KEY, "Content-Type": "application/json"}
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
    cmd = [
        "ffmpeg", "-loop", "1", "-i", image_path, "-i", audio_path,
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        "-t", str(duration + 0.5), "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-shortest", "-y", output_path
    ]
    result = subprocess.run(cmd, text=True)
    if result.returncode != 0:
        log(f"[ERROR] FFmpeg clip creation failed for {output_path}")
    else:
        log(f"[OK] Clip saved: {output_path}")
    return output_path if os.path.exists(output_path) else None

def concat_clips(clip_paths, output_path):
    list_path = "filelist.txt"
    with open(list_path, "w") as f:
        for clip in clip_paths: f.write(f"file '{clip}'\n")
    cmd = [
        "ffmpeg", "-f", "concat", "-safe", "0", "-i", list_path,
        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-y", output_path
    ]
    result = subprocess.run(cmd, text=True)
    os.remove(list_path)
    
    if result.returncode != 0:
        log(f"[ERROR] FFmpeg concat failed. Check Railway logs for FFmpeg errors.")
        return False
        
    log(f"[OK] Final video created: {output_path}")
    return True

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
    success = concat_clips(clips, output_video)
    return success

def run_auto(pdf_path, output_video, job_dir, language="en"):
    if not phase_script(pdf_path, job_dir, language=language): return False
    return phase_render(job_dir, output_video, language=language)