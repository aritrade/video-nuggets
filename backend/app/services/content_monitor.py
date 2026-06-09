"""
24-hour content monitor agent.
Scrapes the Nutanix Cloud Bible website, detects changes vs. the previous
snapshot, *and* compares each section against the local PDF baseline so the
admin Monitor page can show "exact match" / "differences found".

Every execution writes a `MonitorRun` audit row.
"""
import difflib
import hashlib
import json
import logging
import traceback
from datetime import datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.models.database import (
    SessionLocal,
    ContentSnapshot,
    Video,
    VideoStatus,
    ContentSource,
    MonitorRun,
    MonitorRunStatus,
)
from app.config import NUTANIX_BIBLE_URL
from app.services.change_summarizer import summarize_change
from app.services.version_manager import create_draft_version, promote_draft
from app.services import pdf_text_index

logger = logging.getLogger(__name__)

# Keep the per-section snapshot blobs we persist into MonitorRun.drift_details
# bounded so the audit JSON stays small. The full text always lives on
# ContentSnapshot; drift_details is only what the admin UI shows in the
# expanded row.
_DRIFT_TEXT_LIMIT = 8000


def _truncate_for_drift(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    if len(text) <= _DRIFT_TEXT_LIMIT:
        return text
    return text[:_DRIFT_TEXT_LIMIT] + f"\n...[truncated {len(text) - _DRIFT_TEXT_LIMIT} chars]"


def _build_unified_diff(old_text: str, new_text: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile="previous",
            tofile="current",
            n=2,
            lineterm="",
        )
    )

BIBLE_SECTIONS = [
    {"key": "basics", "path": "", "title": "The Basics"},
    {"key": "ahv", "path": "#ahv", "title": "AHV Architecture"},
    {"key": "vsphere", "path": "#vsphere", "title": "vSphere on Nutanix"},
    {"key": "hyperv", "path": "#hyperv", "title": "Hyper-V on Nutanix"},
    {"key": "storage", "path": "#storage", "title": "Storage Architecture"},
    {"key": "volumes", "path": "#volumes", "title": "Volumes (Block Services)"},
    {"key": "files", "path": "#files", "title": "Files (File Services)"},
    {"key": "objects", "path": "#objects", "title": "Objects (Object Services)"},
    {"key": "networking", "path": "#networking", "title": "Network Services"},
    {"key": "flow", "path": "#flow", "title": "Flow Network Security"},
    {"key": "nc2_aws", "path": "#nc2-aws", "title": "NC2 on AWS"},
    {"key": "nc2_azure", "path": "#nc2-azure", "title": "NC2 on Azure"},
    {"key": "prism", "path": "#prism", "title": "Prism"},
    {"key": "ndb", "path": "#ndb", "title": "Nutanix Database Service"},
    {"key": "kubernetes", "path": "#kubernetes", "title": "Nutanix Kubernetes Platform"},
    {"key": "enterprise_ai", "path": "#enterprise-ai", "title": "Enterprise AI"},
    {"key": "dr", "path": "#dr", "title": "Disaster Recovery"},
    {"key": "security", "path": "#security", "title": "Data and Network Security"},
]


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


