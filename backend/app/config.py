import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
VIDEOS_DIR = OUTPUT_DIR / "videos"
SLIDES_DIR = OUTPUT_DIR / "slides"
AUDIO_DIR = OUTPUT_DIR / "audio"
THUMBNAILS_DIR = OUTPUT_DIR / "thumbnails"
TRANSCRIPTS_DIR = OUTPUT_DIR / "transcripts"
VISUALIZATIONS_DIR = OUTPUT_DIR / "visualizations"
UPLOADS_DIR = OUTPUT_DIR / "uploads"
CHROMA_DIR = OUTPUT_DIR / "chromadb"
# Committed seed assets (pre-rendered demo nuggets + transcripts + chroma index).
SEED_DIR = BASE_DIR / "seed"

for d in [OUTPUT_DIR, VIDEOS_DIR, SLIDES_DIR, AUDIO_DIR, THUMBNAILS_DIR,
          TRANSCRIPTS_DIR, VISUALIZATIONS_DIR, UPLOADS_DIR, CHROMA_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── LLM provider ─────────────────────────────────────────────────────────
# The "simplify to a 6-year-old" step and the NuggetBot chat use, in order:
#   1. Groq (free Llama-3, OpenAI-compatible) when GROQ_API_KEY is set.
#   2. Ollama for local development (set LLM_PROVIDER=ollama).
#   3. A deterministic fallback that always works at zero cost.
# The key only ever lives server-side.
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma2:9b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

LLM_PROVIDER = os.getenv(
    "LLM_PROVIDER",
    "groq" if GROQ_API_KEY else "deterministic",
).lower()

# ── Demo + content monitor ───────────────────────────────────────────────
# This public build ships in demo mode: a seeded library of synthetic,
# neutrally-branded nuggets, open generation, and no external scraping.
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"

# The 24h content monitor is OFF by default. Point it at any docs site by
# setting MONITOR_SOURCE_URL and MONITOR_ENABLED=true.
MONITOR_ENABLED = os.getenv("MONITOR_ENABLED", "false").lower() == "true"
MONITOR_SOURCE_URL = os.getenv("MONITOR_SOURCE_URL", "")
MONITOR_INTERVAL_HOURS = int(os.getenv("MONITOR_INTERVAL_HOURS", "24"))
# Back-compat alias for modules that still import the old name.
NUTANIX_BIBLE_URL = MONITOR_SOURCE_URL

# ── CORS ─────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://localhost:3000",
    ).split(",")
    if o.strip()
]

# ── Narration (Edge TTS) ─────────────────────────────────────────────────
EDGE_TTS_VOICE = os.getenv("EDGE_TTS_VOICE", "en-US-AndrewNeural")
EDGE_TTS_RATE = os.getenv("EDGE_TTS_RATE", "+0%")

# ── Video ────────────────────────────────────────────────────────────────
VIDEO_MAX_DURATION_MINUTES = 12
VIDEO_TARGET_DURATION_MINUTES = 10
VIDEO_RESOLUTION = (1920, 1080)

# Neutral brand palette for charts and slides (purple / teal / accent).
BRAND_COLORS = {
    "dark_purple": "#4B00AA",
    "light_purple": "#7855FA",
    "teal": "#1FDDE9",
    "green": "#92DD23",
    "coral": "#FF9178",
    "dark_text": "#131313",
    "white": "#FFFFFF",
    "dark_blue": "#0092B0",
    "deep_purple": "#391699",
}

# ── RAG ──────────────────────────────────────────────────────────────────
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
