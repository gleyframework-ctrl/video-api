FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p uploads outputs slides temp_audio temp_clips

EXPOSE 8080

# Fixed port, no environment-variable dependency — eliminates the mismatch entirely.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
