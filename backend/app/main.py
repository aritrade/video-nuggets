from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.models.database import init_db, SessionLocal
from app.api.videos import router as videos_router
from app.api.uploads import router as uploads_router
from app.api.monitor import router as monitor_router
from app.api.chat import router as chat_router
from app.api.auth import router as auth_router
from app.api.playlists import router as playlists_router
from app.scheduler import start_scheduler, stop_scheduler
from app.seed import seed_if_empty
from app import config


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        seed_if_empty(db)
    finally:
        db.close()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Video Nuggets OS",
    description="Turn any document into a narrated, auto-advancing video lesson with charts and a Q&A bot.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static/videos", StaticFiles(directory=str(config.VIDEOS_DIR)), name="videos")
app.mount("/static/thumbnails", StaticFiles(directory=str(config.THUMBNAILS_DIR)), name="thumbnails")

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(playlists_router, prefix="/api/playlists", tags=["playlists"])
app.include_router(videos_router, prefix="/api/videos", tags=["videos"])
app.include_router(uploads_router, prefix="/api/uploads", tags=["uploads"])
app.include_router(monitor_router, prefix="/api/monitor", tags=["monitor"])
app.include_router(chat_router, prefix="/api/chat", tags=["chat"])


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "video-nuggets-os",
        "mode": "full-backend",
        "llm_provider": config.LLM_PROVIDER,
        "demo_mode": config.DEMO_MODE,
        "live_generation": True,
    }


# ── Serve the built SPA (all-in-one deploy) ──────────────────────────────────
# When FRONTEND_DIST points at a Vite build, this process serves the frontend
# from the same origin as the API, so a single Render URL is the whole app
# (live upload + generation included). Registered last so it never shadows the
# /api/* routers or the /static/* mounts above.
_DIST = Path(config.FRONTEND_DIST) if config.FRONTEND_DIST else None
if _DIST and _DIST.is_dir():
    _INDEX = _DIST / "index.html"
    _assets = _DIST / "assets"
    if _assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        if full_path.startswith(("api/", "static/")):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = _DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_INDEX)
