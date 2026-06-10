"""Render-time SOP enforcement (scene level).

Runs on the fully-built scenes just before rendering and guarantees the rules
that can only be checked once cues + durations exist:

- R7 opening hook  : the first scene shows a value promise within the first seconds.
- R8 motion floor  : no foreground "dead air" - ambient pulses fill long gaps.
- R5 caption clamp : a final hard cap on any caption text length.

Auto-correct / fail-safe: it never drops a scene, only adds/repairs cues, and
returns a list of human-readable adjustment notes for the compliance log.
The renderer already applies continuous Ken Burns motion to the background, so
this is a foreground guarantee on top of that.
"""
from __future__ import annotations

from app.services import engine_policy as policy
from app.services.animation.primitives import CANVAS_W, CANVAS_H
from app.services.animation.types import Beat, Cue, Scene

_DEFAULT_PULSE_COLOR = (120, 130, 255)


def _ambient_color(scene: Scene) -> tuple:
    """Borrow an accent already used in the scene so injected motion stays on-tone."""
    for c in scene.all_cues():
        for key in ("glow", "color"):
            val = c.params.get(key)
            if isinstance(val, (tuple, list)) and len(val) >= 3:
                return tuple(val[:3])
    return _DEFAULT_PULSE_COLOR


def _motion_intervals(scene: Scene) -> list[tuple[float, float]]:
    """Windows where a foreground cue is actively animating (progress changing)."""
    intervals = [(c.start, c.end) for c in scene.all_cues() if c.end > c.start]
    intervals.sort()
    merged: list[tuple[float, float]] = []
    for s, e in intervals:
        if merged and s <= merged[-1][1] + 0.01:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def _dead_air_gaps(scene: Scene) -> list[tuple[float, float]]:
    """Gaps in [0, duration] longer than the SOP dead-air threshold."""
    gaps: list[tuple[float, float]] = []
    cursor = 0.0
    for s, e in _motion_intervals(scene):
        if s - cursor > policy.DEAD_AIR_MAX_SECONDS:
            gaps.append((cursor, s))
        cursor = max(cursor, e)
    if scene.duration - cursor > policy.DEAD_AIR_MAX_SECONDS:
        gaps.append((cursor, scene.duration))
    return gaps


def _ambient_pulse(g0: float, g1: float, color: tuple) -> Cue:
    cycles = max(1, int((g1 - g0) / policy.AMBIENT_PULSE_PERIOD))
    return Cue(
        kind="pulse_ring",
        start=g0,
        end=g1,
        params={
            "center": (CANVAS_W // 2, CANVAS_H // 2),
            "base_radius": 120, "max_radius": 460,
            "color": color, "cycles": cycles, "width": 2,
        },
        ease="linear",
        z=2,  # behind content (content cues are z>=10)
    )


def enforce_scene_policy(scenes: list[Scene]) -> tuple[list[Scene], list[str]]:
    """Apply render-time SOP rules in place; return (scenes, adjustments)."""
    adj: list[str] = []
    if not scenes:
        return scenes, adj

    # R7 opening hook: the first scene must show something by HOOK_BY_SECONDS.
    first = scenes[0]
    has_early = any(
        c.kind == "caption" and c.start <= policy.HOOK_BY_SECONDS
        for c in first.all_cues()
    )
    if not has_early:
        hook = policy.clamp_caption(first.title or "Here's the big idea - made simple.")
        first.beats.append(Beat("hook", 0.0, first.duration, [
            Cue("caption", 0.8, min(1.4, first.duration), {"text": hook, "y": 940},
                ease="out", z=80, hold=max(0.0, first.duration - 1.4)),
        ]))
        adj.append("R7 opening hook: injected a value-promise caption on the first scene")

    # R8 motion floor + R5 caption clamp across every scene.
    pulses_added = 0
    captions_clamped = 0
    for scene in scenes:
        for c in scene.all_cues():
            if c.kind == "caption":
                text = c.params.get("text", "")
                clamped = policy.clamp_caption(text)
                if clamped != text:
                    c.params["text"] = clamped
                    captions_clamped += 1

        gaps = _dead_air_gaps(scene)
        if gaps:
            color = _ambient_color(scene)
            scene.beats.append(Beat(
                "ambient_motion", 0.0, scene.duration,
                [_ambient_pulse(g0, g1, color) for g0, g1 in gaps],
            ))
            pulses_added += len(gaps)

    if pulses_added:
        adj.append(f"R8 motion floor: added {pulses_added} ambient pulse(s) to fill dead air")
    if captions_clamped:
        adj.append(f"R5 text budget: clamped {captions_clamped} over-long caption(s)")

    return scenes, adj
