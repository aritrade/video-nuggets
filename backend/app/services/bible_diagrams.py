"""
Nutanix Cloud Bible diagram extractor + in-memory index.

Run as a script (`python -m app.services.bible_diagrams extract <pdf>`) to
populate `backend/assets/bible_diagrams/` with one PNG per diagram and a
manifest.json that captures:

    {
        "diagrams": [
            {
                "id": "p015_001",
                "page": 15,
                "bbox": [x0, y0, x1, y1],
                "width_px": 1500,
                "height_px": 730,
                "image_path": "diagrams/p015_001.png",
                "topic": "System Imaging and Deployment",
                "topic_path": ["The Nutanix Cloud Bible", "Foundation Imaging Architecture", "System Imaging and Deployment"],
                "heading_above": "Foundation Imaging Architecture",
                "caption_below": "Figure 7-1 ...",
                "surrounding_text": "...",
                "tokens": ["foundation", "imaging", "architecture", ...]
            },
            ...
        ]
    }

At runtime, the rest of the pipeline imports this module and uses:

    load_manifest()                         -> dict (cached)
    find_diagrams_for(query, top_k=3)        -> list[diagram]
    get_diagram_image(diagram, size=None)   -> PIL.Image

Extraction uses PyMuPDF (`pymupdf`) to render each rendered image bbox as a
crisp PNG, and the PDF's TOC + nearby headings to assign a topic to every
diagram. Page-header logos and other tiny graphics are filtered out by size.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image

ASSETS_ROOT = Path(__file__).resolve().parents[2] / "assets" / "bible_diagrams"
MANIFEST_PATH = ASSETS_ROOT / "manifest.json"
DIAGRAMS_DIR = ASSETS_ROOT / "diagrams"

# Page-position filters in PDF point units.
MIN_DIAGRAM_WIDTH_PT = 200
MIN_DIAGRAM_HEIGHT_PT = 90
RENDER_SCALE = 3.0  # 3x supersample so the diagram looks crisp at 1080p.

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "in", "on", "to", "for", "with", "by",
    "is", "are", "be", "this", "that", "as", "it", "its", "from", "into",
    "at", "but", "not", "no", "yes", "have", "has", "had", "can", "will", "may",
    "we", "you", "they", "i", "their", "your", "our", "via", "per", "if",
}


# ----------------- Extraction (offline) -----------------

def _tokenize(text: str) -> list[str]:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s\-]", " ", text)
    parts = [p.strip("-") for p in text.split() if p.strip("-")]
    return [p for p in parts if p and p not in STOPWORDS and len(p) > 1]


def _flatten_toc(toc: list) -> list[tuple[int, list[str], str, int]]:
    """Return [(level, path_titles, leaf_title, page), ...] flattened from PDF TOC."""
    out: list[tuple[int, list[str], str, int]] = []
    stack: list[str] = []
    for level, title, page in toc:
        # PyMuPDF TOC levels are 1-based and reflect tree depth.
        while len(stack) >= level:
            stack.pop()
        stack.append(title)
        out.append((level, list(stack), title, page))
    return out


def _topic_for_page(toc_flat: list[tuple[int, list[str], str, int]], page_num: int) -> tuple[str, list[str]]:
    """Return (topic_title, topic_path) - the deepest TOC entry whose page <= page_num."""
    last_path: list[str] = []
    last_title = ""
    for level, path, title, page in toc_flat:
        if page > page_num:
            break
        last_path = path
        last_title = title
    return last_title, last_path


def _heading_above(blocks: list[dict], img_bbox: tuple) -> str:
    """Find a likely heading text just above the image block."""
    img_top = img_bbox[1]
    candidates: list[tuple[float, str]] = []
    for b in blocks:
        if b["type"] != 0:
            continue
        bx0, by0, bx1, by1 = b["bbox"]
        if by1 > img_top - 4 or by1 < img_top - 200:
            continue
        text = " ".join(
            "".join(s["text"] for s in line["spans"])
            for line in b["lines"]
        ).strip()
        if not text:
            continue
        if len(text) > 200:
            text = text[:197] + "..."
        candidates.append((img_top - by1, text))
    if not candidates:
        return ""
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def _caption_below(blocks: list[dict], img_bbox: tuple) -> str:
    img_bot = img_bbox[3]
    for b in blocks:
        if b["type"] != 0:
            continue
        bx0, by0, bx1, by1 = b["bbox"]
        if by0 < img_bot - 4:
            continue
        if by0 - img_bot > 80:
            continue
        text = " ".join(
            "".join(s["text"] for s in line["spans"])
            for line in b["lines"]
        ).strip()
        if not text:
            continue
        if len(text) > 200:
            text = text[:197] + "..."
        return text
    return ""


def _page_text(blocks: list[dict], img_bbox: tuple, vertical_window: int = 300) -> str:
    img_cy = (img_bbox[1] + img_bbox[3]) / 2
    chunks: list[tuple[float, str]] = []
    for b in blocks:
        if b["type"] != 0:
            continue
        bx0, by0, bx1, by1 = b["bbox"]
        block_cy = (by0 + by1) / 2
        if abs(block_cy - img_cy) > vertical_window:
            continue
        text = " ".join(
            "".join(s["text"] for s in line["spans"])
            for line in b["lines"]
        ).strip()
        if text:
            chunks.append((block_cy, text))
    chunks.sort(key=lambda x: x[0])
    return "\n".join(c[1] for c in chunks)


def extract(pdf_path: str | Path, output_dir: Path = ASSETS_ROOT) -> dict:
    """Walk the PDF, save one PNG per diagram, and write manifest.json."""
    import pymupdf as fitz  # imported here so runtime doesn't depend on it

    pdf_path = Path(pdf_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))
    toc_flat = _flatten_toc(doc.get_toc())

    diagrams: list[dict] = []
    skipped_small = 0

    for i in range(doc.page_count):
        page = doc[i]
        page_num = i + 1
        page_dict = page.get_text("dict")
        blocks = page_dict["blocks"]

        img_blocks = [b for b in blocks if b["type"] == 1]
        if not img_blocks:
            continue

        for j, b in enumerate(img_blocks):
            bbox = b["bbox"]
            w_pt = bbox[2] - bbox[0]
            h_pt = bbox[3] - bbox[1]
            if w_pt < MIN_DIAGRAM_WIDTH_PT or h_pt < MIN_DIAGRAM_HEIGHT_PT:
                skipped_small += 1
                continue

            mat = fitz.Matrix(RENDER_SCALE, RENDER_SCALE)
            try:
                pix = page.get_pixmap(matrix=mat, clip=bbox, alpha=False)
            except Exception as e:
                print(f"  [skip] page {page_num} block {j}: render failed: {e}")
                continue

            png_path = DIAGRAMS_DIR / f"p{page_num:03d}_{j:02d}.png"
            pix.save(str(png_path))

            heading = _heading_above(blocks, bbox)
            caption = _caption_below(blocks, bbox)
            topic, topic_path = _topic_for_page(toc_flat, page_num)
            surrounding = _page_text(blocks, bbox)

            tokens_src = " ".join([heading, caption, topic, " ".join(topic_path), surrounding])
            tokens = _tokenize(tokens_src)

            diagrams.append({
                "id": f"p{page_num:03d}_{j:02d}",
                "page": page_num,
                "bbox": [round(x, 2) for x in bbox],
                "width_px": pix.width,
                "height_px": pix.height,
                "image_path": str(png_path.relative_to(ASSETS_ROOT)),
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
        "skipped_small": skipped_small,
        "diagrams": diagrams,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    print(f"[bible_diagrams] Extracted {len(diagrams)} diagrams; skipped {skipped_small} small images")
    print(f"[bible_diagrams] Manifest: {MANIFEST_PATH}")
    return manifest


# ----------------- Runtime (in-memory index) -----------------

_MANIFEST_CACHE: Optional[dict] = None
_IMAGE_CACHE: dict[tuple[str, Optional[int]], Image.Image] = {}


def load_manifest() -> dict:
    global _MANIFEST_CACHE
    if _MANIFEST_CACHE is not None:
        return _MANIFEST_CACHE
    if not MANIFEST_PATH.exists():
        _MANIFEST_CACHE = {"diagrams": []}
        return _MANIFEST_CACHE
    _MANIFEST_CACHE = json.loads(MANIFEST_PATH.read_text())
    return _MANIFEST_CACHE


def all_diagrams() -> list[dict]:
    return load_manifest().get("diagrams", [])


def get_diagram_image(diagram: dict, max_dim: Optional[int] = None) -> Optional[Image.Image]:
    """Load + cache the diagram PNG. If `max_dim` is given, scale so the larger
    side fits while preserving aspect ratio."""
    if not diagram:
        return None
    rel_path = diagram.get("image_path")
    if not rel_path:
        return None
    cache_key = (rel_path, max_dim)
    if cache_key in _IMAGE_CACHE:
        return _IMAGE_CACHE[cache_key]
    abs_path = ASSETS_ROOT / rel_path
    if not abs_path.exists():
        return None
    img = Image.open(abs_path).convert("RGBA")
    if max_dim is not None and (img.size[0] > max_dim or img.size[1] > max_dim):
        ratio = max_dim / max(img.size)
        new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
        img = img.resize(new_size, Image.LANCZOS)
    _IMAGE_CACHE[cache_key] = img
    return img


def find_diagrams_for(query: str, top_k: int = 3, exclude_ids: Optional[set[str]] = None) -> list[dict]:
    """Score diagrams against a free-text query and return the top matches.

    Scoring is a token-overlap weighted sum:
      - +5 for each query token that appears in `topic_path`
      - +3 for each token in `heading_above`
      - +1 per matching surrounding-text token
    """
    diagrams = all_diagrams()
    if not diagrams:
        return []
    qtokens = _tokenize(query)
    if not qtokens:
        return []
    qcounts = Counter(qtokens)

    exclude_ids = exclude_ids or set()
    scored: list[tuple[float, dict]] = []
    for d in diagrams:
        if d["id"] in exclude_ids:
            continue
        score = 0.0
        topic_tokens = set(_tokenize(" ".join(d.get("topic_path", []) + [d.get("topic", "")])))
        for t in qcounts:
            if t in topic_tokens:
                score += 5.0 * qcounts[t]
        heading_tokens = set(_tokenize(d.get("heading_above", "")))
        for t in qcounts:
            if t in heading_tokens:
                score += 3.0 * qcounts[t]
        body_tokens = set(d.get("tokens", []))
        for t in qcounts:
            if t in body_tokens:
                score += 1.0 * qcounts[t]
        if score > 0:
            scored.append((score, d))

    scored.sort(key=lambda kv: -kv[0])
    return [d for _, d in scored[:top_k]]


def find_best_diagram_for(query: str, exclude_ids: Optional[set[str]] = None) -> Optional[dict]:
    matches = find_diagrams_for(query, top_k=1, exclude_ids=exclude_ids)
    return matches[0] if matches else None


# ----------------- CLI -----------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bible diagram extractor + indexer")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_ext = sub.add_parser("extract", help="Extract diagrams from PDF into manifest")
    p_ext.add_argument("pdf", help="Path to Nutanix Cloud Bible PDF")
    p_ext.add_argument("--out", default=str(ASSETS_ROOT), help="Output assets dir")
    p_search = sub.add_parser("search", help="Search the manifest for a query")
    p_search.add_argument("query", nargs="+", help="Query words")
    p_search.add_argument("--top", type=int, default=5)
    args = parser.parse_args()

    if args.cmd == "extract":
        extract(args.pdf, Path(args.out))
    elif args.cmd == "search":
        q = " ".join(args.query)
        for d in find_diagrams_for(q, top_k=args.top):
            print(f"  page {d['page']} ({d['width_px']}x{d['height_px']}) -> {d['topic']}  | heading: {d['heading_above'][:60]!r}")
