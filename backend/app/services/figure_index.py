"""Per-video source-document figure mining.

Generalizes the (Bible-specific) extractor in ``bible_diagrams`` so the engine
can mine REAL diagrams / architecture figures out of any uploaded PDF and show
them - animated - while the narration explains the concept.

Flow:
- At parse time, :func:`build_for_pdf` renders every sufficiently-large image
  region of the PDF to a crisp PNG under ``output/figures/{video_id}/`` and
  records heading/caption/topic/token metadata (reusing the helper functions in
  ``bible_diagrams``).
- The returned :class:`DiagramIndex` matches a section's text to the best figure
  via token overlap, and loads the cropped PNG for the animation engine.

Non-PDF sources (txt/url/image) simply yield an empty index; the director then
relies on synthesized diagrams / icon scenes instead.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Optional

from PIL import Image

from app import config
from app.services import bible_diagrams as _bd

# Reuse the (pure) extraction + tokenization helpers so there is one code path.
_tokenize = _bd._tokenize
MIN_W_PT = _bd.MIN_DIAGRAM_WIDTH_PT
MIN_H_PT = _bd.MIN_DIAGRAM_HEIGHT_PT
RENDER_SCALE = _bd.RENDER_SCALE

FIGURES_DIR = config.OUTPUT_DIR / "figures"


def _scored(diagrams: list[dict], query: str,
            exclude_ids: Optional[set[str]]) -> list[tuple[float, dict]]:
    """Token-overlap scoring identical to bible_diagrams.find_diagrams_for."""
    qtokens = _tokenize(query)
    if not qtokens or not diagrams:
        return []
    qcounts = Counter(qtokens)
    exclude_ids = exclude_ids or set()
    scored: list[tuple[float, dict]] = []
    for d in diagrams:
        if d.get("id") in exclude_ids:
            continue
        score = 0.0
        topic_tokens = set(_tokenize(" ".join(d.get("topic_path", []) + [d.get("topic", "")])))
        heading_tokens = set(_tokenize(d.get("heading_above", "")))
        body_tokens = set(d.get("tokens", []))
        for t, c in qcounts.items():
            if t in topic_tokens:
                score += 5.0 * c
            if t in heading_tokens:
                score += 3.0 * c
            if t in body_tokens:
                score += 1.0 * c
        if score > 0:
            scored.append((score, d))
    scored.sort(key=lambda kv: -kv[0])
    return scored


def _score_diagrams(diagrams: list[dict], query: str, top_k: int,
                    exclude_ids: Optional[set[str]]) -> list[dict]:
    return [d for _, d in _scored(diagrams, query, exclude_ids)[:top_k]]


class DiagramIndex:
    """An in-memory index over one document's extracted figures."""

    def __init__(self, manifest: dict, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.diagrams: list[dict] = manifest.get("diagrams", [])
        self._image_cache: dict[tuple[str, Optional[int]], Image.Image] = {}

    def __bool__(self) -> bool:
        return bool(self.diagrams)

    def find(self, query: str, top_k: int = 3,
             exclude_ids: Optional[set[str]] = None) -> list[dict]:
        return _score_diagrams(self.diagrams, query, top_k, exclude_ids)

    def best(self, query: str, exclude_ids: Optional[set[str]] = None) -> Optional[dict]:
        matches = self.find(query, top_k=1, exclude_ids=exclude_ids)
        return matches[0] if matches else None

    def best_scored(self, query: str,
                    exclude_ids: Optional[set[str]] = None) -> tuple[Optional[dict], float]:
        """Best match plus its relevance score (0 when nothing matches)."""
        scored = _scored(self.diagrams, query, exclude_ids)
        return (scored[0][1], scored[0][0]) if scored else (None, 0.0)

    def abs_path(self, diagram: dict) -> Optional[str]:
        rel = (diagram or {}).get("image_path")
        return str(self.base_dir / rel) if rel else None

    def get_image(self, diagram: dict, max_dim: Optional[int] = None) -> Optional[Image.Image]:
        if not diagram:
            return None
        rel = diagram.get("image_path")
        if not rel:
            return None
        key = (rel, max_dim)
        if key in self._image_cache:
            return self._image_cache[key]
        abs_path = self.base_dir / rel
        if not abs_path.exists():
            return None
        img = Image.open(abs_path).convert("RGBA")
        if max_dim is not None and max(img.size) > max_dim:
            ratio = max_dim / max(img.size)
            img = img.resize((int(img.size[0] * ratio), int(img.size[1] * ratio)), Image.LANCZOS)
        self._image_cache[key] = img
        return img


EMPTY_INDEX = DiagramIndex({"diagrams": []}, FIGURES_DIR)


def extract_figures(pdf_path: str | Path, out_dir: Path) -> dict:
    """Render each large image region of the PDF to a PNG + return a manifest.

    Mirrors bible_diagrams.extract but writes to an arbitrary per-video dir with
    image paths relative to that dir.
    """
    import pymupdf as fitz

    pdf_path = Path(pdf_path)
    diagrams_dir = out_dir / "diagrams"
    diagrams_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))
    toc_flat = _bd._flatten_toc(doc.get_toc())

    diagrams: list[dict] = []
    skipped = 0
    for i in range(doc.page_count):
        page = doc[i]
        page_num = i + 1
        blocks = page.get_text("dict")["blocks"]
        img_blocks = [b for b in blocks if b["type"] == 1]
        if not img_blocks:
            continue
        for j, b in enumerate(img_blocks):
            bbox = b["bbox"]
            if (bbox[2] - bbox[0]) < MIN_W_PT or (bbox[3] - bbox[1]) < MIN_H_PT:
                skipped += 1
                continue
            try:
                pix = page.get_pixmap(matrix=fitz.Matrix(RENDER_SCALE, RENDER_SCALE),
                                      clip=bbox, alpha=False)
            except Exception:
                continue
            rel = f"diagrams/p{page_num:03d}_{j:02d}.png"
            pix.save(str(out_dir / rel))
            heading = _bd._heading_above(blocks, bbox)
            caption = _bd._caption_below(blocks, bbox)
            topic, topic_path = _bd._topic_for_page(toc_flat, page_num)
            surrounding = _bd._page_text(blocks, bbox)
            tokens = _tokenize(" ".join([heading, caption, topic, " ".join(topic_path), surrounding]))
            diagrams.append({
                "id": f"p{page_num:03d}_{j:02d}",
                "page": page_num,
                "bbox": [round(x, 2) for x in bbox],
                "width_px": pix.width,
                "height_px": pix.height,
                "image_path": rel,
                "topic": topic,
                "topic_path": topic_path,
                "heading_above": heading,
                "caption_below": caption,
                "surrounding_text": surrounding[:1200],
                "tokens": list(set(tokens)),
            })

    manifest = {
        "source_pdf": str(pdf_path),
        "diagram_count": len(diagrams),
        "skipped_small": skipped,
        "diagrams": diagrams,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def build_for_pdf(pdf_path: str | Path, video_id: int) -> DiagramIndex:
    """Extract a per-video figure index from a PDF. Safe to call for any source;
    returns an empty index if the file is not a PDF or extraction fails."""
    pdf_path = Path(pdf_path)
    if pdf_path.suffix.lower() != ".pdf" or not pdf_path.exists():
        return EMPTY_INDEX
    out_dir = FIGURES_DIR / str(video_id)
    try:
        manifest = extract_figures(pdf_path, out_dir)
    except Exception as e:  # pragma: no cover - never break the pipeline
        print(f"[figure_index] extraction failed for {pdf_path}: {e}")
        return EMPTY_INDEX
    print(f"[figure_index] video {video_id}: extracted {manifest['diagram_count']} figures")
    return DiagramIndex(manifest, out_dir)


def load_index(video_id: int) -> DiagramIndex:
    """Load a previously-extracted per-video index (or empty)."""
    out_dir = FIGURES_DIR / str(video_id)
    mpath = out_dir / "manifest.json"
    if not mpath.exists():
        return EMPTY_INDEX
    try:
        return DiagramIndex(json.loads(mpath.read_text()), out_dir)
    except Exception:
        return EMPTY_INDEX
