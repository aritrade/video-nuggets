"""
Playlist management endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.models.database import get_db, Playlist, Video, User, DifficultyLevel
from app.api.auth import require_admin, get_current_user

router = APIRouter()


class PlaylistCreate(BaseModel):
    name: str
    description: Optional[str] = None


@router.get("/")
def list_playlists(db: Session = Depends(get_db)):
    """List all playlists with video counts per difficulty."""
    playlists = db.query(Playlist).order_by(Playlist.order_index, Playlist.created_at).all()
    result = []
    for p in playlists:
        counts = {"basic": 0, "platform_deep_dive": 0, "advanced": 0}
        for v in p.videos:
            if v.is_active:
                counts[v.difficulty_level.value] += 1
        result.append({
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "is_default": p.is_default,
            "video_counts": counts,
            "total_videos": sum(counts.values()),
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })
    return {"playlists": result}


@router.post("/")
def create_playlist(
    payload: PlaylistCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Create a new playlist (admin only)."""
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Playlist name is required")

    existing = db.query(Playlist).filter(Playlist.name == name).first()
    if existing:
        raise HTTPException(status_code=409, detail="A playlist with this name already exists")

    max_order = db.query(Playlist).count()
    playlist = Playlist(
        name=name,
        description=payload.description,
        is_default=False,
        created_by_user_id=admin.id,
        order_index=max_order + 1,
    )
    db.add(playlist)
    db.commit()
    db.refresh(playlist)

    return {
        "id": playlist.id,
        "name": playlist.name,
        "description": playlist.description,
        "is_default": False,
        "video_counts": {"basic": 0, "platform_deep_dive": 0, "advanced": 0},
        "total_videos": 0,
    }
