import os
import sys
import subprocess
from openai import OpenAI
import requests
from pypdf import PdfReader
from PIL import Image
import io

# ==========================================
# 🔑 API KEYS — Read from Environment Variables
# ==========================================
# These are set in Railway → Variables
# DO NOT hardcode keys in this file!
NVIDIA_API_KEY = os.environ["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"]
CARTESIA_API_KEY = os.environ["sk_car_SvzBq8wZyZ2jE12aHGnift"]
CARTESIA_VOICE_ID = os.environ["aee2a343-ab30-430a-b50d-34eaec3dfba6"]


def log(msg):
    print(msg)
    sys.stdout.flush()


def pdf_to_images(pdf_path, output_folder="slides"):
    log(f"[PDF] Extracting images from: {pdf_path}")
    os.makedirs(output_folder, exist_ok=True)
    reader = PdfReader(pdf_path)
    image_paths = []

    for i, page in enumerate(reader.pages):
        image_found = False
        for img in page.images:
            try:
                image_data = img.data
                pil_image = Image.open(io.BytesIO(image_data))
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
                continue

        if not image_found:
            log(f"[WARN] No image on page {i+1}, creating placeholder")
            img = Image.new('RGB', (1920, 1080), color=(255, 255, 255))
            image_path = f"{output_folder}/slide_{i+1:02d}.png"
            img.save(image_path, "PNG")
            image_paths.append(image_path)

    log(f"[OK] Total slides extracted: {len(image_paths)}")
    return image_paths


def generate_script(slide_text):
    log("[AI] Generating script with NVIDIA Llama 3.2...")
    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=NVIDIA_API_KEY,
    )

    prompt = f"""
You are an expert video scriptwriter for entrepreneurs.

Slide content:
{slide_text}

Task: Write an engaging spoken script (max 80 words).
Requirements:
- Energetic, conversational tone
- Use contractions (you'll, we're, don't)
- No visual directions
- Output ONLY the raw spoken text
- Make it sound natural when spoken aloud
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
        log(f"[OK] Script generated ({len(script)} chars)")
        return script
    except Exception as e:
        log(f"[ERROR] NVIDIA API failed: {e}")
        return None


def generate_audio(script, output_path):
    log("[AUDIO] Generating cloned voice with Cartesia...")
    url = "https://api.cartesia.ai/tts/bytes"
    headers = {
        "Cartesia-Version": "2024-06-10",
        "X-API-Key": CARTESIA_API_KEY,
        "Content-Type": "application/json",
    }

    payload = {
        "model_id": "sonic-2",
        "voice": {"mode": "id", "id": CARTESIA_VOICE_ID},
        "output_format": {
            "container": "mp3",
            "bit_rate": 128000,
            "sample_rate": 44100
        },
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
            log(f"[ERROR] Cartesia API error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        log(f"[ERROR] Cartesia request failed: {e}")
        return None


def get_audio_duration(audio_path):
    log(f"[TIME] Measuring duration of {audio_path}")
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        duration = float(result.stdout.strip())
        log(f"[TIME] Duration: {duration:.2f}s")
        return duration
    except Exception as e:
        log(f"[WARN] ffprobe failed: {e}, defaulting to 10s")
        return 10.0


def create_clip(image_path, audio_path, duration, output_path):
    log(f"[VIDEO] Creating clip: {output_path}")
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

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        log(f"[OK] Clip created: {output_path}")
        return output_path
    else:
        log(f"[ERROR] FFmpeg failed: {result.stderr}")
        return None


def concat_clips(clip_paths, output_path):
    log(f"[MERGE] Combining {len(clip_paths)} clips...")

    list_path = "filelist.txt"
    with open(list_path, "w") as f:
        for clip in clip_paths:
            f.write(f"file '{clip.replace(os.sep, '/')}'\n")

    cmd = [
        "ffmpeg", "-f", "concat",
        "-safe", "0",
        "-i", list_path,
        "-c", "copy",
        "-y", output_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if os.path.exists(list_path):
        os.remove(list_path)

    if result.returncode == 0:
        log(f"[OK] Final video created: {output_path}")
        return output_path
    else:
        log(f"[ERROR] FFmpeg concat failed: {result.stderr}")
        return None


def extract_text_from_slide(pdf_path, slide_index):
    try:
        reader = PdfReader(pdf_path)
        if slide_index < len(reader.pages):
            page = reader.pages[slide_index]
            text = page.extract_text()
            return text.strip() if text else f"Slide {slide_index + 1}"
    except Exception as e:
        log(f"[WARN] Could not extract text: {e}")
    return f"Slide {slide_index + 1}"


def process_slide(image_path, index, pdf_path):
    log(f"\n[PROCESS] ========== Slide {index} ==========")
    slide_text = extract_text_from_slide(pdf_path, index - 1)
    log(f"[TEXT] {slide_text[:100]}...")

    script = generate_script(slide_text)
    if not script:
        log("[ERROR] Script generation failed")
        return None

    os.makedirs("temp_audio", exist_ok=True)
    audio_path = f"temp_audio/slide_{index:02d}.mp3"
    audio_file = generate_audio(script, audio_path)
    if not audio_file:
        log("[ERROR] Audio generation failed")
        return None

    duration = get_audio_duration(audio_file)

    os.makedirs("temp_clips", exist_ok=True)
    clip_path = f"temp_clips/clip_{index:02d}.mp4"
    clip = create_clip(image_path, audio_file, duration, clip_path)
    if not clip:
        log("[ERROR] Clip creation failed")
        return None
    return clip_path


def run_pipeline(pdf_path, output_video):
    log("\n" + "="*60)
    log("[START] AI VIDEO GENERATION PIPELINE")
    log("="*60)

    if not os.path.exists(pdf_path):
        log(f"[ERROR] PDF not found: {pdf_path}")
        return False

    log(f"[INPUT] PDF: {pdf_path}")
    log(f"[OUTPUT] Video: {output_video}")

    image_paths = pdf_to_images(pdf_path)
    if not image_paths:
        log("[ERROR] No slides extracted")
        return False
    log(f"[OK] {len(image_paths)} slides ready")

    clips = []
    for i, img_path in enumerate(image_paths, 1):
        clip = process_slide(img_path, i, pdf_path)
        if clip:
            clips.append(clip)
        else:
            log(f"[WARN] Slide {i} failed, continuing...")

    if not clips:
        log("[ERROR] No clips created successfully")
        return False

    os.makedirs(os.path.dirname(output_video) if os.path.dirname(output_video) else ".", exist_ok=True)
    final_video = concat_clips(clips, output_video)

    if final_video and os.path.exists(final_video):
        file_size = os.path.getsize(final_video) / (1024 * 1024)
        log("\n" + "="*60)
        log("[SUCCESS] Video generation complete!")
        log(f"[FILE] {final_video}")
        log(f"[SIZE] {file_size:.2f} MB")
        log("="*60)
        return True
    else:
        log("[ERROR] Final video creation failed")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        log("Usage: python pipeline_video.py <pdf_file> [output_video]")
        sys.exit(1)

    pdf_file = sys.argv[1]
    output_video = sys.argv[2] if len(sys.argv) > 2 else "final_video.mp4"

    success = run_pipeline(pdf_file, output_video)
    sys.exit(0 if success else 1)
