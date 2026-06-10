"""
Scene templates - turn a (title, body, audio_path, timeline, extras) bundle
into a fully-populated Scene with timed cues.

Each template is a function `build_<name>(ctx) -> Scene` and takes a
`TemplateContext` with the inputs it needs.

Animation templates are paired with the slide layouts produced by
`slide_image_generator`. When `slide_image_generator.OMIT_FOCAL_ICONS=True`
(the default during animated rendering) the static slide draws the title /
body / cards / footer but skips focal brand icons. Each template here
reveals those icons at positions matching the slide layout, so the visual
rhythm is "the slide draws itself, then icons pop in on cue".

Templates also emit a closing caption near the bottom that summarises the
scene, and a soft pulse ring around revealed icons to keep the screen alive.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from PIL import Image

from app.services import icon_library
from app.services import bible_diagrams
from app.services.animation.primitives import (
    CANVAS_W, CANVAS_H,
    PURPLE, PURPLE_LIGHT, TEAL, GREEN, CORAL, YELLOW, PINK, WHITE,
)
from app.services.animation.types import Beat, Cue, Scene


@dataclass
class TemplateContext:
    title: str
    body: str
    duration: float
    audio_path: str
    background_image: str
    section_index: int = -1
    motion_seed: int = 0
    word_timeline: list[dict] = field(default_factory=list)
    layout: str = "default"
    slide_num: int = 0
    total_slides: int = 0
    extra: dict = field(default_factory=dict)


# Accent palettes mirror slide_image_generator.ACCENT_PALETTES (primary, secondary).
ACCENT_PALETTES = [
    (TEAL, PURPLE_LIGHT),
    (CORAL, YELLOW),
    (GREEN, TEAL),
    (PURPLE_LIGHT, PINK),
    (YELLOW, CORAL),
    (PINK, PURPLE_LIGHT),
]


# ---------------- Word-timeline helpers ----------------

def _word_starts_with(timeline: list[dict], words: list[str]) -> Optional[float]:
    if not timeline:
        return None
    targets = [w.lower() for w in words]
    for entry in timeline:
        w = entry["word"].lower().strip(",.!?:;'\"()[]")
        if any(w == t or w.startswith(t) for t in targets):
            return float(entry["start"])
    return None


def _times_for_words(timeline: list[dict], words: list[str], limit: int = 5) -> list[float]:
    if not timeline:
        return []
    targets = [w.lower() for w in words]
    out: list[float] = []
    for entry in timeline:
        w = entry["word"].lower().strip(",.!?:;'\"()[]")
        if any(w == t for t in targets):
            out.append(float(entry["start"]))
            if len(out) >= limit:
                break
    return out


def _evenly_spaced(start: float, end: float, n: int) -> list[float]:
    if n <= 0:
        return []
    span = max(0.1, end - start)
    step = span / (n + 1)
    return [start + step * (i + 1) for i in range(n)]


def _icon_path(concept: str, size: int = 512) -> Optional[str]:
    actual = icon_library._resolve_concept(concept)
    if actual is None:
        return None
    lib = icon_library.load_manifest()
    entries = lib["concepts"].get(actual)
    if not entries:
        return None
    sizes = entries[0].get("sizes", {})
    rel = sizes.get(str(size)) or sizes.get("512") or sizes.get("256")
    if not rel:
        return None
    return str(icon_library.ASSETS_ROOT / rel)


def _accent_for(slide_num: int) -> tuple:
    return ACCENT_PALETTES[slide_num % len(ACCENT_PALETTES)]


# ---------------- Closing caption ----------------

def _caption_cue(text: str, start: float, end: float, z: int = 80) -> Cue:
    fade = 0.6
    end_anim = min(start + fade, end)
    return Cue(
        kind="caption",
        start=start,
        end=end_anim,
        params={"text": text, "y": 940},
        ease="out",
        z=z,
        hold=max(0.0, end - end_anim),
    )


def _first_sentence(text: str, max_chars: int = 90) -> str:
    if not text:
        return ""
    for sep in [". ", "! ", "? "]:
        idx = text.find(sep)
        if 10 < idx < max_chars + 30:
            return text[:idx + 1].strip()
    return text[:max_chars].rstrip() + ("..." if len(text) > max_chars else "")


# ---------------- Beat timing + kinetic captions ----------------

def _resolve_beat_times(beats: list[dict], timeline: list[dict], duration: float,
                        head: float = 0.6, tail: float = 1.0) -> list[float]:
    """Map each beat to a scene-time, preferring its narration anchor word.

    Anchors that resolve against the word timeline pin the beat to the voice;
    unresolved beats are evenly spaced. Times are forced monotonic with a small
    minimum gap so captions never stack on top of each other.
    """
    n = len(beats)
    if n == 0:
        return []
    span_end = max(head + 2.0, duration - tail)
    even = _evenly_spaced(head, span_end, n)
    times: list[float] = []
    for i, b in enumerate(beats):
        anchor = (b.get("anchor") or "").strip()
        t = _word_starts_with(timeline, [anchor]) if anchor else None
        times.append(t if t is not None else even[i])
    # Enforce monotonic order with a minimum spacing.
    min_gap = max(1.2, (span_end - head) / (n + 1) * 0.6)
    for i in range(1, n):
        if times[i] <= times[i - 1] + min_gap:
            times[i] = times[i - 1] + min_gap
    return [max(head, min(t, span_end)) for t in times]


def _beat_caption_cues(beats: list[dict], timeline: list[dict], duration: float,
                       z: int = 80) -> list[Cue]:
    """One rolling bottom caption per beat, each anchored to its narration word
    and held until the next beat fires. Replaces the old single canned caption so
    on-screen text tracks the voice and keeps delivering value."""
    cues: list[Cue] = []
    times = _resolve_beat_times(beats, timeline, duration)
    for i, b in enumerate(beats):
        text = (b.get("text") or "").strip()
        if not text:
            continue
        start = times[i]
        end_of_life = times[i + 1] if i + 1 < len(times) else duration
        fade = 0.45
        end_anim = min(start + fade, end_of_life)
        cues.append(Cue(
            kind="caption", start=start, end=end_anim,
            params={"text": text, "y": 944}, ease="out", z=z,
            hold=max(0.0, end_of_life - end_anim),
        ))
    return cues


def _closing_cues(ctx: TemplateContext, fallback_text: str) -> list[Cue]:
    """Kinetic beat captions when the visual script supplies beats; otherwise a
    single closing caption (legacy behavior)."""
    beats = ctx.extra.get("beats") or []
    if beats:
        return _beat_caption_cues(beats, ctx.word_timeline, ctx.duration)
    return [_caption_cue(fallback_text, max(ctx.duration - 3.0, 0.5), ctx.duration)]


def _beat_list_cues(beats: list[dict], timeline: list[dict], duration: float,
                    x: int = 90, y0: int = 470, line_gap: int = 96,
                    font_size: int = 40, accents: Optional[list] = None) -> list[Cue]:
    """Reveal beats as a centered, building bullet list (kinetic typography).

    Used by scenes whose center would otherwise be empty (e.g. the generic
    `default`/`analogy` layouts without a diagram) so the screen keeps filling
    with value, each line typed in as the narration reaches its anchor word.
    """
    accents = accents or [TEAL, GREEN, CORAL, YELLOW]
    cues: list[Cue] = []
    times = _resolve_beat_times(beats, timeline, duration)
    for i, b in enumerate(beats):
        text = (b.get("text") or "").strip()
        if not text:
            continue
        t0 = times[i]
        type_dur = max(0.4, min(1.1, len(text) * 0.035))
        y = y0 + i * line_gap
        color = accents[i % len(accents)]
        # Colored bullet that pops, then the line types in beside it.
        cues.append(Cue("chip", t0, t0 + 0.4, {
            "text": str(i + 1), "anchor_xy": (x, y),
            "bg": color, "fg": (10, 14, 38, 255), "font_size": 24,
        }, ease="back", z=30 + i))
        cues.append(Cue("text_in", t0 + 0.15, t0 + 0.15 + type_dur, {
            "text": text, "anchor_xy": (x + 64, y + 4),
            "font_size": font_size, "font_weight": "bold",
            "color": WHITE, "cursor": False,
        }, ease="linear", z=31 + i, hold=float("inf")))
    return cues


# ---------------- Template: hero ----------------

def _hero_hook(title: str) -> str:
    """A short value-promise hook for the opening scene, derived from the title."""
    t = re.sub(r"\s+", " ", (title or "").strip()).rstrip(".!?")
    if not t:
        return "Here's the big idea - made simple."
    if len(t) > 38:
        t = t[:37].rstrip() + "\u2026"
    return f"{t} - made simple."


def build_hero(ctx: TemplateContext) -> Scene:
    cues: list[Cue] = []
    duration = ctx.duration

    concept = icon_library.best_concept_for_text(ctx.title, fallback="cloud_node")
    icon_p = _icon_path(concept) if concept else _icon_path("cloud_node")

    cx, cy = (280, CANVAS_H // 2)

    if icon_p:
        # Fast reveal so something moves in the first second (the hook).
        cues.append(Cue("icon_reveal", 0.3, 1.1, {
            "icon": icon_p, "center": (cx, cy), "size": 320,
            "glow": PURPLE_LIGHT, "glow_alpha": 170,
        }, ease="back", z=10))
        cues.append(Cue("pulse_ring", 1.0, max(duration - 0.5, 4.0), {
            "center": (cx, cy), "base_radius": 200,
            "max_radius": 300, "color": PURPLE_LIGHT, "cycles": 3, "width": 4,
        }, ease="linear", z=11))

    # Hook caption appears early and holds, promising value up front.
    cues.append(_caption_cue(_hero_hook(ctx.title), 0.9, duration))

    return Scene(
        title=ctx.title, duration=duration, audio_path=ctx.audio_path,
        background_image=ctx.background_image, template="hero",
        section_index=ctx.section_index, motion_seed=ctx.motion_seed,
        beats=[Beat("hero", 0, duration, cues)],
    )


# ---------------- Template: outro ----------------

def build_outro(ctx: TemplateContext) -> Scene:
    cues: list[Cue] = [
        _caption_cue("Thanks for watching - keep exploring!",
                     0.5, ctx.duration),
    ]
    return Scene(
        title=ctx.title, duration=ctx.duration, audio_path=ctx.audio_path,
        background_image=ctx.background_image, template="outro",
        section_index=ctx.section_index, motion_seed=ctx.motion_seed,
        beats=[Beat("outro", 0, ctx.duration, cues)],
    )


# ---------------- Template: analogy ----------------

def build_analogy(ctx: TemplateContext) -> Scene:
    """Reveals the focal icon center-left where the analogy slide expects it."""
    cues: list[Cue] = []
    duration = ctx.duration
    accent = _accent_for(ctx.slide_num)

    concept = icon_library.best_concept_for_text(
        f"{ctx.title} {ctx.body}", fallback="lightbulb", title=ctx.title,
    )
    icon_p = _icon_path(concept) if concept else None

    cx, cy = (280, 460)
    reveal_at = _word_starts_with(ctx.word_timeline, ["imagine", "picture", "think", "remember"]) or 0.6
    reveal_at = max(0.4, min(reveal_at, duration * 0.25))

    if icon_p:
        cues.append(Cue("icon_reveal", reveal_at, reveal_at + 1.0, {
            "icon": icon_p, "center": (cx, cy), "size": 360,
            "glow": accent[0], "glow_alpha": 150,
            "tag": (concept or "").replace("_", " ") if concept else None,
        }, ease="back", z=10))
        cues.append(Cue("pulse_ring", reveal_at + 1.0, max(duration - 0.5, reveal_at + 4.0), {
            "center": (cx, cy), "base_radius": 220,
            "max_radius": 320, "color": accent[1], "cycles": 3, "width": 4,
        }, ease="linear", z=11))

    beats = ctx.extra.get("beats") or []
    if beats:
        # Building bullet list in the right-hand text column (icon sits left).
        cues.extend(_beat_list_cues(beats, ctx.word_timeline, duration,
                                    x=560, y0=430, line_gap=92, font_size=38))
    else:
        cues.append(_caption_cue(_first_sentence(ctx.body) or ctx.title,
                                 max(duration - 3.0, 0.5), duration))

    return Scene(
        title=ctx.title, duration=duration, audio_path=ctx.audio_path,
        background_image=ctx.background_image, template="analogy",
        section_index=ctx.section_index, motion_seed=ctx.motion_seed,
        beats=[Beat("analogy", 0, duration, cues)],
    )


# ---------------- Template: comparison ----------------

def build_comparison(ctx: TemplateContext) -> Scene:
    """Two-card comparison: the old way (left) vs the new way (right)."""
    cues: list[Cue] = []
    duration = ctx.duration

    left_icon = _icon_path("three_tier") or _icon_path("silos") or _icon_path("datacenter")
    right_icon = _icon_path("distributed_cloud") or _icon_path("cluster") or _icon_path("cloud_node")

    # Slide places small icons in top-right corner of each card.
    # Card dims (from slide_image_generator): card_w=720, gap, with margins.
    # Approx top-right of left card  : (820,  430)
    # Approx top-right of right card : (1740, 430)
    left_cx, left_cy = 820, 430
    right_cx, right_cy = 1740, 430

    left_at = 0.6
    right_at = max(left_at + 1.4, duration * 0.30)
    vs_at = max(right_at + 1.4, duration * 0.55)

    if left_icon:
        cues.append(Cue("icon_reveal", left_at, left_at + 1.0, {
            "icon": left_icon, "center": (left_cx, left_cy), "size": 130,
            "glow": CORAL, "glow_alpha": 130,
        }, ease="back", z=10))

    if right_icon:
        cues.append(Cue("icon_reveal", right_at, right_at + 1.0, {
            "icon": right_icon, "center": (right_cx, right_cy), "size": 130,
            "glow": TEAL, "glow_alpha": 130,
        }, ease="back", z=10))

    # Pulse around the slide's static VS badge (slide_image_generator draws it).
    cues.append(Cue("pulse_ring", vs_at, max(duration - 0.5, vs_at + 4.0), {
        "center": (CANVAS_W // 2, 540), "base_radius": 90,
        "max_radius": 150, "color": YELLOW, "cycles": 3, "width": 4,
    }, ease="linear", z=20))

    cues.extend(_closing_cues(ctx, "The old way versus the new way."))

    return Scene(
        title=ctx.title, duration=duration, audio_path=ctx.audio_path,
        background_image=ctx.background_image, template="comparison",
        section_index=ctx.section_index, motion_seed=ctx.motion_seed,
        beats=[Beat("compare", 0, duration, cues)],
    )


# ---------------- Template: numbered_reveal ----------------

def build_numbered_reveal(ctx: TemplateContext) -> Scene:
    """Numbered grid - reveal each card's icon on cue word ('first', 'second', ...)."""
    cues: list[Cue] = []
    duration = ctx.duration

    points = ctx.extra.get("points") or []
    if not points:
        # Fallback: use slide_image_generator's _extract_sentences logic.
        import re as _re
        sents = _re.split(r"(?<=[.!?])\s+", ctx.body.strip())
        points = [s.strip() for s in sents if s.strip()][:4]
    n = max(1, min(len(points), 4))

    anchors = _times_for_words(
        ctx.word_timeline,
        ["first", "second", "third", "fourth", "next", "finally"],
        limit=n,
    )
    if len(anchors) < n:
        last = anchors[-1] if anchors else 0.6
        anchors = anchors + _evenly_spaced(last + 0.4, max(duration - 4.0, last + 4.0), n - len(anchors))

    palette = [TEAL, GREEN, CORAL, YELLOW]

    # Slide layout: numbered grid is 2 cols x N rows.
    # Card grid uses (CANVAS_W - 240) // cols cards. For n<=4 it's 2x2, for n=2 a single row, etc.
    # We'll mirror slide_image_generator.render_numbered's grid for icon placement.
    if n == 1:
        cards = [(CANVAS_W // 2 - 350, 380, 700, 320)]
    elif n == 2:
        cards = [(140, 440, 800, 280), (980, 440, 800, 280)]
    elif n == 3:
        # The slide does cols=2, ceil(3/2)=2 rows. We mirror.
        col_w = (CANVAS_W - 240 - 30) // 2
        h = 320
        y0 = 380
        cards = [
            (140, y0, col_w, h),
            (140 + col_w + 30, y0, col_w, h),
            (140 + (col_w + 30) // 2, y0 + h + 30, col_w, h),
        ]
    else:  # n == 4
        col_w = (CANVAS_W - 240 - 30) // 2
        h = 280
        y0 = 380
        cards = [
            (140, y0, col_w, h),
            (140 + col_w + 30, y0, col_w, h),
            (140, y0 + h + 30, col_w, h),
            (140 + col_w + 30, y0 + h + 30, col_w, h),
        ]

    for i in range(n):
        x, y, w, h = cards[i]
        t0 = anchors[i] if i < len(anchors) else (1.0 + i * 2.5)
        color = palette[i % len(palette)]

        body_text = points[i] if i < len(points) else ""
        concept = icon_library.best_concept_for_text(body_text, fallback=None) if body_text else None
        icon_p = _icon_path(concept) if concept else _icon_path("lightbulb")

        if icon_p:
            ic_size = 78 if h < 250 else 92
            ic_cx = x + w - ic_size // 2 - 22
            ic_cy = y + h - ic_size // 2 - 22
            cues.append(Cue("icon_reveal", t0, t0 + 0.9, {
                "icon": icon_p, "center": (ic_cx, ic_cy), "size": ic_size,
                "glow": color, "glow_alpha": 110,
            }, ease="back", z=15 + i))
            cues.append(Cue("highlight_box", t0, t0 + 0.8, {
                "box": (x, y, x + w, y + h),
                "color": color, "width": 4, "radius": 18,
            }, ease="out", z=8 + i, hold=0.0))

    cues.extend(_closing_cues(ctx, f"{n} key ideas to remember."))

    return Scene(
        title=ctx.title, duration=duration, audio_path=ctx.audio_path,
        background_image=ctx.background_image, template="numbered_reveal",
        section_index=ctx.section_index, motion_seed=ctx.motion_seed,
        beats=[Beat("points", 0, duration, cues)],
    )


# ---------------- Template: key_points ----------------

def build_key_points(ctx: TemplateContext) -> Scene:
    """Reveal a row of key-point cards with their icons sequentially."""
    cues: list[Cue] = []
    duration = ctx.duration

    import re as _re
    sents = _re.split(r"(?<=[.!?])\s+", ctx.body.strip())
    points = [s.strip() for s in sents if s.strip()][:4]
    n = max(1, len(points))
    if n == 0:
        n = 1

    palette = [TEAL, CORAL, GREEN, YELLOW]

    # Slide layout: card_y = 380, card_w = (CANVAS_W - 240) // n
    card_y = 380
    card_w = (CANVAS_W - 240) // n
    icon_size = 140

    times = _evenly_spaced(0.6, max(duration - 4.0, 4.0), n)

    for i in range(n):
        x = 100 + i * (card_w + 20)
        accent = palette[i % len(palette)]
        ic_cx = x + (card_w - 20) // 2
        ic_cy = card_y + 60 + icon_size // 2

        body_text = points[i] if i < len(points) else ""
        concept = icon_library.best_concept_for_text(body_text, fallback="lightbulb") if body_text else "lightbulb"
        icon_p = _icon_path(concept)

        if icon_p:
            cues.append(Cue("icon_reveal", times[i], times[i] + 0.9, {
                "icon": icon_p, "center": (ic_cx, ic_cy), "size": icon_size,
                "glow": accent, "glow_alpha": 110,
            }, ease="back", z=10 + i))
            cues.append(Cue("highlight_box", times[i], times[i] + 0.7, {
                "box": (x, card_y, x + card_w - 20, card_y + 540),
                "color": accent, "width": 4, "radius": 20,
            }, ease="out", z=8 + i, hold=0.0))

    cues.extend(_closing_cues(ctx, "Key takeaways to keep in mind."))

    return Scene(
        title=ctx.title, duration=duration, audio_path=ctx.audio_path,
        background_image=ctx.background_image, template="key_points",
        section_index=ctx.section_index, motion_seed=ctx.motion_seed,
        beats=[Beat("points", 0, duration, cues)],
    )


# ---------------- Template: architecture_stack ----------------

def build_architecture_stack(ctx: TemplateContext) -> Scene:
    """Reveal the 4 layers of the architecture stack bottom-up with icons on each side."""
    cues: list[Cue] = []
    duration = ctx.duration

    layers = [
        ("Applications",      "user_vms",      PURPLE_LIGHT),
        ("Platform Services", "nutanix_files", TEAL),
        ("Core (AOS + AHV)",  "cvm",           GREEN),
        ("Infrastructure",    "server",        CORAL),
    ]

    # Slide layer geometry from render_architecture: layer_w = CANVAS_W - 200,
    # base_y = 360, layer_h = 130 + 14 spacing.
    base_y = 360
    layer_h = 130
    spacing = 14
    icon_cx_left = 170
    layer_w = CANVAS_W - 200
    icon_cx_right = 100 + layer_w - 80

    times = _evenly_spaced(0.4, max(duration - 4.0, 4.0), 4)

    secondary_concepts = ["application", "calm", "ahv", "storage"]

    for i, (name, concept, color) in enumerate(layers):
        t0 = times[i]
        y_layer = base_y + i * (layer_h + spacing)
        ic_cy = y_layer + layer_h // 2

        left_p = _icon_path(concept)
        if left_p:
            cues.append(Cue("icon_reveal", t0, t0 + 0.7, {
                "icon": left_p, "center": (icon_cx_left, ic_cy), "size": 96,
                "glow": color, "glow_alpha": 100,
            }, ease="back", z=20 + i))

        right_p = _icon_path(secondary_concepts[i] if i < len(secondary_concepts) else "node")
        if right_p:
            cues.append(Cue("icon_reveal", t0 + 0.3, t0 + 1.0, {
                "icon": right_p, "center": (icon_cx_right, ic_cy), "size": 80,
            }, ease="out", z=21 + i))

        cues.append(Cue("highlight_box", t0 + 0.4, t0 + 1.1, {
            "box": (100, y_layer, 100 + layer_w, y_layer + layer_h),
            "color": color, "width": 4, "radius": 18,
        }, ease="out", z=30 + i, hold=0.0))

    cues.extend(_closing_cues(ctx, "Layers stacking into one platform."))

    return Scene(
        title=ctx.title, duration=duration, audio_path=ctx.audio_path,
        background_image=ctx.background_image, template="architecture_stack",
        section_index=ctx.section_index, motion_seed=ctx.motion_seed,
        beats=[Beat("stack", 0, duration, cues)],
    )


# ---------------- Template: bible_diagram ----------------

def build_bible_diagram(ctx: TemplateContext) -> Scene:
    """Reveal a Cloud Bible PDF diagram inside the slide's white panel.

    The slide layout (rendered with OMIT_FOCAL_ICONS=True) draws the title,
    body excerpt, white panel chrome, and source caption but skips the diagram
    image itself. This template fades the diagram in inside the panel, runs a
    pulse ring around it, and shows a closing caption.
    """
    cues: list[Cue] = []
    duration = ctx.duration
    accent = _accent_for(ctx.slide_num)

    diagram = ctx.extra.get("diagram")
    if diagram is None:
        # Fall back to default look if no diagram pinned somehow.
        return build_default(ctx)

    # Panel coords mirror render_bible_diagram in slide_image_generator.
    panel_x0 = 80
    panel_x1 = CANVAS_W - 80
    panel_top = 360
    panel_bottom = 970
    panel_w = panel_x1 - panel_x0
    panel_h = panel_bottom - panel_top
    cx = panel_x0 + panel_w // 2
    cy = panel_top + panel_h // 2
    max_w = panel_w - 60
    max_h = panel_h - 60

    diagram_img = bible_diagrams.get_diagram_image(diagram)
    if diagram_img is None:
        return build_default(ctx)

    dw, dh = diagram_img.size
    scale = min(max_w / dw, max_h / dh)
    target_w = max(1, int(dw * scale))
    target_h = max(1, int(dh * scale))
    scaled_img = diagram_img.resize((target_w, target_h), Image.LANCZOS) if (target_w, target_h) != diagram_img.size else diagram_img

    reveal_at = 0.5
    reveal_end = min(duration * 0.25, reveal_at + 1.4)

    cues.append(Cue("diagram_reveal", reveal_at, reveal_end, {
        "pil_image": scaled_img,
        "center": (cx, cy),
        "glow": accent[0],
        "glow_alpha": 130,
        "scale_start": 0.88,
    }, ease="out", z=10))

    # Subtle pulse around the panel after reveal.
    cues.append(Cue("pulse_ring", reveal_end, max(duration - 0.5, reveal_end + 4.0), {
        "center": (cx, cy),
        "base_radius": min(panel_w, panel_h) // 2 + 10,
        "max_radius": min(panel_w, panel_h) // 2 + 60,
        "color": accent[1], "cycles": 3, "width": 3,
    }, ease="linear", z=11))

    closing = (diagram.get("caption_below") or diagram.get("topic") or "").strip()
    if closing:
        if len(closing) > 90:
            closing = closing[:87] + "..."
        closing = f"Source: Nutanix Cloud Bible (page {diagram.get('page', 0)}) - {closing}"
    else:
        closing = f"Source: Nutanix Cloud Bible (page {diagram.get('page', 0)})"

    cues.append(_caption_cue(closing, max(duration - 3.0, 0.5), duration))

    return Scene(
        title=ctx.title, duration=duration, audio_path=ctx.audio_path,
        background_image=ctx.background_image, template="bible_diagram",
        section_index=ctx.section_index, motion_seed=ctx.motion_seed,
        beats=[Beat("diagram", 0, duration, cues)],
    )


# ---------------- Template: default ----------------

def build_default(ctx: TemplateContext) -> Scene:
    """Default - icon reveals at the slide's center-right with a soft pulse."""
    cues: list[Cue] = []
    duration = ctx.duration
    accent = _accent_for(ctx.slide_num)

    concept = icon_library.best_concept_for_text(
        f"{ctx.title} {ctx.body}", fallback="lightbulb", title=ctx.title,
    )
    icon_p = _icon_path(concept) if concept else _icon_path("lightbulb")

    cx, cy = (CANVAS_W - 380, 470)

    if icon_p:
        cues.append(Cue("icon_reveal", 0.5, 1.5, {
            "icon": icon_p, "center": (cx, cy), "size": 440,
            "glow": accent[0], "glow_alpha": 150,
            "tag": (concept or "").replace("_", " ") if concept else None,
        }, ease="back", z=10))
        cues.append(Cue("pulse_ring", 1.4, max(duration - 0.5, 4.0), {
            "center": (cx, cy), "base_radius": 250,
            "max_radius": 360, "color": accent[1], "cycles": 3, "width": 4,
        }, ease="linear", z=11))

    beats = ctx.extra.get("beats") or []
    if beats:
        # Fill the (otherwise empty) body area with a building bullet list.
        cues.extend(_beat_list_cues(beats, ctx.word_timeline, duration,
                                    x=90, y0=470, line_gap=96))
    else:
        cues.append(_caption_cue(_first_sentence(ctx.body) or ctx.title,
                                 max(duration - 3.0, 0.5), duration))

    return Scene(
        title=ctx.title, duration=duration, audio_path=ctx.audio_path,
        background_image=ctx.background_image, template="default",
        section_index=ctx.section_index, motion_seed=ctx.motion_seed,
        beats=[Beat("default", 0, duration, cues)],
    )


# ---------------- Template: diagram (LLM-authored animated graph) ----------------

def _edge_point(cx: float, cy: float, hw: float, hh: float,
                tx: float, ty: float) -> tuple[float, float]:
    """Point on the border of a box (center cx,cy; half-size hw,hh) along the
    direction toward (tx, ty). Lets edges start/end at node edges, not centers."""
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0:
        return cx, cy
    sx = hw / abs(dx) if dx else float("inf")
    sy = hh / abs(dy) if dy else float("inf")
    k = min(sx, sy)
    return cx + dx * k, cy + dy * k


def build_diagram(ctx: TemplateContext) -> Scene:
    """Build an animated boxes-and-arrows diagram from the LLM visual script.

    Nodes pop in one by one (anchored to narration beats), edges draw between
    them once both endpoints exist, and a flow dot travels along each edge to
    convey movement - so the diagram assembles itself while the voice explains.
    """
    duration = ctx.duration
    diagram = ctx.extra.get("diagram") or {}
    nodes = diagram.get("nodes") or []
    edges = diagram.get("edges") or []

    if len(nodes) < 2:
        return build_default(ctx)

    # Design-space content area: below the headline band, above the caption lane.
    AX0, AY0, AX1, AY1 = 130, 372, 1790, 898
    cols = max((n.get("col", 0) for n in nodes), default=0) + 1
    rows = max((n.get("row", 0) for n in nodes), default=0) + 1
    cols = max(1, min(cols, 4))
    rows = max(1, min(rows, 3))
    cell_w = (AX1 - AX0) / cols
    cell_h = (AY1 - AY0) / rows
    pad_x = min(40, cell_w * 0.10)
    pad_y = min(40, cell_h * 0.12)

    palette = [TEAL, GREEN, CORAL, PURPLE_LIGHT, YELLOW, PINK]
    geom: dict[str, dict] = {}
    for i, node in enumerate(nodes):
        col = max(0, min(node.get("col", i % cols), cols - 1))
        row = max(0, min(node.get("row", i // cols), rows - 1))
        bx0 = AX0 + col * cell_w + pad_x
        by0 = AY0 + row * cell_h + pad_y
        bx1 = AX0 + (col + 1) * cell_w - pad_x
        by1 = AY0 + (row + 1) * cell_h - pad_y
        geom[node["id"]] = {
            "box": (bx0, by0, bx1, by1),
            "cx": (bx0 + bx1) / 2, "cy": (by0 + by1) / 2,
            "hw": (bx1 - bx0) / 2, "hh": (by1 - by0) / 2,
            "color": palette[i % len(palette)],
        }

    # Reveal timing: spread node pop-ins across the first part of the scene so the
    # diagram is fully assembled around the midpoint and then *holds* (with flow
    # dots) while the voice keeps explaining. Anchoring to beat words bunched the
    # reveals late on long narrations and left the canvas empty - pace it instead.
    beats = ctx.extra.get("beats") or []
    node_span_end = min(max(2.0, duration * 0.55), 13.0)
    node_times = _evenly_spaced(0.6, node_span_end, len(nodes))

    cues: list[Cue] = []
    reveal_at: dict[str, float] = {}
    for i, node in enumerate(nodes):
        nid = node["id"]
        g = geom[nid]
        t0 = node_times[i] if i < len(node_times) else 0.6 + i * 1.5
        reveal_at[nid] = t0
        cues.append(Cue("node_box", t0, t0 + 0.7, {
            "box": g["box"], "label": node.get("label", ""),
            "color": g["color"], "icon": _icon_path(node["icon"]) if node.get("icon") else None,
        }, ease="back", z=20 + i))

    # Edges: draw after both endpoints exist, then send a flow dot along them.
    for j, edge in enumerate(edges):
        src, dst = edge.get("from"), edge.get("to")
        if src not in geom or dst not in geom:
            continue
        gs, gd = geom[src], geom[dst]
        p_start = _edge_point(gs["cx"], gs["cy"], gs["hw"], gs["hh"], gd["cx"], gd["cy"])
        p_end = _edge_point(gd["cx"], gd["cy"], gd["hw"], gd["hh"], gs["cx"], gs["cy"])
        draw_at = max(reveal_at.get(src, 0), reveal_at.get(dst, 0)) + 0.55
        draw_at = min(draw_at, max(1.0, duration - 1.5))
        color = gs["color"]
        cues.append(Cue("arrow", draw_at, draw_at + 0.6, {
            "start": p_start, "end": p_end,
            "color": color, "width": 6, "head_size": 22, "curve": 0.0,
        }, ease="out", z=14 + j, hold=float("inf")))
        # One shared flow dot per edge keeps continuous motion cheap.
        flow_start = draw_at + 0.6
        if flow_start < duration - 0.6:
            cycles = max(1, int((duration - flow_start) / 2.2))
            cues.append(Cue("flow_dot", flow_start, max(duration - 0.4, flow_start + 1.0), {
                "start": p_start, "end": p_end, "color": GREEN,
                "radius": 9, "cycles": cycles,
            }, ease="linear", z=40 + j))

    cues.extend(_beat_caption_cues(beats, ctx.word_timeline, duration))

    return Scene(
        title=ctx.title, duration=duration, audio_path=ctx.audio_path,
        background_image=ctx.background_image, template="diagram",
        section_index=ctx.section_index, motion_seed=ctx.motion_seed,
        beats=[Beat("diagram", 0, duration, cues)],
    )


# ---------------- Template: node_anatomy (unused by default; kept for storyboard heuristics) ----------------

def build_node_anatomy(ctx: TemplateContext) -> Scene:
    """For 'inside a node' / 'controller VM' content. Reveals CVM icon and arrows to compute/storage."""
    cues: list[Cue] = []
    duration = ctx.duration

    # Same position as default-layout focal icon.
    cx, cy = (CANVAS_W - 380, 470)

    cvm_icon = _icon_path("cvm") or _icon_path("cloud_node") or _icon_path("server")
    storage_icon = _icon_path("storage")
    network_icon = _icon_path("network")

    reveal_at = _word_starts_with(ctx.word_timeline, ["imagine", "picture", "meet", "every", "controller"]) or 0.6
    reveal_at = min(max(reveal_at, 0.4), duration * 0.25)

    if cvm_icon:
        cues.append(Cue("icon_reveal", reveal_at, reveal_at + 1.0, {
            "icon": cvm_icon, "center": (cx, cy), "size": 380,
            "glow": PURPLE_LIGHT, "glow_alpha": 160,
            "tag": "Controller VM",
        }, ease="back", z=10))
        cues.append(Cue("pulse_ring", reveal_at + 1.0, max(duration - 0.5, reveal_at + 4.0), {
            "center": (cx, cy), "base_radius": 230,
            "max_radius": 330, "color": PURPLE_LIGHT, "cycles": 3, "width": 3,
        }, ease="linear", z=11))

    storage_at = _word_starts_with(ctx.word_timeline, ["storage", "data", "drive", "files"])
    if storage_at is None:
        storage_at = reveal_at + 2.5
    storage_at = max(reveal_at + 1.5, min(storage_at, duration - 4.0))

    if storage_icon:
        cues.append(Cue("arrow", storage_at, storage_at + 0.8, {
            "start": (cx - 320, cy - 80), "end": (cx - 200, cy - 60),
            "color": YELLOW, "width": 7, "head_size": 20, "curve": -0.12,
        }, ease="out", z=12, hold=2.0))
        cues.append(Cue("chip", storage_at + 0.4, storage_at + 0.9, {
            "text": "Storage drives",
            "anchor_xy": (cx - 580, cy - 110),
            "bg": TEAL, "fg": (10, 14, 38, 255), "font_size": 24,
        }, ease="back", z=13))
        cues.append(Cue("icon_reveal", storage_at + 0.6, storage_at + 1.4, {
            "icon": storage_icon, "center": (cx - 600, cy + 30), "size": 130,
        }, ease="back", z=14))

    compute_at = _word_starts_with(ctx.word_timeline, ["compute", "cpu", "memory", "server"])
    if compute_at is None:
        compute_at = storage_at + 2.0
    compute_at = max(storage_at + 1.2, min(compute_at, duration - 2.5))

    if network_icon:
        cues.append(Cue("arrow", compute_at, compute_at + 0.8, {
            "start": (cx - 320, cy + 120), "end": (cx - 200, cy + 80),
            "color": CORAL, "width": 7, "head_size": 20, "curve": 0.10,
        }, ease="out", z=12, hold=2.0))
        cues.append(Cue("chip", compute_at + 0.4, compute_at + 0.9, {
            "text": "Compute + Network",
            "anchor_xy": (cx - 600, cy + 130),
            "bg": CORAL, "fg": (10, 14, 38, 255), "font_size": 24,
        }, ease="back", z=13))
        cues.append(Cue("icon_reveal", compute_at + 0.6, compute_at + 1.4, {
            "icon": network_icon, "center": (cx - 600, cy + 230), "size": 130,
        }, ease="back", z=14))

    cues.extend(_closing_cues(ctx, "Compute and storage, together in one box."))

    return Scene(
        title=ctx.title, duration=duration, audio_path=ctx.audio_path,
        background_image=ctx.background_image, template="node_anatomy",
        section_index=ctx.section_index, motion_seed=ctx.motion_seed,
        beats=[Beat("anatomy", 0, duration, cues)],
    )


TEMPLATES = {
    "hero": build_hero,
    "outro": build_outro,
    "analogy": build_analogy,
    "comparison": build_comparison,
    "numbered_reveal": build_numbered_reveal,
    "numbered": build_numbered_reveal,
    "key_points": build_key_points,
    "architecture_stack": build_architecture_stack,
    "architecture": build_architecture_stack,
    "node_anatomy": build_node_anatomy,
    "bible_diagram": build_bible_diagram,
    "diagram": build_diagram,
    "default": build_default,
}


def build(template_name: str, ctx: TemplateContext) -> Scene:
    fn = TEMPLATES.get(template_name) or build_default
    return fn(ctx)
