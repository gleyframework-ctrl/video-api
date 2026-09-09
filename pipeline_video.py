import os
import sys
import subprocess
from openai import OpenAI
import requests
from pypdf import PdfReader
from PIL import Image
import io

# 🔑 API KEYS - Read from Environment Variables
NVIDIA_API_KEY = os.environ.get("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")
CARTESIA_API_KEY = os.environ.get("aee2a343-ab30-430a-b50d-34eaec3dfba6")
CARTESIA_VOICE_ID = os.environ.get("sk_car_j1AAGoyVXQF5pZ7W4zvydX")

if not NVIDIA_API_KEY or not CARTESIA_API_KEY:
    raise ValueError("Missing API keys! Set NVIDIA_API_KEY and CARTESIA_API_KEY in Railway variables.")

def log(msg):
    print(msg)
    sys.stdout.flush()

def pdf_to_images(pdf_path, output_folder="slides"):
    os.makedirs(output_folder, exist_ok=True)
    reader = PdfReader(pdf_path)
    image_paths = []
    for i, page in enumerate(reader.pages):
        image_found = False
        for img in page.images:
            try:
                image_data = img.data
                pil_image = Image.open(io.BytesIO(image_data))
                image_path = f"{output_folder}/slide_{i+1:02d}.png"
                pil_image.save(image_path)
                image_paths.append(image_path)
                log(f"[OK] Saved: {image_path}")
                image_found = True
                break
            except:
                continue
        if not image_found:
            log(f"[WARNING] No image found for page {i+1}, creating placeholder")
            img = Image.new('RGB', (800, 600), color='white')
            image_path = f"{output_folder}/slide_{i+1:02d}.png"
            img.save(image_path)
            image_paths.append(image_path)
    return image_paths

def generate_script(slide_text):
    log("[AI] Writing script with NVIDIA Llama 3.2...")
    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=NVIDIA_API_KEY,
    )
    prompt = f"""
You are an expert video scriptwriter.
Audience: Entrepreneurs. Tone: Energetic and conversational.
Slide text: "{slide_text}"
Task: Write a short, engaging spoken script (max 80 words).
Use contractions. No visual cues. Output ONLY the raw spoken text.
"""
    try:
        completion = client.chat.completions.create(
            model="meta/llama-3.2-11b-vision-instruct",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=200,
            timeout=300,
        )
        script = completion.choices[0].message.content.strip()
        log(f"[OK] Script generated")
        return script
    except Exception as e:
        log(f"[ERROR] NVIDIA API error: {e}")
        return None

def generate_audio(script, output_path):
    log("[AUDIO] Generating cloned voice audio with Cartesia...")
    url = "https://api.cartesia.ai/tts/bytes"
    headers = {
        "Cartesia-Version": "2024-06-10",
        "X-API-Key": CARTESIA_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "model_id": "sonic-2",
        "voice": {"mode": "id", "id": CARTESIA_VOICE_ID},
        "output_format": {"container": "mp3", "bit_rate": 128000, "sample_rate": 44100},
        "transcript": script,
        "language": "en",
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        if response.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(response.content)
            log(f"[OK] Audio saved: {output_path}")
            return output_path
        else:
            log(f"[ERROR] Cartesia error: {response.status_code}")
            return None
    except Exception as e:
        log(f"[ERROR] Cartesia request failed: {e}")
        return None

def get_audio_duration(audio_path):
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 10.0

def create_clip(image_path, audio_path, duration, output_path):
    duration = max(duration, 0.5)
    cmd = [
        "ffmpeg", "-loop", "1",
        "-i", image_path,
        "-i", audio_path,
        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
        "-c:v", "libx264",
        "-t", str(duration + 0.5),
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        "-y",
        output_path
    ]
    subprocess.run(cmd, capture_output=True)
    log(f"[OK] Clip saved: {output_path}")
    return output_path

def concat_clips(clip_paths, output_path):
    list_path = "filelist.txt"
    with open(list_path, "w") as f:
        for clip in clip_paths:
            f.write(f"file '{clip}'\n")
    cmd = [
        "ffmpeg", "-f", "concat",
        "-safe", "0",
        "-i", list_path,
        "-c", "copy",
        "-y",
        output_path
    ]
    subprocess.run(cmd, capture_output=True)
    os.remove(list_path)
    log(f"[OK] Final video created: {output_path}")
    return output_path

def process_slide(image_path, index):
    log(f"[PROCESS] Slide {index}...")
    slide_text = f"Slide {index}: The Future of Automation"
    script = generate_script(slide_text)
    if not script:
        return None
    os.makedirs("temp_audio", exist_ok=True)
    audio_path = f"temp_audio/slide_{index:02d}.mp3"
    audio_file = generate_audio(script, audio_path)
    if not audio_file:
        return None
    duration = get_audio_duration(audio_file)
    log(f"[TIME] Duration: {duration:.2f}s")
    os.makedirs("temp_clips", exist_ok=True)
    clip_path = f"temp_clips/clip_{index:02d}.mp4"
    create_clip(image_path, audio_file, duration, clip_path)
    return clip_path

def run_pipeline(pdf_path, output_video):
    if not os.path.exists(pdf_path):
        log(f"[ERROR] PDF not found: {pdf_path}")
        return False
    log("[START] Starting Video Pipeline...")
    image_paths = pdf_to_images(pdf_path)
    log(f"[OK] {len(image_paths)} slides extracted")
    clips = []
    for i, img in enumerate(image_paths, 1):
        clip = process_slide(img, i)
        if clip:
            clips.append(clip)
    if clips:
        concat_clips(clips, output_video)
        log("[OK] SUCCESS! Video created: " + output_video)
        return True
    else:
        log("[ERROR] No clips created.")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        log("Usage: python pipeline_video.py <pdf_file> [output_video]")
        sys.exit(1)
    pdf_file = sys.argv[1]
    output_video = sys.argv[2] if len(sys.argv) > 2 else "final_video.mp4"
    success = run_pipeline(pdf_file, output_video)
    sys.exit(0 if success else 1)
