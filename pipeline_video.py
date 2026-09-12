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
CARTESIA_VOICE_ID = os.environ.get("CARTESIA_VOICE_ID", "2a1938fe-6a4c-4fa0-86a7-dd585a5f7211")

if not NVIDIA_API_KEY or not CARTESIA_API_KEY:
    raise ValueError("Missing API keys!")

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
                if pil_image.mode != 'RGB':
                    pil_image = pil_image.convert('RGB')
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
            img = Image.new('RGB', (1280, 720), color=(255, 255, 255))
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
    """SIMPLIFIED: Uses winning pattern without heavy validation"""
    log(f"[AI] Generating script for language: {language}...")
    client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=NVIDIA_API_KEY)
    lang_name = LANGUAGE_NAMES.get(language, language)

    # THE WINNING PATTERN (Arabic example from your successful videos)
    winning_pattern = """مرحباً، وصلنا اليوم إلى اليوم الأول من التحدي.

اليوم سنبدأ بشيء بسيط.

شيء لا يحتاج إلى الكثير.

فقط بضع دقائق لنفسك.

والآن، خذي لحظة...

اجلسي بهدوء.

ثم اسألي نفسك:

ماذا أشعر الآن؟

لا تحاولي تغيير الإجابة.

فقط لاحظي."""

    if language == "en":
        prompt = f"""You are an expert video scriptwriter. Follow this WRITING PATTERN exactly:

{winning_pattern}

Now write a script about THIS CONTENT:
"{slide_text}"

RULES:
1. Use the SAME structure, rhythm, and style as the pattern
2. But write about the content provided (not the pattern's topic)
3. Keep sentences short (8-15 words)
4. Use natural pauses
5. Write in English
6. Output ONLY the final script, no explanations

Write the script now."""
    else:
        prompt = f"""أنت خبير في كتابة النصوص. اتبع نمط الكتابة هذا تماماً:

{winning_pattern}

الآن اكتب نصاً عن هذا المحتوى:
"{slide_text}"

القواعد:
1. استخدم نفس الهيكل والإيقاع والأسلوب مثل النمط
2. لكن اكتب عن المحتوى المقدم (ليس موضوع النمط)
3. اجعل الجمل قصيرة (8-15 كلمة)
4. استخدم وقفات طبيعية
5. اكتب بالعربية
6. أخرج النص النهائي فقط، بدون شرح

اكتب النص الآن."""

    try:
        completion = client.chat.completions.create(
            model="meta/llama-3.2-11b-vision-instruct",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=400,
            timeout=300,
        )
        script = completion.choices[0].message.content.strip()
        log(f"[OK] Script generated ({len(script)} chars)")
        return script
    except Exception as e:
        log(f"[ERROR] NVIDIA API error: {e}")
        return None

def generate_audio(script, output_path, language="en"):
    log(f"[AUDIO] Generating audio for: {output_path}")
    
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
            file_size = os.path.getsize(output_path)
            log(f"[OK] Audio saved: {output_path} (size: {file_size} bytes)")
            return output_path
        else:
            log(f"[ERROR] Cartesia error: {response.status_code}")
            return None
    except Exception as e:
        log(f"[ERROR] Cartesia request failed: {e}")
        return None

def get_audio_duration(audio_path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 10.0

def create_clip(image_path, audio_path, duration, output_path):
    log(f"[CLIP] Creating clip...")
    
    duration = max(duration, 0.5)
    
    # PROVEN SETTINGS (from working deployment c2ff811c)
    cmd = [
        "ffmpeg", 
        "-loop", "1", 
        "-i", image_path, 
        "-i", audio_path,
        "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264", 
        "-preset", "fast",      # ✅ Proven to work
        "-crf", "20",           # ✅ Good quality
        "-t", str(duration + 0.5), 
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-threads", "1",        # ✅ Prevents memory crash
        "-shortest", "-y", output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        log(f"[ERROR] FFmpeg failed: {result.stderr[:200]}")
        return None
    else:
        if os.path.exists(output_path):
            size = os.path.getsize(output_path)
            log(f"[OK] Clip saved: {output_path} (size: {size} bytes)")
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
    
    # PROVEN SETTINGS
    cmd = [
        "ffmpeg", 
        "-f", "concat", 
        "-safe", "0", 
        "-i", list_path,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", "128k",
        "-threads", "1",
        "-y", output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        log(f"[ERROR] FFmpeg concat failed")
        if os.path.exists(list_path):
            os.remove(list_path)
        return False
    
    if os.path.exists(output_path):
        file_size = os.path.getsize(output_path)
        log(f"[OK] Final video created: {output_path} (size: {file_size} bytes)")
        if os.path.exists(list_path):
            os.remove(list_path)
        return True
    return False

def phase_script(pdf_path, job_dir, language="en"):
    slides_folder = f"{job_dir}/slides"
    image_paths = pdf_to_images(pdf_path, slides_folder)
    scripts_data = []
    for i, img_path in enumerate(image_paths, 1):
        slide_text = extract_text_from_slide(pdf_path, i - 1)
        script = generate_script(slide_text, language=language)
        if not script:
            script = f"Let's take a look at slide {i}."
        scripts_data.append({"index": i, "image": img_path, "script": script})
    
    with open(f"{job_dir}/scripts.json", "w") as f:
        json.dump(scripts_data, f)
    log(f"[OK] {len(scripts_data)} scripts saved")
    return True

def phase_render(job_dir, output_video, language="en"):
    with open(f"{job_dir}/scripts.json", "r") as f:
        scripts_data = json.load(f)
    temp_audio_dir = f"{job_dir}/temp_audio"
    temp_clips_dir = f"{job_dir}/temp_clips"
    os.makedirs(temp_audio_dir, exist_ok=True)
    os.makedirs(temp_clips_dir, exist_ok=True)
    
    clips = []
    for entry in scripts_data:
        i, script, image_path = entry["index"], entry["script"], entry["image"]
        audio_path = f"{temp_audio_dir}/slide_{i:02d}.mp3"
        audio_file = generate_audio(script, audio_path, language=language)
        if not audio_file:
            continue
        duration = get_audio_duration(audio_file)
        clip_path = f"{temp_clips_dir}/clip_{i:02d}.mp4"
        clip = create_clip(image_path, audio_file, duration, clip_path)
        if clip:
            clips.append(clip)
        
    if not clips:
        log("[ERROR] No clips created")
        return False
    
    log(f"[RENDER] Starting concat of {len(clips)} clips...")
    success = concat_clips(clips, output_video)
    
    if success:
        log(f"[RENDER] Video generation completed successfully!")
    else:
        log(f"[RENDER] Video generation failed!")
    
    return success

def run_auto(pdf_path, output_video, job_dir, language="en"):
    if not phase_script(pdf_path, job_dir, language=language):
        return False
    return phase_render(job_dir, output_video, language=language)
