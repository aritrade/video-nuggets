# syntax=docker/dockerfile:1
# All-in-one image: builds the React/Vite frontend and serves it from the same
# FastAPI process that runs the real document-to-video pipeline. One Render web
# service = the whole app, including live upload + generation.

# ── Stage 1: build the frontend ─────────────────────────────────────────────
FROM node:20-slim AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# No VITE_API_URL: the app calls its own origin (/api/*), which on Render is
# this same FastAPI service. (The identical build also works on Vercel, where
# /api/* is the static-demo function instead.)
RUN npm run build

# ── Stage 2: FastAPI backend + media pipeline ───────────────────────────────
FROM python:3.11-slim

# ffmpeg -> compose, tesseract -> OCR for image uploads, fonts -> PIL slides.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    tesseract-ocr \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY --from=frontend /fe/dist ./frontend_dist

RUN mkdir -p output/videos output/slides output/audio output/thumbnails \
    output/transcripts output/visualizations output/uploads output/chromadb

# Pre-warm ChromaDB's default ONNX embedder so the first chat after a cold
# start doesn't pay the one-time model download cost.
RUN python -c "import chromadb; c=chromadb.Client(); col=c.get_or_create_collection('warm'); col.add(documents=['warm up the embedder'], ids=['1'])" || true

ENV FRONTEND_DIST=/app/frontend_dist
ENV DEMO_MODE=true
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
