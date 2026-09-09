FROM python:3.11-slim

WORKDIR /app

# Install FFmpeg (CRITICAL for video processing)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all files
COPY . .

# Create directories
RUN mkdir -p uploads outputs slides temp_audio temp_clips

# Expose port
EXPOSE 8000

# Fix: Use shell form to expand $PORT variable
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
