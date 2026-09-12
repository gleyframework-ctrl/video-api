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
    log(f"[AI] Writing script with NVIDIA Llama 3.2 for language: {language}...")
    client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=NVIDIA_API_KEY)
    lang_name = LANGUAGE_NAMES.get(language, language)

    # WINNING SCRIPT PATTERN (Example structure to follow)
    winning_script_pattern = """مرحباً، وصلنا اليوم إلى اليوم الأول من التحدي.

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
        prompt = f"""You are an expert video scriptwriter who follows EXACT patterns.

I will provide you with:
1. A SLIDE/REFERENCE that determines WHAT the script says (the content)
2. A WINNING SCRIPT that determines HOW the script is written (the structure/pattern)

YOUR JOB:
- Extract the STRUCTURE from the winning script (opening, transitions, sentence rhythm, paragraph flow, question placement, closing)
- Extract the CONTENT from the slide (topic, exercises, instructions, reflections)
- Create a NEW script that uses the WINNING STRUCTURE with the SLIDE CONTENT

SLIDE CONTENT:
"{slide_text}"

WINNING SCRIPT PATTERN (STUDY THIS CAREFULLY):
{winning_script_pattern}

CRITICAL RULES:

**RULE 1: THE SLIDE IS THE CONTENT SOURCE**
- The slide determines the topic, exercises, steps, instructions, reflections
- Do NOT change the slide's topic
- Do NOT replace the slide's exercises
- Do NOT add exercises from the winning script
- Do NOT invent new exercises
- Do NOT mix content from different topics
- If the slide says "Topic X", the entire script must be about "Topic X"

**RULE 2: THE WINNING SCRIPT IS LOCKED**
- Preserve the EXACT structure: opening approach, transitions, sentence rhythm
- Preserve the paragraph flow and pacing
- Preserve question placement and style
- Preserve reflection transitions
- Preserve closing style
- Preserve short-sentence rhythm
- Preserve conversational flow
- Do NOT create your own structure
- Do NOT invent a new format

**RULE 3: THE FORMULA**
WINNING SCRIPT = STRUCTURE + RHYTHM + WRITING STYLE
SLIDE = TOPIC + EXERCISE + INSTRUCTIONS + REFLECTION
FINAL SCRIPT = WINNING STRUCTURE + SLIDE CONTENT

**RULE 4: NO "HELPFUL" CHANGES**
- Do NOT think "I can make this better"
- Do NOT add explanations
- Do NOT reorganize
- Do NOT make it more creative
- Do NOT turn it into an essay
- Do NOT make sentences longer
- FOLLOW THE SLIDE + FOLLOW THE PATTERN

**RULE 5: VOICE-OVER REQUIREMENTS**
- Keep short sentences
- Natural pauses
- Conversational flow
- Emotional pacing
- Direct address to viewer
- Clear instructions

**QUALITY CHECK BEFORE RESPONDING:**
1. Is every sentence directly related to the slide content?
2. Does the script follow the winning script's sequence?
3. Did you preserve the sentence rhythm?
4. Did you preserve the transitions?
5. Did you preserve the reflection style?
6. Did you preserve the closing style?
7. If I compared the structure with the winning demo, would it feel like the same pattern?

OUTPUT:
Give me ONLY the finished voice-over script in {lang_name}.
No analysis. No explanation. No commentary.
Just the final copy.

Write the script in {lang_name} using the winning pattern structure applied to the slide content above."""
    else:
        prompt = f"""أنت خبير في كتابة النصوص للفيديو تتبع أنماطاً دقيقة.

سأقدم لك:
1. شريحة/مرجع يحدد ماذا يقول النص (المحتوى)
2. نص ناجح يحدد كيف يُكتب النص (الهيكل/النمط)

مهمتك:
- استخرج الهيكل من النص الناجح (البداية، الانتقالات، إيقاع الجمل، تدفق الفقرات، Placement الأسئلة، الخاتمة)
- استخرج المحتوى من الشريحة (الموضوع، التمارين، التعليمات، التأملات)
- أنشئ نصاً جديداً يستخدم الهيكل الناجح مع محتوى الشريحة

محتوى الشريحة:
"{slide_text}"

النمط الناجح (ادرسه بعناية):
{winning_script_pattern}

القواعد الحاسمة:

**القاعدة 1: الشريحة هي مصدر المحتوى**
- الشريحة تحدد الموضوع، التمارين، الخطوات، التعليمات، التأملات
- لا تغير موضوع الشريحة
- لا تستبدل تمارين الشريحة
- لا تضف تمارين من النص الناجح
- لا تختلق تمارين جديدة
- لا تخلط محتوى من مواضيع مختلفة
- إذا قالت الشريحة "الموضوع س"، النص بأكمله يجب أن يكون عن "الموضوع س"

**القاعدة 2: النص الناجح ثابت**
- احفظ الهيكل تماماً: نهج البداية، الانتقالات، إيقاع الجمل
- احفظ تدفق الفقرات والإيقاع
- احفظ Placement الأسئلة والأسلوب
- احفظ انتقالات التأمل
- احفظ أسلوب الخاتمة
- احفظ إيقاع الجمل القصيرة
- احفظ التدفق الحواري
- لا تنشئ هيكلك الخاص
- لا تختلق تنسيقاً جديداً

**القاعدة 3: الصيغة**
النص الناجح = الهيكل + الإيقاع + أسلوب الكتابة
الشريحة = الموضوع + التمرين + التعليمات + التأمل
النص النهائي = الهيكل الناجح + محتوى الشريحة