async def run_content_check(triggered_by: str = "scheduler") -> dict:
    """Run one full Cloud Bible content check.

    Always returns a summary dict (never raises out) so the scheduler thread
    and HTTP triggers can both consume it. Every invocation writes one
    `MonitorRun` row.
    """
    db = SessionLocal()
    run = MonitorRun(
        started_at=datetime.utcnow(),
        status=MonitorRunStatus.RUNNING,
        triggered_by=triggered_by,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    drift_rows: list[dict] = []
    web_changes: list[dict] = []
    pdf_baseline_ok = pdf_text_index.is_available()

    try:
        # trust_env=False: ignore ambient HTTP(S)_PROXY env vars. The monitor
        # always talks to a specific public site (nutanixbible.com); routing
        # through whatever proxy happens to be set in the host environment
        # (corp proxy, Cursor browser sandbox, etc.) is never what we want and
        # has caused 403 ProxyError failures in the past.
        async with httpx.AsyncClient(
            timeout=30.0,
            trust_env=False,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "NutanixVideoNuggets-ContentMonitor/1.0 "
                    "(+https://github.com/) "
                    "Mozilla/5.0"
                ),
            },
        ) as client:
            response = await client.get(NUTANIX_BIBLE_URL)
            response.raise_for_status()
            full_page = response.text

        soup = BeautifulSoup(full_page, "html.parser")

        for section_info in BIBLE_SECTIONS:
            section_content = _extract_section_content(soup, section_info)
            content_hash = hashlib.sha256(section_content.encode()).hexdigest()

            existing = db.query(ContentSnapshot).filter(
                ContentSnapshot.section_key == section_info["key"]
            ).first()

            web_changed = False
            change_kind = "first_seen" if existing is None else "no_change"
            # Capture the previous text BEFORE we overwrite it on `existing`,
            # so the admin UI can render an old-vs-new diff for this run.
            old_content: Optional[str] = existing.content_text if existing else None

            if existing:
                if existing.content_hash != content_hash:
                    web_changed = True
                    change_kind = "modified"
                    web_changes.append({
                        "section": section_info,
                        "old_hash": existing.content_hash,
                        "new_hash": content_hash,
                        "content": section_content,
                    })
                    existing.content_hash = content_hash
                    existing.content_text = section_content
                    existing.last_changed = datetime.utcnow()
                existing.last_checked = datetime.utcnow()
            else:
                snapshot = ContentSnapshot(
                    section_key=section_info["key"],
                    section_title=section_info["title"],
                    content_hash=content_hash,
                    content_text=section_content,
                    url=f"{NUTANIX_BIBLE_URL}{section_info['path']}",
                    last_checked=datetime.utcnow(),
                )
                db.add(snapshot)

            pdf_match: Optional[bool] = None
            pdf_summary = ""
            if pdf_baseline_ok:
                try:
                    cmp = pdf_text_index.compare_section(section_content)
                    pdf_match = bool(cmp["exact"])
                    pdf_summary = cmp["verdict"]
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "PDF compare failed for %s: %s", section_info["key"], exc
                    )
                    pdf_summary = f"PDF compare error: {exc}"

            if web_changed or (pdf_match is False):
                if web_changed:
                    diff_unified = _build_unified_diff(
                        old_content or "", section_content
                    )
                    change_summary = await summarize_change(
                        section_info["title"], old_content or "", section_content
                    )
                else:
                    diff_unified = None
                    change_summary = None

                drift_rows.append({
                    "section_key": section_info["key"],
                    "section_title": section_info["title"],
                    "kind": change_kind if web_changed else "pdf_drift_only",
                    "web_changed": web_changed,
                    "pdf_match": pdf_match,
                    "summary": pdf_summary,
                    "url": f"{NUTANIX_BIBLE_URL}{section_info['path']}",
                    "old_content": _truncate_for_drift(old_content),
                    "new_content": _truncate_for_drift(section_content),
                    "diff_unified": diff_unified,
                    "change_summary": change_summary,
                })

            db.commit()

        run.sections_checked = len(BIBLE_SECTIONS)
        run.web_drift_count = sum(1 for r in drift_rows if r["web_changed"])
        run.pdf_drift_count = sum(1 for r in drift_rows if r["pdf_match"] is False)
        run.pdf_match = (
            None if not pdf_baseline_ok
            else (run.pdf_drift_count == 0)
        )
        run.drift_details = json.dumps(drift_rows)
        run.status = MonitorRunStatus.SUCCESS

    except Exception as exc:  # noqa: BLE001
        logger.exception("Monitor run failed")
        run.status = MonitorRunStatus.FAILURE
        run.error_message = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
    finally:
        run.finished_at = datetime.utcnow()
        db.commit()
        db.refresh(run)

        # Kick off video regeneration only when website actually changed.
        try:
            if run.status == MonitorRunStatus.SUCCESS and web_changes:
                await _handle_changes(db, web_changes)
        except Exception:
            logger.exception("Video regeneration trigger failed")

        db.close()

    return {
        "run_id": run.id,
        "status": run.status.value if run.status else None,
        "sections_checked": run.sections_checked,
        "web_drift_count": run.web_drift_count,
        "pdf_drift_count": run.pdf_drift_count,
        "pdf_match": run.pdf_match,
        "drift_rows": drift_rows,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _handle_changes(db: Session, changes: list[dict]):
    """Trigger video regeneration for sections whose website content changed."""
    from app.services.pipeline import run_video_pipeline

    for change in changes:
        section = change["section"]
        logger.info("Change detected in: %s", section["title"])

        existing_video = db.query(Video).filter(
            Video.section_key == section["key"],
            Video.is_active == True,  # noqa: E712
        ).first()

        if existing_video:
            draft = create_draft_version(db, existing_video)
            url = f"{NUTANIX_BIBLE_URL}{section['path']}"
            run_video_pipeline(draft.id, url)
            promote_draft(db, existing_video.id, draft.id)
        else:
            video = Video(
                title=section["title"],
                section_key=section["key"],
                source_type=ContentSource.BIBLE_SCRAPE,
                status=VideoStatus.PENDING,
            )
            db.add(video)
            db.commit()
            db.refresh(video)
            url = f"{NUTANIX_BIBLE_URL}{section['path']}"
            run_video_pipeline(video.id, url)


def _extract_section_content(soup: BeautifulSoup, section_info: dict) -> str:
    """Extract text content for a specific section from the page."""
    section_id = section_info["path"].lstrip("#")

    if section_id:
        anchor = soup.find(id=section_id) or soup.find(attrs={"name": section_id})
        if anchor:
            content_parts = []
            sibling = anchor.find_next()
            count = 0
            while sibling and count < 50:
                if sibling.name in ["h1", "h2"] and count > 0:
                    break
                text = sibling.get_text(strip=True)
                if text:
                    content_parts.append(text)
                sibling = sibling.find_next_sibling()
                count += 1
            return "\n".join(content_parts)

    main_content = soup.find("main") or soup.find("article") or soup.find("body")
    if main_content:
        return main_content.get_text(separator="\n", strip=True)[:5000]

    return soup.get_text(separator="\n", strip=True)[:5000]
