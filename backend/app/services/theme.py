"""Signature visual design tokens for generated videos.

There is ONE signature look - a deep, modern "midnight" base with crisp Sora/Inter
typography - and a small set of curated, on-brand *accent* variations the style
engine can choose between per video (see theme_engine.py). Everything here is a
plain token (colors, type scale, spacing) so both the static slide generator and
the animation overlays render from the same source of truth.

Design space is 1920x1080 (the slide canvas + animation design space). Sizes are
in design pixels; the animation layer scales them to the render resolution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

RGB = tuple[int, int, int]
RGBA = tuple[int, int, int, int]

# ---------------- Signature base (constant across all videos) ----------------

# Deep midnight gradient - richer and less flat than a single navy.
BG_TOP: RGB = (8, 9, 22)
BG_BOTTOM: RGB = (20, 17, 48)

# Text ramp tuned for the dark base (all clear WCAG AA on BG_*).
TEXT: RGB = (245, 247, 252)
TEXT_MUTED: RGB = (174, 184, 208)
TEXT_DIM: RGB = (116, 122, 148)

# Translucent glass surfaces for cards/panels.
SURFACE: RGBA = (255, 255, 255, 13)
SURFACE_STRONG: RGBA = (255, 255, 255, 20)
SURFACE_BORDER: RGBA = (255, 255, 255, 33)

RADIUS = 26          # default card corner radius (design px)
RADIUS_SM = 16
MARGIN = 130         # default content margin from canvas edge

# Type scale (design px). Display weights use Sora; body uses Inter.
TYPE = {
    "hero": 104,
    "display": 84,
    "title": 66,
    "h2": 46,
    "lead": 34,
    "body": 28,
    "label": 26,
    "caption": 24,
    "small": 20,
    "tiny": 16,
}

# ---------------- Accent palette (named, on-brand) ----------------

TEAL: RGB = (45, 224, 230)
CYAN: RGB = (70, 170, 250)
BLUE: RGB = (96, 142, 255)
INDIGO: RGB = (130, 110, 255)
VIOLET: RGB = (165, 120, 255)
GREEN: RGB = (74, 222, 160)
LIME: RGB = (146, 221, 95)
CORAL: RGB = (255, 138, 92)
AMBER: RGB = (255, 196, 75)
PINK: RGB = (240, 110, 200)
ROSE: RGB = (255, 120, 150)


@dataclass(frozen=True)
class Accent:
    """A curated accent identity: a primary/secondary pair for gradient text and
    dividers, a harmonized multi-item palette for card grids, and a mood that
    drives the backdrop glow temperature."""
    key: str
    mood: str                 # "cool" | "warm" | "neutral"
    primary: RGB
    secondary: RGB
    palette: tuple[RGB, ...]  # >=4 harmonized accents for numbered/key_points/etc.


# All combinations are bright on the midnight base, so any choice stays legible.
ACCENTS: dict[str, Accent] = {
    "teal_indigo": Accent("teal_indigo", "cool", TEAL, INDIGO, (TEAL, INDIGO, CYAN, GREEN)),
    "blue_cyan": Accent("blue_cyan", "cool", CYAN, TEAL, (CYAN, TEAL, INDIGO, GREEN)),
    "green_teal": Accent("green_teal", "cool", GREEN, TEAL, (GREEN, TEAL, CYAN, LIME)),
    "violet_teal": Accent("violet_teal", "neutral", VIOLET, TEAL, (VIOLET, TEAL, PINK, GREEN)),
    "indigo_pink": Accent("indigo_pink", "neutral", INDIGO, PINK, (INDIGO, PINK, TEAL, AMBER)),
    "coral_amber": Accent("coral_amber", "warm", CORAL, AMBER, (CORAL, AMBER, PINK, VIOLET)),
    "rose_violet": Accent("rose_violet", "warm", ROSE, VIOLET, (ROSE, VIOLET, AMBER, TEAL)),
}

DEFAULT_ACCENT = "teal_indigo"

# Backdrop glow colors per mood (deep, low-alpha washes - kept tasteful).
_GLOWS: dict[str, tuple[RGB, ...]] = {
    "cool": (INDIGO, TEAL, BLUE),
    "warm": (CORAL, PINK, AMBER),
    "neutral": (INDIGO, TEAL, VIOLET),
}


@dataclass
class VideoStyle:
    """The fully-resolved look for one video. Constructed by build_style and
    threaded through slide_image_generator + the animation TemplateContext."""
    accent_key: str = DEFAULT_ACCENT
    mood: str = "cool"
    bg_intensity: str = "calm"        # "calm" | "rich"

    bg_top: RGB = BG_TOP
    bg_bottom: RGB = BG_BOTTOM
    glows: tuple[RGB, ...] = field(default_factory=lambda: _GLOWS["cool"])

    accent: RGB = TEAL
    accent2: RGB = INDIGO
    palette: tuple[RGB, ...] = field(default_factory=lambda: ACCENTS[DEFAULT_ACCENT].palette)

    text: RGB = TEXT
    text_muted: RGB = TEXT_MUTED
    text_dim: RGB = TEXT_DIM
    surface: RGBA = SURFACE
    surface_border: RGBA = SURFACE_BORDER

    def accent_at(self, i: int) -> RGB:
        """Stable accent for the i-th item in a multi-item layout."""
        return self.palette[i % len(self.palette)]

    def pair_at(self, i: int) -> tuple[RGB, RGB]:
        """A (primary, secondary) accent pair offset by i, for per-slide variety
        that still stays within the chosen palette."""
        p = self.palette
        return p[i % len(p)], p[(i + 1) % len(p)]


# ---------------- Contrast / legibility helpers ----------------

def _srgb_to_linear(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb: RGB) -> float:
    r, g, b = (_srgb_to_linear(x) for x in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: RGB, bg: RGB) -> float:
    """WCAG contrast ratio (1..21) between two colors."""
    l1, l2 = relative_luminance(fg), relative_luminance(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def ensure_legible(fg: RGB, bg: RGB, min_ratio: float = 3.0) -> RGB:
    """Lighten ``fg`` toward white until it clears ``min_ratio`` against ``bg``.

    Used as a safety net for text/accents on the dark base; the curated accents
    already pass, so this is a no-op for them but guards any future additions.
    """
    if contrast_ratio(fg, bg) >= min_ratio:
        return fg
    r, g, b = fg[:3]
    for t in (i / 10 for i in range(1, 11)):
        cand = (int(r + (255 - r) * t), int(g + (255 - g) * t), int(b + (255 - b) * t))
        if contrast_ratio(cand, bg) >= min_ratio:
            return cand
    return (255, 255, 255)


def build_style(accent_key: str = DEFAULT_ACCENT,
                mood: Optional[str] = None,
                bg_intensity: str = "calm") -> VideoStyle:
    """Resolve a curated accent + mood + intensity into a full VideoStyle.

    Inputs are clamped to the curated sets, so the result is always on-brand and
    legible regardless of what the LLM proposed.
    """
    accent = ACCENTS.get(accent_key) or ACCENTS[DEFAULT_ACCENT]
    mood = mood if mood in _GLOWS else accent.mood
    bg_intensity = bg_intensity if bg_intensity in ("calm", "rich") else "calm"

    # Legibility safety net: lighten anything that doesn't clear contrast on the
    # base. The curated tokens already pass (verified), so this is a no-op for
    # them but guards any future accent/text additions.
    bg = BG_BOTTOM
    return VideoStyle(
        accent_key=accent.key,
        mood=mood,
        bg_intensity=bg_intensity,
        bg_top=BG_TOP,
        bg_bottom=BG_BOTTOM,
        glows=_GLOWS[mood],
        accent=ensure_legible(accent.primary, bg, 3.0),
        accent2=ensure_legible(accent.secondary, bg, 3.0),
        palette=tuple(ensure_legible(c, bg, 3.0) for c in accent.palette),
        text=ensure_legible(TEXT, bg, 4.5),
        text_muted=ensure_legible(TEXT_MUTED, bg, 4.5),
        text_dim=TEXT_DIM,
        surface=SURFACE,
        surface_border=SURFACE_BORDER,
    )


DEFAULT_STYLE = build_style()
