"""Bundled typography for slide + animation rendering.

The product uses a two-family system:
- display = Sora (geometric, premium) for titles, big numerals and punchy labels
- text    = Inter (highly legible) for body copy, captions, badges and footers

The TTFs are bundled under ``app/assets/fonts`` so the rendered output is
identical locally and inside the Render container - which otherwise only ships
``fonts-dejavu-core`` and made every slide fall back to the generic DejaVuSans.
OS fonts and DejaVu remain as last-resort fallbacks.

Both ``slide_image_generator`` and ``animation.primitives`` resolve fonts
through :func:`get_font` so a single weight->file mapping drives the whole video.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

# Logical weight name -> bundled file. Display weights map to Sora; the rest to
# Inter. Callers use the same weight strings the code already passed to _font
# ("regular" / "bold" / "black"), plus the new "medium"/"semibold"/"display".
_BUNDLED = {
    "regular": "Inter-400.ttf",
    "medium": "Inter-500.ttf",
    "semibold": "Inter-600.ttf",
    "bold": "Inter-700.ttf",
    "display": "Sora-700.ttf",
    "display_semibold": "Sora-600.ttf",
    # "black" historically meant "heaviest display weight" - route it to Sora
    # ExtraBold so headlines and numerals read as a real display face.
    "black": "Sora-800.ttf",
}

# Ordered OS / distro fallbacks if a bundled file is somehow missing.
_DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_DEJAVU_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_OS_FALLBACK = {
    "regular": ["/System/Library/Fonts/Supplemental/Arial.ttf", _DEJAVU],
    "medium": ["/System/Library/Fonts/Supplemental/Arial.ttf", _DEJAVU],
    "semibold": ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", _DEJAVU_BOLD],
    "bold": ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", _DEJAVU_BOLD],
    "display": ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", _DEJAVU_BOLD],
    "display_semibold": ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", _DEJAVU_BOLD],
    "black": ["/System/Library/Fonts/Supplemental/Arial Black.ttf", _DEJAVU_BOLD],
}


@lru_cache(maxsize=512)
def get_font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    """Return a cached truetype font for a logical weight at the given size."""
    candidates: list[str] = []
    bundled = _BUNDLED.get(weight)
    if bundled:
        candidates.append(str(FONTS_DIR / bundled))
    candidates.extend(_OS_FALLBACK.get(weight, _OS_FALLBACK["regular"]))
    for path in candidates:
        try:
            if os.path.exists(path):
                return ImageFont.truetype(path, size=size)
        except Exception:
            continue
    return ImageFont.load_default()
