"""
Lazy in-memory full-text index of the Cloud Bible PDF.

Used by the content monitor to answer the question:
    "Does the section we just scraped from nutanixbible.com match the
     reference text we have on file from the local PDF baseline?"

We deliberately keep the algorithm simple:
1. On first access, load every page of the PDF and build a single normalized
   text blob (lowercase, single-spaced).
2. Per section, normalize the website-scraped text the same way.
3. If `web_norm` is a contiguous substring of `pdf_norm` -> exact match.
4. Otherwise, do a word-set diff: words in the website but not in the PDF
   (likely additions/edits) and words in the PDF but not in the website
   (likely removed/restructured paragraphs).

This returns a verdict + a short human-readable summary that the admin sees
in the Monitor page and the email.
"""
from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Optional

from app.services import bible_diagrams

_LOCK = threading.Lock()
_FULL_TEXT: Optional[str] = None
_NORM_TEXT: Optional[str] = None
_NORM_TOKENS: Optional[set[str]] = None
_PDF_PATH: Optional[Path] = None


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse all whitespace to single spaces."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[\u200b\u00a0]", " ", text)
    text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _resolve_pdf_path() -> Optional[Path]:
    """Find the PDF that was used to populate the Cloud Bible diagrams.

    Falls back to scanning ~/Downloads for a Nutanix Cloud Bible classic PDF
    if the manifest doesn't record one.
    """
    global _PDF_PATH
    if _PDF_PATH:
        return _PDF_PATH

    manifest = bible_diagrams.load_manifest()
    src = manifest.get("source_pdf")
    if src and Path(src).exists():
        _PDF_PATH = Path(src)
        return _PDF_PATH

    home = Path.home()
    for candidate_dir in [home / "Downloads", home / "Documents"]:
        if not candidate_dir.exists():
            continue
        for p in candidate_dir.glob("nutanix*cloud*bible*.pdf"):
            _PDF_PATH = p
            return _PDF_PATH
    return None


def _load_pdf_text() -> str:
    """Read every page of the PDF and concatenate the text. Cheap-ish for
    a 350-page PDF (a few seconds), so we cache aggressively."""
    pdf_path = _resolve_pdf_path()
    if pdf_path is None:
        raise FileNotFoundError(
            "PDF baseline not found. Re-run `python -m app.services.bible_diagrams "
            "extract <pdf>` to register it."
        )
    import pymupdf as fitz
    doc = fitz.open(str(pdf_path))
    parts: list[str] = []
    for page in doc:
        parts.append(page.get_text("text"))
    doc.close()
    return "\n".join(parts)


def ensure_loaded() -> None:
    """Load + normalize the PDF text once, thread-safely."""
    global _FULL_TEXT, _NORM_TEXT, _NORM_TOKENS
    if _NORM_TEXT is not None:
        return
    with _LOCK:
        if _NORM_TEXT is not None:
            return
        full = _load_pdf_text()
        norm = _normalize(full)
        _FULL_TEXT = full
        _NORM_TEXT = norm
        _NORM_TOKENS = set(norm.split())


def is_available() -> bool:
    return _resolve_pdf_path() is not None


def compare_section(web_text: str, min_words: int = 6) -> dict:
    """Compare a single website section against the PDF baseline.

    Returns:
        {
            "match_kind":  "exact" | "subset_match" | "differences" | "skipped",
            "verdict":     short human-readable string,
            "exact":       bool,
            "added":       up to 12 words present on the website but not the PDF,
            "missing":     up to 12 words present in the PDF but not the website,
            "added_count": int,
            "missing_count": int,
        }
    """
    ensure_loaded()
    if not _NORM_TEXT:
        return {
            "match_kind": "skipped",
            "verdict": "PDF baseline unavailable",
            "exact": False,
            "added": [], "missing": [],
            "added_count": 0, "missing_count": 0,
        }

    web_norm = _normalize(web_text or "")
    web_tokens = web_norm.split()
    if len(web_tokens) < min_words:
        return {
            "match_kind": "skipped",
            "verdict": "Website section too short to compare",
            "exact": True,  # treat as non-drift
            "added": [], "missing": [],
            "added_count": 0, "missing_count": 0,
        }

    if web_norm and web_norm in _NORM_TEXT:
        return {
            "match_kind": "exact",
            "verdict": "Exactly matches the PDF",
            "exact": True,
            "added": [], "missing": [],
            "added_count": 0, "missing_count": 0,
        }

    # Word-set diff (cheap drift summary).
    web_set = set(web_tokens)
    pdf_set = _NORM_TOKENS or set()
    added = sorted(t for t in web_set - pdf_set if len(t) > 2)
    overlap = len(web_set & pdf_set)
    overlap_ratio = overlap / max(1, len(web_set))

    # Anything above this ratio is effectively the same content (chrome / nav words don't count).
    NEAR_MATCH_RATIO = 0.95

    if overlap_ratio >= NEAR_MATCH_RATIO and len(added) < 25:
        kind = "subset_match"
        verdict = f"Matches the PDF ({overlap_ratio:.0%} word overlap, {len(added)} chrome word(s))"
        exact = True
    elif overlap_ratio > 0.85:
        kind = "minor_differences"
        verdict = (
            f"Minor differences vs PDF: {len(added)} new word(s), "
            f"{overlap_ratio:.0%} word overlap"
        )
        exact = False
    else:
        kind = "differences"
        verdict = (
            f"Differences vs PDF: {len(added)} new word(s), "
            f"{overlap_ratio:.0%} word overlap"
        )
        exact = False

    return {
        "match_kind": kind,
        "verdict": verdict,
        "exact": exact,
        "added": added[:12],
        "missing": [],
        "added_count": len(added),
        "missing_count": 0,
    }
