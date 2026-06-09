import uuid
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.database import get_db, Video, VideoStatus, ContentSource, DifficultyLevel, Visibility, User, Playlist
from app.config import UPLOADS_DIR
from app.services.pipeline import run_video_pipeline
from app.api.auth import require_admin_or_demo

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".pptx", ".txt", ".png", ".jpg", ".jpeg"}


def _get_content_source(filename: str) -> ContentSource:
    ext = Path(filename).suffix.lower()
    mapping = {
        ".pdf": ContentSource.PDF_UPLOAD,
        ".pptx": ContentSource.PPTX_UPLOAD,
        ".txt": ContentSource.TXT_UPLOAD,
        ".png": ContentSource.IMAGE_UPLOAD,
        ".jpg": ContentSource.IMAGE_UPLOAD,
        ".jpeg": ContentSource.IMAGE_UPLOAD,
    }
    return mapping.get(ext, ContentSource.TXT_UPLOAD)


def _resolve_playlist(db: Session, playlist_id: Optional[int]) -> Playlist:
    if playlist_id is not None:
        playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
        if playlist:
            return playlist
    default = db.query(Playlist).filter(Playlist.is_default == True).first()
    if not default:
        default = db.query(Playlist).first()
    if not default:
        raise HTTPException(status_code=400, detail="No playlists exist; create one first")
    return default


def _validate_options(difficulty_level: str, visibility: str):
    try:
        diff = DifficultyLevel(difficulty_level)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid difficulty_level: {difficulty_level}")
    try:
        vis = Visibility(visibility)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid visibility: {visibility}")
    return diff, vis


@router.post("/file")
async def upload_file(
    file: UploadFile = File(...),
    title: str = Form(None),
    difficulty_level: str = Form("basic"),
    visibility: str = Form("public"),
    playlist_id: Optional[int] = Form(None),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    uploader: Optional[User] = Depends(require_admin_or_demo),
):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {ALLOWED_EXTENSIONS}",
        )

    diff_level, vis = _validate_options(difficulty_level, visibility)
    playlist = _resolve_playlist(db, playlist_id)

    file_id = str(uuid.uuid4())
    upload_path = UPLOADS_DIR / f"{file_id}{ext}"
    content = await file.read()
    upload_path.write_bytes(content)

    max_order = db.query(Video).filter(
        Video.playlist_id == playlist.id,
        Video.difficulty_level == diff_level,
    ).count()

    video = Video(
        title=title or Path(file.filename).stem,
        source_type=_get_content_source(file.filename),
        status=VideoStatus.PENDING,
        playlist_id=playlist.id,
        difficulty_level=diff_level,
        visibility=vis,
        playlist_order=max_order + 1,
    )
    db.add(video)
    db.commit()
    db.refresh(video)

    background_tasks.add_task(run_video_pipeline, video.id, str(upload_path))

    return {
        "id": video.id,
        "title": video.title,
        "status": video.status.value,
        "playlist_id": playlist.id,
        "playlist_name": playlist.name,
        "difficulty_level": diff_level.value,
        "visibility": vis.value,
        "message": "Video generation started",
    }


@router.post("/url")
async def upload_url(
    url: str = Form(...),
    title: str = Form(None),
    difficulty_level: str = Form("basic"),
    visibility: str = Form("public"),
    playlist_id: Optional[int] = Form(None),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    uploader: Optional[User] = Depends(require_admin_or_demo),
):
    diff_level, vis = _validate_options(difficulty_level, visibility)
    playlist = _resolve_playlist(db, playlist_id)

    max_order = db.query(Video).filter(
        Video.playlist_id == playlist.id,
        Video.difficulty_level == diff_level,
    ).count()

    video = Video(
        title=title or "Video from URL",
        source_type=ContentSource.URL_UPLOAD,
        status=VideoStatus.PENDING,
        playlist_id=playlist.id,
        difficulty_level=diff_level,
        visibility=vis,
        playlist_order=max_order + 1,
    )
    db.add(video)
    db.commit()
    db.refresh(video)

    background_tasks.add_task(run_video_pipeline, video.id, url)

    return {
        "id": video.id,
        "title": video.title,
        "status": video.status.value,
        "playlist_id": playlist.id,
        "playlist_name": playlist.name,
        "difficulty_level": diff_level.value,
        "visibility": vis.value,
        "message": "Video generation started from URL",
    }


@router.get("/status/{video_id}")
def get_generation_status(video_id: int, db: Session = Depends(get_db)):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return {
        "id": video.id,
        "status": video.status.value,
        "title": video.title,
    }
