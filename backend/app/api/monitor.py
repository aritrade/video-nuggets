"""
Admin Monitor API.

All run-history reads and the manual trigger are gated to NUTANIX_ADMIN.
The legacy read-only `/status` endpoint stays open to any authenticated user
so the rest of the app can still display "last synced N hours ago" metadata.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.models.database import (
    get_db,
    ContentSnapshot,
    ContentSource,
    MonitorRun,
    MonitorRunVideoJob,
    MonitorRunVideoJobStatus,
    SessionLocal,
    User,
    Video,
    VideoStatus,
)
from app.services.content_monitor import run_content_check
from app.services.pipeline import run_video_pipeline
from app.services.version_manager import create_draft_version, promote_draft
from app.services import pdf_text_index

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize_run(run: MonitorRun, *, include_details: bool = False) -> dict:
    drift = []
    if include_details and run.drift_details:
        try:
            drift = json.loads(run.drift_details)
        except Exception:
            drift = []
    return {
        "id": run.id,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_seconds": (
            (run.finished_at - run.started_at).total_seconds()
            if run.finished_at and run.started_at else None
        ),
        "status": run.status.value if run.status else None,
        "triggered_by": run.triggered_by,
        "error_message": run.error_message,
        "sections_checked": run.sections_checked,
        "web_drift_count": run.web_drift_count,
        "pdf_match": run.pdf_match,
        "pdf_drift_count": run.pdf_drift_count,
        "drift_count": (run.web_drift_count or 0) + (run.pdf_drift_count or 0),
        "drift_details": drift if include_details else None,
    }


def _serialize_job(job: MonitorRunVideoJob) -> dict:
    return {
        "id": job.id,
        "monitor_run_id": job.monitor_run_id,
        "section_key": job.section_key,
        "section_title": job.section_title,
        "video_id": job.video_id,
        "action": job.action,
        "status": job.status.value if job.status else None,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/status")
def monitor_status(db: Session = Depends(get_db)):
    """Public-ish: per-section snapshot index. Used in the rest of the app."""
    snapshots = db.query(ContentSnapshot).all()
    return {
        "total_sections": len(snapshots),
        "pdf_baseline_available": pdf_text_index.is_available(),
        "sections": [
            {
                "section_key": s.section_key,
                "section_title": s.section_title,
                "last_checked": s.last_checked.isoformat() if s.last_checked else None,
                "last_changed": s.last_changed.isoformat() if s.last_changed else None,
                "content_hash": (s.content_hash[:12] + "...") if s.content_hash else None,
            }
            for s in snapshots
        ],
    }


@router.get("/runs")
def list_runs(
    limit: int = 50,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Admin: list recent monitor runs."""
    limit = max(1, min(200, limit))
    rows = (
        db.query(MonitorRun)
        .order_by(MonitorRun.started_at.desc())
        .limit(limit)
        .all()
    )
    latest = rows[0] if rows else None
    return {
        "total": db.query(MonitorRun).count(),
        "latest": _serialize_run(latest) if latest else None,
        "runs": [_serialize_run(r) for r in rows],
        "pdf_baseline_available": pdf_text_index.is_available(),
    }


