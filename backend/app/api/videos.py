import os
import subprocess
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Optional

from app.models.database import (
    get_db, Video, VideoStatus, DifficultyLevel, Visibility, User, UserRole, Playlist
)
from app.api.auth import get_current_user

router = APIRouter()

DIFFICULTY_LABELS = {
    "basic": "Core Foundation",
    "platform_deep_dive": "Platform Deep Dive",
    "advanced": "Advanced",
}


def _video_visible(video: Video, user: Optional[User]) -> bool:
    if video.visibility == Visibility.PUBLIC:
        return True
    if user is None or user.role == UserRole.GUEST:
        return False
    return True


def _video_to_dict(v: Video) -> dict:
    return {
        "id": v.id,
        "title": v.title,
        "description": v.description,
        "status": v.status.value,
        "duration_seconds": v.duration_seconds,
        "version": v.version,
        "playlist_id": v.playlist_id,
        "difficulty_level": v.difficulty_level.value,
        "visibility": v.visibility.value,
        "playlist_order": v.playlist_order,
        "thumbnail_url": f"/static/thumbnails/{v.id}.png" if v.thumbnail_path else None,
        "created_at": v.created_at.isoformat(),
    }


@router.get("/")
def list_videos(
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """List videos grouped by playlist > difficulty level, filtered by visibility."""
    playlists = db.query(Playlist).order_by(Playlist.order_index, Playlist.created_at).all()
    videos = (
        db.query(Video)
        .filter(Video.is_active == True)
        .order_by(Video.playlist_id, Video.difficulty_level, Video.playlist_order)
        .all()
    )

    by_playlist = defaultdict(list)
    for v in videos:
        if not _video_visible(v, user):
            continue
        by_playlist[v.playlist_id].append(v)

    result_playlists = []
    for p in playlists:
        playlist_videos = by_playlist.get(p.id, [])
        if not playlist_videos and not p.is_default:
            continue

        sections = {"basic": [], "platform_deep_dive": [], "advanced": []}
        for v in playlist_videos:
            sections[v.difficulty_level.value].append(_video_to_dict(v))

        result_playlists.append({
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "is_default": p.is_default,
            "sections": [
                {"key": key, "name": DIFFICULTY_LABELS[key], "videos": sections[key]}
                for key in ("basic", "platform_deep_dive", "advanced")
                if sections[key]
            ],
            "total_videos": len(playlist_videos),
        })

    orphan_videos = [v for v in videos if v.playlist_id is None and _video_visible(v, user)]
    if orphan_videos:
        sections = {"basic": [], "platform_deep_dive": [], "advanced": []}
        for v in orphan_videos:
            sections[v.difficulty_level.value].append(_video_to_dict(v))
        result_playlists.append({
            "id": None,
            "name": "Uncategorized",
            "description": None,
            "is_default": False,
            "sections": [
                {"key": key, "name": DIFFICULTY_LABELS[key], "videos": sections[key]}
                for key in ("basic", "platform_deep_dive", "advanced")
                if sections[key]
            ],
            "total_videos": len(orphan_videos),
        })

    return {"playlists": result_playlists}


@router.get("/{video_id}")
def get_video(video_id: int, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user)):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if not _video_visible(video, user):
        raise HTTPException(status_code=403, detail="Access denied: private video")

    return {
        "id": video.id,
        "title": video.title,
        "description": video.description,
        "section_key": video.section_key,
        "source_type": video.source_type.value,
        "status": video.status.value,
        "video_url": f"/static/videos/{video.id}.mp4" if video.video_path else None,
        "thumbnail_url": f"/static/thumbnails/{video.id}.png" if video.thumbnail_path else None,
        "transcript_url": f"/api/videos/{video.id}/transcript" if video.transcript_path else None,
        "slides_url": f"/api/videos/{video.id}/slides" if video.slides_path else None,
        "duration_seconds": video.duration_seconds,
        "playlist_id": video.playlist_id,
        "playlist_name": video.playlist.name if video.playlist else None,
        "difficulty_level": video.difficulty_level.value,
        "visibility": video.visibility.value,
        "version": video.version,
        "created_at": video.created_at.isoformat(),
        "updated_at": video.updated_at.isoformat(),
    }


@router.get("/{video_id}/transcript")
def get_transcript(video_id: int, db: Session = Depends(get_db)):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video or not video.transcript_path:
        raise HTTPException(status_code=404, detail="Transcript not found")
    return FileResponse(video.transcript_path, media_type="text/vtt")


@router.get("/{video_id}/download")
def download_video(video_id: int, db: Session = Depends(get_db)):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video or not video.video_path:
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(
        video.video_path,
        media_type="video/mp4",
        filename=f"{video.title}.mp4",
    )


@router.get("/{video_id}/slides")
def download_slides(
    video_id: int,
    format: str = Query("pptx", pattern="^(pptx|pdf)$"),
    db: Session = Depends(get_db),
):
    """Download slides in PPTX or PDF format."""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video or not video.slides_path:
        raise HTTPException(status_code=404, detail="Slides not found")

    if format == "pdf":
        pdf_path = video.slides_path.replace(".pptx", ".pdf")
        if not os.path.exists(pdf_path):
            try:
                out_dir = os.path.dirname(video.slides_path)
                subprocess.run(
                    ["libreoffice", "--headless", "--convert-to", "pdf", video.slides_path, "--outdir", out_dir],
                    check=True, timeout=60, capture_output=True,
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                raise HTTPException(status_code=500, detail="PDF conversion failed (LibreOffice not available)")
        if not os.path.exists(pdf_path):
            raise HTTPException(status_code=500, detail="PDF conversion failed")
        return FileResponse(pdf_path, media_type="application/pdf", filename=f"{video.title}.pdf")

    return FileResponse(
        video.slides_path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=f"{video.title}.pptx",
    )
