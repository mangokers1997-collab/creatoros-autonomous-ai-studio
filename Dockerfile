FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CREATOROS_DB_PATH=/data/creatoros.db \
    CREATOROS_MEDIA_DIR=/data/media \
    CREATOROS_RENDER_DIR=/data/renders \
    CREATOROS_TOKEN_DIR=/data/secure_tokens \
    CREATOROS_FONT_FILE=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg fonts-dejavu-core ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY web ./web

RUN useradd --create-home --uid 10001 creatoros \
    && mkdir -p /data/media /data/renders /data/secure_tokens \
    && chown -R creatoros:creatoros /app /data

USER creatoros
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
