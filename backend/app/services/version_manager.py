"""
Zero-downtime version swap logic for seamless video updates.
Manages draft/active version pointers so users always see a working video.
"""
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.database import Video, VideoVersion, VideoStatus, ContentSource


def create_draft_version(db: Session, existing_video: Video) -> Video:
    """Create a new draft video entry for regeneration while the current one stays active."""
    draft = Video(
        title=existing_video.title,
        description=existing_video.description,
        section_key=existing_video.section_key,
        source_type=existing_video.source_type,
        status=VideoStatus.DRAFT,
        version=existing_video.version + 1,
        is_active=False,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)

    version_record = VideoVersion(
        video_id=existing_video.id,
        version_number=draft.version,
        video_path=existing_video.video_path or "",
        transcript_path=existing_video.transcript_path,
        slides_path=existing_video.slides_path,
        is_active=False,
    )
    db.add(version_record)
    db.commit()

    return draft


def promote_draft(db: Session, original_id: int, draft_id: int):
    """Atomically swap the active version pointer from original to draft."""
    original = db.query(Video).filter(Video.id == original_id).first()
    draft = db.query(Video).filter(Video.id == draft_id).first()

    if not original or not draft:
        return

    if draft.status != VideoStatus.READY:
        print(f"[VersionManager] Draft {draft_id} not ready, skipping promotion")
        return

    original.is_active = False
    original.updated_at = datetime.utcnow()

    draft.is_active = True
    draft.status = VideoStatus.READY
    draft.updated_at = datetime.utcnow()

    version_record = VideoVersion(
        video_id=original_id,
        version_number=draft.version,
        video_path=draft.video_path or "",
        transcript_path=draft.transcript_path,
        slides_path=draft.slides_path,
        content_hash=None,
        is_active=True,
    )
    db.add(version_record)
    db.commit()

    print(f"[VersionManager] Promoted draft {draft_id} -> active (was {original_id})")


def rollback_version(db: Session, video_id: int):
    """Rollback to the previous active version."""
    current = db.query(Video).filter(
        Video.id == video_id, Video.is_active == True
    ).first()

    if not current:
        return

    previous = db.query(Video).filter(
        Video.section_key == current.section_key,
        Video.is_active == False,
        Video.status == VideoStatus.READY,
        Video.id != video_id,
    ).order_by(Video.version.desc()).first()

    if previous:
        current.is_active = False
        previous.is_active = True
        db.commit()
        print(f"[VersionManager] Rolled back from {video_id} to {previous.id}")


def get_version_history(db: Session, section_key: str) -> list[dict]:
    """Get version history for a content section."""
    versions = db.query(VideoVersion).join(Video).filter(
        Video.section_key == section_key
    ).order_by(VideoVersion.version_number.desc()).all()

    return [
        {
            "version": v.version_number,
            "video_path": v.video_path,
            "is_active": v.is_active,
            "created_at": v.created_at.isoformat(),
        }
        for v in versions
    ]
