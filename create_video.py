import requests
import json
import time
import os

# ======================
# EDIT YOUR SCRIPTS HERE
# ======================
# One script per slide, in order
scripts = [
    "مرحباً، اليوم سنتعلم عن إدارة الوقت.",
    "الخطوة الأولى: حدد أولوياتك بوضوح.",
    "الآن، خذ ورقة واكتب أهم 3 مهام اليوم.",
    "لاحظ كيف تشعر بعد تنظيم وقتك.",
    "تذكر: التكرار هو المفتاح للنجاح."
]

# ======================
# CONFIGURATION
# ======================
PDF_FILE = "test_presentation.pdf"  # Your PDF file name
API_URL = "https://video-api-production-c928.up.railway.app"
LANGUAGE = "ar"  # 'ar' for Arabic, 'en' for English

# ======================
# MAIN PROCESS
# ======================

print("=" * 60)
print("🎬 AI VIDEO GENERATOR")
print("=" * 60)

# Check if PDF exists
if not os.path.exists(PDF_FILE):
    print(f"❌ Error: {PDF_FILE} not found!")
    print("Please make sure your PDF file is in the same folder.")
    exit()

print(f"\n📄 Using PDF: {PDF_FILE}")
print(f"📝 Number of scripts: {len(scripts)}")
print(f"🌍 Language: {LANGUAGE}")

# Upload to API
print("\n⏳ Uploading to Railway...")
try:
    with open(PDF_FILE, 'rb') as pdf_file:
        files = {'file': (PDF_FILE, pdf_file, 'application/pdf')}
        data = {
            'scripts': json.dumps(scripts),
            'language': LANGUAGE
        }
        
        response = requests.post(
            f"{API_URL}/create-video",
            files=files,
            data=data,
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            job_id = result.get('job_id')
            print(f"\n✅ Upload successful!")
            print(f"🎯 Job ID: {job_id}")
            print(f"📊 Status: {result.get('status')}")
            
            # Wait and check status
            print("\n⏳ Generating video (this takes 30-60 seconds)...")
            time.sleep(30)
            
            # Check status
            max_attempts = 10
            for attempt in range(max_attempts):
                status_response = requests.get(f"{API_URL}/status/{job_id}")
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    status = status_data.get('status')
                    
                    if status == 'completed':
                        print(f"\n🎉 Video generation completed!")
                        
                        # Download video
                        print("\n⏳ Downloading video...")
                        download_response = requests.get(f"{API_URL}/download/{job_id}/final_video.mp4")
                        
                        if download_response.status_code == 200:
                            output_file = f"video_{job_id}.mp4"
                            with open(output_file, 'wb') as f:
                                f.write(download_response.content)
                            print(f"\n✅ Video downloaded: {output_file}")
                            print("=" * 60)
                            print("🎬 DONE! Your video is ready!")
                            print("=" * 60)
                        else:
                            print(f"❌ Download failed: {download_response.status_code}")
                        break
                    elif status == 'failed':
                        print(f"\n❌ Video generation failed: {status_data}")
                        break
                    else:
                        print(f"⏳ Still processing... (attempt {attempt + 1}/{max_attempts})")
                        time.sleep(10)
                else:
                    print(f" Waiting... (attempt {attempt + 1}/{max_attempts})")
                    time.sleep(10)
            else:
                print("\n⏳ Video is still processing. Check status later:")
                print(f"{API_URL}/status/{job_id}")
        else:
            print(f"❌ Upload failed: {response.status_code}")
            print(f"Response: {response.text}")
            
except Exception as e:
    print(f"❌ Error: {e}")
    print("Make sure:")
    print("1. Your PDF file exists")
    print("2. You have internet connection")
    print("3. Railway API is accessible")
