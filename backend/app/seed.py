"""
Seed the database from the committed, pre-rendered demo library.

On a fresh database (e.g. every cold start on an ephemeral host) this:
  1. creates a default playlist,
  2. inserts one READY, PUBLIC video row per nugget in `seed/manifest.json`
     (insertion order -> ids 1..N, matching the shipped Chroma index),
  3. copies the pre-rendered MP4 / thumbnail / transcript into the served
     output dirs as `{id}.mp4` etc., and
  4. copies the pre-built Chroma vector index so NuggetBot works immediately.

If no seed manifest is present it just ensures a default playlist exists so
live uploads still work.
"""
import json
import shutil
from hashlib import sha256

from sqlalchemy.orm import Session

from app import config
from app.models.database import (
    Video, Playlist, VideoStatus, ContentSource, DifficultyLevel, Visibility,
    User, UserRole,
)

SEED_MANIFEST = config.SEED_DIR / "manifest.json"

# Demo accounts so visitors can explore the admin-only Upload and Monitor
# views. These are intentionally weak, public demo credentials.
_DEMO_USERS = [
    ("admin", "admin123", UserRole.ADMIN, "Demo Admin", "admin@example.com"),
    ("viewer", "viewer123", UserRole.VIEWER, "Demo Viewer", "viewer@example.com"),
]


def _seed_users(db: Session) -> None:
    if db.query(User).count() > 0:
        return
    for username, password, role, display_name, email in _DEMO_USERS:
        db.add(User(
            username=username,
            email=email,
            password_hash=sha256(password.encode()).hexdigest(),
            role=role,
            display_name=display_name,
        ))
    db.commit()
    print("[Seed] Created demo users (admin / viewer)")


def _ensure_default_playlist(db: Session) -> Playlist:
    pl = db.query(Playlist).filter(Playlist.is_default == True).first()  # noqa: E712
    if pl:
        return pl
    pl = Playlist(
        name="Video Nuggets Library",
        description="Auto-generated narrated micro-lessons.",
        is_default=True,
        order_index=0,
    )
    db.add(pl)
    db.commit()
    db.refresh(pl)
    return pl


def _copy_seed_chroma() -> None:
    seed_chroma = config.SEED_DIR / "chromadb"
    if not seed_chroma.exists():
        return
    existing = list(config.CHROMA_DIR.glob("*"))
    if existing:
        return
    shutil.copytree(seed_chroma, config.CHROMA_DIR, dirs_exist_ok=True)
    print("[Seed] Copied pre-built Chroma index")


def seed_if_empty(db: Session) -> None:
    _seed_users(db)

    if db.query(Video).count() > 0:
        return

    playlist = _ensure_default_playlist(db)

    if not SEED_MANIFEST.exists():
        print("[Seed] No seed manifest found; starting with an empty library.")
        return

    _copy_seed_chroma()

    manifest = json.loads(SEED_MANIFEST.read_text())
    nuggets = manifest.get("nuggets", [])

    for order, entry in enumerate(nuggets):
        try:
            difficulty = DifficultyLevel(entry.get("difficulty", "basic"))
        except ValueError:
            difficulty = DifficultyLevel.BASIC

        video = Video(
            title=entry["title"],
            description=entry.get("description"),
            section_key=entry.get("key"),
            source_type=ContentSource.TXT_UPLOAD,
            status=VideoStatus.READY,
            playlist_id=playlist.id,
            difficulty_level=difficulty,
            visibility=Visibility.PUBLIC,
            playlist_order=order,
            duration_seconds=entry.get("duration_seconds"),
        )
        db.add(video)
        db.commit()
        db.refresh(video)

        _attach_media(video, entry)
        db.commit()

    print(f"[Seed] Loaded {len(nuggets)} demo nuggets into the library")


def _attach_media(video: Video, entry: dict) -> None:
    videos_src = config.SEED_DIR / "videos" / entry.get("video_file", "")
    if videos_src.exists():
        dst = config.VIDEOS_DIR / f"{video.id}.mp4"
        shutil.copy(videos_src, dst)
        video.video_path = str(dst)

    thumb_src = config.SEED_DIR / "thumbnails" / entry.get("thumbnail_file", "")
    if thumb_src.exists():
        dst = config.THUMBNAILS_DIR / f"{video.id}.png"
        shutil.copy(thumb_src, dst)
        video.thumbnail_path = str(dst)

    transcript_src = config.SEED_DIR / "transcripts" / entry.get("transcript_file", "")
    if transcript_src.exists():
        dst = config.TRANSCRIPTS_DIR / f"{video.id}.vtt"
        shutil.copy(transcript_src, dst)
        video.transcript_path = str(dst)