@router.get("/runs/{run_id}")
def get_run(
    run_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    run = db.query(MonitorRun).filter(MonitorRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Monitor run not found")
    return _serialize_run(run, include_details=True)


@router.post("/trigger")
async def trigger_check(
    background_tasks: BackgroundTasks,
    admin: User = Depends(require_admin),
):
    """Admin: kick off a content check immediately. Runs in background."""
    triggered_by = f"manual:{admin.username}"
    background_tasks.add_task(run_content_check, triggered_by)
    return {
        "message": "Content check triggered",
        "status": "running",
        "triggered_by": triggered_by,
    }


# ---------------------------------------------------------------------------
# Apply-changes flow: regenerate (or create) videos for selected drifted
# sections. The admin clicks "Apply changes to N video(s)" in the Monitor UI;
# we materialize one MonitorRunVideoJob per section, schedule a background
# worker for each, and the UI polls /jobs to render per-section status pills.
# ---------------------------------------------------------------------------


class ApplyChangesRequest(BaseModel):
    section_keys: List[str]


@router.post("/runs/{run_id}/apply-changes")
def apply_changes(
    run_id: int,
    payload: ApplyChangesRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Admin: regenerate / create videos for the drifted sections selected by the admin."""
    run = db.query(MonitorRun).filter(MonitorRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Monitor run not found")

    # Dedupe while preserving order.
    keys = list(dict.fromkeys(payload.section_keys or []))
    if not keys:
        raise HTTPException(status_code=400, detail="section_keys is required")

    snapshots = {
        s.section_key: s
        for s in db.query(ContentSnapshot)
        .filter(ContentSnapshot.section_key.in_(keys))
        .all()
    }

    created_jobs: list[dict] = []
    for key in keys:
        snap = snapshots.get(key)
        if snap is None:
            raise HTTPException(
                status_code=400,
                detail=f"No content snapshot recorded for section '{key}' yet",
            )

        existing_video = (
            db.query(Video)
            .filter(Video.section_key == key, Video.is_active == True)  # noqa: E712
            .first()
        )

        job = MonitorRunVideoJob(
            monitor_run_id=run_id,
            section_key=key,
            section_title=snap.section_title or key,
            video_id=existing_video.id if existing_video else None,
            action="update" if existing_video else "create",
            status=MonitorRunVideoJobStatus.QUEUED,
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        background_tasks.add_task(_run_apply_job, job.id)
        created_jobs.append(_serialize_job(job))

    return {"jobs": created_jobs}


@router.get("/runs/{run_id}/jobs")
def list_run_jobs(
    run_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Admin: per-section apply-changes status for a given monitor run."""
    run = db.query(MonitorRun).filter(MonitorRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Monitor run not found")

    jobs = (
        db.query(MonitorRunVideoJob)
        .filter(MonitorRunVideoJob.monitor_run_id == run_id)
        .order_by(MonitorRunVideoJob.created_at.asc(), MonitorRunVideoJob.id.asc())
        .all()
    )
    return {"jobs": [_serialize_job(j) for j in jobs]}


def _run_apply_job(job_id: int) -> None:
    """Background worker: regenerate (or create) the video for one drifted section.

    Mirrors `_handle_changes` in `content_monitor.py`, but keyed on a single
    admin-selected section and tracked with a `MonitorRunVideoJob` row so the
    UI can show per-section progress.
    """
    db = SessionLocal()
    try:
        job = db.query(MonitorRunVideoJob).filter(MonitorRunVideoJob.id == job_id).first()
        if not job:
            return

        job.status = MonitorRunVideoJobStatus.RUNNING
        db.commit()

        snapshot = (
            db.query(ContentSnapshot)
            .filter(ContentSnapshot.section_key == job.section_key)
            .first()
        )
        if snapshot is None or not snapshot.url:
            job.status = MonitorRunVideoJobStatus.FAILED
            job.error_message = (
                f"No ContentSnapshot/url recorded for section '{job.section_key}'"
            )
            job.finished_at = datetime.utcnow()
            db.commit()
            return

        url = snapshot.url

        existing_video = (
            db.query(Video)
            .filter(Video.section_key == job.section_key, Video.is_active == True)  # noqa: E712
            .first()
        )

        if existing_video:
            draft = create_draft_version(db, existing_video)
            run_video_pipeline(draft.id, url)
            promote_draft(db, existing_video.id, draft.id)
            job.video_id = draft.id
        else:
            video = Video(
                title=job.section_title,
                section_key=job.section_key,
                source_type=ContentSource.BIBLE_SCRAPE,
                status=VideoStatus.PENDING,
            )
            db.add(video)
            db.commit()
            db.refresh(video)
            run_video_pipeline(video.id, url)
            job.video_id = video.id

        job.status = MonitorRunVideoJobStatus.SUCCESS
        job.finished_at = datetime.utcnow()
        db.commit()

    except Exception as exc:  # noqa: BLE001
        logger.exception("apply-changes job %s failed", job_id)
        job = db.query(MonitorRunVideoJob).filter(MonitorRunVideoJob.id == job_id).first()
        if job:
            job.status = MonitorRunVideoJobStatus.FAILED
            job.error_message = f"{type(exc).__name__}: {exc}"
            job.finished_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()
