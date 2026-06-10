"""
Data classes for the animation engine.

A Scene is one narrated section. It owns a duration, an audio file, and a list
of Beats. A Beat is a semantic chunk of the scene anchored to specific
narration words. Cues are the actual visual commands evaluated per frame by
the renderer (icon reveal, arrow draw, count-up, fade, etc.).

A Cue is `kind + start + end + params`. The renderer dispatches `kind` to a
draw function in `primitives.py`. The draw function receives `progress`
(0.0 - 1.0 normalized through whatever easing the cue requested) plus the
cue's params. This keeps the renderer trivial - it just walks every active
cue at time t and asks the primitive to paint itself onto the canvas.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

# Type alias for an easing function: takes progress 0..1, returns eased 0..1.
EaseFn = Callable[[float], float]


# ---------------- Easing functions ----------------

def linear(t: float) -> float:
    return max(0.0, min(1.0, t))


def ease_in(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t


def ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 2


def ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 0.5 * (1.0 - math.cos(math.pi * t))


def ease_out_back(t: float) -> float:
    """Slight overshoot: useful for icons popping in."""
    t = max(0.0, min(1.0, t))
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def ease_pulse(t: float) -> float:
    """0 -> 1 -> 0 over [0,1]. Good for blink / pulse effects."""
    t = max(0.0, min(1.0, t))
    return math.sin(math.pi * t)


EASES: dict[str, EaseFn] = {
    "linear": linear,
    "in": ease_in,
    "out": ease_out,
    "in_out": ease_in_out,
    "back": ease_out_back,
    "pulse": ease_pulse,
}


def get_ease(name: str | None) -> EaseFn:
    return EASES.get(name or "out", ease_out)


# ---------------- Scene / Beat / Cue ----------------

PERSISTENT_KINDS: set[str] = {
    "icon_reveal", "diagram_reveal", "fade_in", "slide_in", "chip", "text_in",
    "node_box",
}
"""Cues whose default behavior is to stay on screen after the animation
completes. Override by setting `hold=0.0` explicitly on the cue."""


@dataclass
class Cue:
    """A single visual command active over [start, end + hold] seconds.

    The animation runs from `start` to `end`. After `end`, the cue stays
    drawn at progress=1.0 for an additional `hold` seconds. For "reveal"
    style cues (icon_reveal, fade_in, slide_in, chip, text_in) the storyboard
    typically sets hold = (scene_duration - end) so the element persists for
    the rest of the scene. Time-bounded cues (arrow, pulse_ring,
    highlight_box, count_up, spotlight) default to hold=0.

    `kind` selects the primitive that paints it. `params` is kind-specific.
    """
    kind: str
    start: float
    end: float
    params: dict[str, Any] = field(default_factory=dict)
    ease: str = "out"
    z: int = 0  # layer order; higher = drawn later (on top)
    hold: float | None = None  # if None, defaults based on kind

    def effective_hold(self) -> float:
        if self.hold is not None:
            return self.hold
        return float("inf") if self.kind in PERSISTENT_KINDS else 0.0

    def progress_at(self, t: float) -> float:
        """Normalized 0..1 progress at scene-time t, with easing applied."""
        if t < self.start:
            return 0.0
        if t >= self.end:
            return 1.0
        if self.end <= self.start:
            return 1.0
        raw = (t - self.start) / (self.end - self.start)
        return get_ease(self.ease)(raw)

    def is_active(self, t: float) -> bool:
        """Whether the cue should be considered at scene-time t."""
        return self.start <= t <= self.end + self.effective_hold()


@dataclass
class Beat:
    """A semantic chunk of the scene tied to specific narration words.

    A beat groups cues that should fire together when the narration reaches a
    given anchor word/phrase. `start` and `end` are scene-time seconds.
    """
    label: str
    start: float
    end: float
    cues: list[Cue] = field(default_factory=list)


@dataclass
class Scene:
    """One narrated section, ready to render.

    Attributes:
        title: scene/section title (used in headers, not animated by default)
        duration: total scene length in seconds (matches audio duration)
        audio_path: source mp3 to mux at render time
        background_image: static slide PNG that serves as the fixed backdrop
            (produced by Step A's slide_image_generator).
        beats: ordered list of Beats. Cues from all beats are flattened by the
            renderer; beats are mostly an organizational aid for storyboarding.
        template: name of the template used (informational).
        section_index: original ContentSection index (informational).
    """
    title: str
    duration: float
    audio_path: str
    background_image: str
    beats: list[Beat] = field(default_factory=list)
    template: str = "default"
    section_index: int = -1
    motion_seed: int = 0

    def all_cues(self) -> list[Cue]:
        """Flatten all cues from all beats, stable-sorted by z then start."""
        cues: list[Cue] = []
        for b in self.beats:
            cues.extend(b.cues)
        cues.sort(key=lambda c: (c.z, c.start))
        return cues
