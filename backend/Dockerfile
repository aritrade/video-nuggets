FROM python:3.11-slim

# Runtime deps for the render pipeline:
#   ffmpeg        -> video/audio composition
#   tesseract-ocr -> OCR for image uploads (optional path)
#   fonts-dejavu  -> PIL text rendering on slides
# LibreOffice is intentionally NOT installed; the optional "download slides as
# PDF" path degrades gracefully without it (PPTX download still works).
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    tesseract-ocr \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p output/videos output/slides output/audio output/thumbnails \
    output/transcripts output/visualizations output/uploads output/chromadb

# Pre-warm ChromaDB's default ONNX embedding model so the first chat request
# after a cold start doesn't pay the one-time download cost.
RUN python -c "import chromadb; c=chromadb.Client(); col=c.get_or_create_collection('warm'); col.add(documents=['warm up the embedder'], ids=['1'])" || true

ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