**القاعدة 4: لا تغييرات "مفيدة"**
- لا تفكر "يمكنني تحسين هذا"
- لا تضف شرحاً
- لا تعيد التنظيم
- لا تجعله أكثر إبداعاً
- لا تحوله إلى مقال
- لا تجعل الجمل أطول
- اتبع الشريحة + اتبع النمط

**القاعدة 5: متطلبات التعليق الصوتي**
- احفظ الجمل القصيرة
- وقفات طبيعية
- تدفق حواري
- إيقاع عاطفي
- مخاطبة مباشرة للمشاهد
- تعليمات واضحة

**فحص الجودة قبل الرد:**
1. هل كل جملة مرتبطة مباشرة بمحتوى الشريحة؟
2. هل النص يتبع تسلسل النص الناجح؟
3. هل حفظت إيقاع الجمل؟
4. هل حفظت الانتقالات؟
5. هل حفظت أسلوب التأمل؟
6. هل حفظت أسلوب الخاتمة؟
7. إذا قارنت الهيكل مع النموذج الناجح، هل سيبدو وكأنه نفس النمط؟

المخرج:
أعطني النص النهائي فقط باللغة {lang_name}.
بدون تحليل. بدون شرح. بدون تعليق.
فقط النسخة النهائية.

اكتب النص باللغة {lang_name} باستخدام هيكل النمط الناجح المطبق على محتوى الشريحة أعلاه."""

    try:
        completion = client.chat.completions.create(
            model="meta/llama-3.2-11b-vision-instruct",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=400,
            timeout=300,
        )
        script = completion.choices[0].message.content.strip()
        log("[OK] Script generated")
        return script
    except Exception as e:
        log(f"[ERROR] NVIDIA API error: {e}")
        return None

def generate_audio(script, output_path, language="en"):
    log(f"[AUDIO] STARTING audio generation for: {output_path}")
    log(f"[AUDIO] Language: {language}")
    log(f"[AUDIO] Script length: {len(script)} chars")
    log(f"[AUDIO] CARTESIA_API_KEY present: {bool(CARTESIA_API_KEY)}")
    log(f"[AUDIO] CARTESIA_VOICE_ID: {CARTESIA_VOICE_ID}")
    
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
        log(f"[AUDIO] Sending request to Cartesia...")
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        log(f"[AUDIO] Cartesia response status: {response.status_code}")
        
        if response.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(response.content)
            file_size = os.path.getsize(output_path)
            log(f"[AUDIO] OK Audio saved: {output_path} (size: {file_size} bytes)")
            return output_path
        else:
            log(f"[AUDIO] ERROR Cartesia error: {response.status_code}")
            log(f"[AUDIO] Cartesia response body: {response.text[:500]}")
            return None
    except Exception as e:
        log(f"[AUDIO] ERROR Cartesia request failed: {type(e).__name__}: {e}")
        return None

def get_audio_duration(audio_path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 10.0

def create_clip(image_path, audio_path, duration, output_path):
    log(f"[CLIP] STARTING clip creation")
    log(f"[CLIP] Image exists: {os.path.exists(image_path)}")
    log(f"[CLIP] Audio exists: {os.path.exists(audio_path)}")
    log(f"[CLIP] Audio size: {os.path.getsize(audio_path) if os.path.exists(audio_path) else 0} bytes")
    log(f"[CLIP] Duration: {duration}s")
    
    duration = max(duration, 0.5)
    
    # IMPROVED QUALITY: Fast preset (still safe for Railway) with better CRF
    cmd = [
        "ffmpeg", 
        "-loop", "1", 
        "-i", image_path, 
        "-i", audio_path,
        "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264", 
        "-preset", "fast",  # Upgraded from "ultrafast" to "fast" for better quality
        "-crf", "23",       # Better quality than 28 (lower = better)
        "-t", str(duration + 0.5), 
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-threads", "1",
        "-shortest", "-y", output_path
    ]
    
    log(f"[CLIP] Running FFmpeg command...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        log(f"[CLIP] ERROR FFmpeg failed (return code: {result.returncode})")
        log(f"[CLIP] FFmpeg stderr: {result.stderr[:500]}")
        return None
    else:
        if os.path.exists(output_path):
            size = os.path.getsize(output_path)
            log(f"[CLIP] OK Clip saved: {output_path} (size: {size} bytes)")
            return output_path
        else:
            log(f"[CLIP] ERROR FFmpeg reported success but file not found")
            return None

def concat_clips(clip_paths, output_path):
    output_dir = os.path.dirname(output_path)
    os.makedirs(output_dir, exist_ok=True)
    list_path = os.path.join(output_dir, "filelist.txt")
    
    log(f"[CONCAT] Creating filelist at: {list_path}")
    log(f"[CONCAT] Clips to concatenate: {clip_paths}")
    
    with open(list_path, "w") as f:
        for clip in clip_paths:
            abs_clip = os.path.abspath(clip)
            f.write(f"file '{abs_clip}'\n")
            log(f"[CONCAT] Added to list: {abs_clip}")
    
    # IMPROVED QUALITY SETTINGS
    cmd = [
        "ffmpeg", 
        "-f", "concat", 
        "-safe", "0", 
        "-i", list_path,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-threads", "1",
        "-y", output_path
    ]
    
    log(f"[CONCAT] Running FFmpeg concat command...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        log(f"[ERROR] FFmpeg concat failed: {result.stderr}")
        if os.path.exists(list_path):
            os.remove(list_path)
        return False
    
    if os.path.exists(output_path):
        file_size = os.path.getsize(output_path)
        log(f"[OK] Final video created: {output_path} (size: {file_size} bytes)")
        if os.path.exists(list_path):
            os.remove(list_path)
        return True
    else:
        log(f"[ERROR] FFmpeg reported success but file not found at: {output_path}")
        if os.path.exists(list_path):
            os.remove(list_path)
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
