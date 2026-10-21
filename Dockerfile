FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Kolkata \
    APP_TIMEZONE=Asia/Kolkata

# tzdata: the order cut-off and the 4 AM dispatch need Indian time
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend backend
COPY frontend frontend

# Run as a normal user; /data holds the database and photos
RUN useradd --uid 1000 --create-home dairy \
    && mkdir -p /data/uploads frontend/download \
    && chown -R dairy:dairy /data /app
USER dairy

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

CMD ["python", "backend/run.py"]
