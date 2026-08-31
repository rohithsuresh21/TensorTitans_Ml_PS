# SentinelIQ - CPU-first container image.
# For NVIDIA GPU inference see docker-compose.gpu.yml (nvidia-container-toolkit).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# OpenCV runtime libraries for python:3.11-slim.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app ./app
COPY run.py config.py export_tensorrt.py ./

# Runtime data + media volumes (set in docker-compose).
RUN mkdir -p /app/models /app/videos /app/data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["python", "run.py"]