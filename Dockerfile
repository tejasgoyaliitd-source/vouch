# Vouch on Vercel: one container that serves the API and the built web app.

# 1. Build the React app
FROM node:24-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# 2. Python app with Tesseract OCR (Vercel's plain Python runtime cannot install it)
FROM python:3.14-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
 && (apt-get install -y --no-install-recommends libglib2.0-0t64 || apt-get install -y --no-install-recommends libglib2.0-0) \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ap backend/ap
COPY backend/main.py backend/main.py
COPY data data
COPY samples samples
COPY --from=web /web/dist frontend/dist

# Hosted settings: everything written goes under /tmp (the only disk a serverless container can be sure to write),
# copies of files are kept in the database, and runs start inside the live stream.
ENV TESSERACT_CMD=/usr/bin/tesseract \
    AP_DB=/tmp/vouch.db \
    AP_STORAGE=/tmp/vouch-storage \
    PYTHONDONTWRITEBYTECODE=1 \
    RUN_IN_STREAM=1 \
    PYTHONUNBUFFERED=1

CMD ["sh", "-c", "uvicorn main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-80}"]
