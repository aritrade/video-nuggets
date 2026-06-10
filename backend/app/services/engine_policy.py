"""The video-generation Standard Operating Plan (SOP) - the rulebook.

This module is the single source of truth for the engine's non-negotiable rules.
Every video, on every generation path, is built and then verified against these
rules. Behavior is auto-correct / fail-safe: the engine always produces a video,
downgrading gracefully to the most compliant option and logging what it changed.

The NON-NEGOTIABLE RULES
------------------------
R1  cohesive_look     One VideoStyle per video; color psychology drives the look.
R2  legibility        Text/accents clear WCAG minimums on the base (auto-lighten).
R3  visual_first      Every section is a MOVING visual (figure > diagram > icon);
                      never a static text card.
R4  source_fidelity   A matched real source figure is shown faithfully (no redraw).
R5  text_budget       No body paragraphs; on-screen beats capped to a few short lines.
R6  narration_sync    On-screen beats anchored to spoken words where possible.
R7  opening_hook      The video opens with a value promise within the first seconds.
R8  motion_floor      No dead air; foreground motion runs continuously.
R9  pacing            Scene durations kept in range; long narration is beat-spread.
R10 brand_neutrality  No third-party trademarks in on-screen text (scrubbed).
R11 accessibility     Every video emits a VTT transcript + thumbnail.
R12 zero_cost         The full SOP holds with no API key (deterministic fallbacks).

The two enforcers that consume this rulebook:
- video_director.enforce_policy  -> plan-level rules (R1-R5, R10), pre-render.
- animation.policy.enforce_scene_policy -> render-time rules (R5 clamp, R7, R8).
Both append human-readable notes to an ``adjustments`` log.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------- Thresholds (tune the SOP here, one place) ----------------

# R5 text budget
TEXT_BUDGET_MAX_BEATS = 4          # max kinetic beats kept per scene
TEXT_BUDGET_MAX_WORDS = 7          # max words per on-screen beat line
CAPTION_MAX_CHARS = 96             # hard cap on any single caption string

# R4 figure-first: token-overlap score a source figure must clear to be trusted
# (5 == one matching topic-path token; require a bit more confidence).
FIGURE_MATCH_MIN_SCORE = 8.0

# R7 opening hook must appear by this scene-time (seconds).
HOOK_BY_SECONDS = 2.5

# R8 motion floor: no foreground cue may be absent for longer than this (seconds).
DEAD_AIR_MAX_SECONDS = 3.0
AMBIENT_PULSE_PERIOD = 3.0         # spacing of injected ambient pulses

# R9 pacing bounds (seconds). Audio length is fixed, so over-long scenes are
# logged + beat-spread rather than hard-trimmed.
SCENE_MIN_SECONDS = 3.0
SCENE_MAX_SECONDS = 45.0

# R2 legibility (WCAG contrast ratios on the midnight base).
CONTRAST_TEXT_MIN = 4.5
CONTRAST_ACCENT_MIN = 3.0


# ---------------- Rule registry (for the compliance summary) ----------------

@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    why: str


RULES: tuple[Rule, ...] = (
    Rule("R1", "cohesive_look", "One intentional look per video reads as designed, not random."),
    Rule("R2", "legibility", "Viewers must be able to read every word at a glance."),
    Rule("R3", "visual_first", "Motion holds attention; the narration already speaks the text."),
    Rule("R4", "source_fidelity", "Real diagrams stay accurate when shown faithfully."),
    Rule("R5", "text_budget", "Walls of text are boring and compete with the voice."),
    Rule("R6", "narration_sync", "Visuals landing on the spoken word feel intentional."),
    Rule("R7", "opening_hook", "The first seconds decide whether viewers stay."),
    Rule("R8", "motion_floor", "Dead air feels broken; something should always move."),
    Rule("R9", "pacing", "Scenes that are too long or too short hurt comprehension."),
    Rule("R10", "brand_neutrality", "Avoid third-party trademarks in on-screen text."),
    Rule("R11", "accessibility", "Captions/transcripts make every video usable by all."),
    Rule("R12", "zero_cost", "The bar holds even with no API key (deterministic)."),
)

RULE_COUNT = len(RULES)


# ---------------- R10 brand neutrality ----------------

# Map third-party trademarks that may slip into on-screen text onto neutral,
# generic wording. Whole-word, case-insensitive. Conservative by design.
_BRAND_REPLACEMENTS: dict[str, str] = {
    "nutanix": "the platform",
    "vmware": "the hypervisor",
    "vsphere": "the hypervisor",
    "esxi": "the hypervisor",
    "hyper-v": "the hypervisor",
    "ahv": "the hypervisor",
    "prism": "the console",
}


def scrub_branding(text: str) -> tuple[str, bool]:
    """Replace third-party trademarks with neutral wording.

    Returns (clean_text, changed). Preserves leading capitalization of the
    matched word so sentence case still reads naturally.
    """
    if not text:
        return text, False
    changed = False
    out = text
    for brand, repl in _BRAND_REPLACEMENTS.items():
        pattern = re.compile(rf"\b{re.escape(brand)}\b", re.IGNORECASE)

        def _sub(m: re.Match) -> str:
            nonlocal changed
            changed = True
            word = m.group(0)
            return repl[:1].upper() + repl[1:] if word[:1].isupper() else repl

        out = pattern.sub(_sub, out)
    return out, changed


# ---------------- R5 text budget helpers ----------------

def clamp_beats(beats: list[dict],
                max_beats: int = TEXT_BUDGET_MAX_BEATS,
                max_words: int = TEXT_BUDGET_MAX_WORDS) -> list[dict]:
    """Few, short kinetic beats only. Trims count and words-per-line; scrubs brands."""
    trimmed: list[dict] = []
    for b in (beats or [])[:max_beats]:
        text = " ".join(str(b.get("text", "")).split()[:max_words]).strip()
        text, _ = scrub_branding(text)
        if text:
            trimmed.append({"anchor": b.get("anchor", ""), "text": text})
    return trimmed


def clamp_caption(text: str, max_chars: int = CAPTION_MAX_CHARS) -> str:
    text, _ = scrub_branding(text or "")
    if len(text) > max_chars:
        text = text[:max_chars - 1].rstrip() + "\u2026"
    return text


# ---------------- R3 visual-first helpers ----------------

# Scene types that, on their own (no diagram/figure), lean text-heavy and should
# be upgraded to a moving visual when possible.
_TEXT_LEANING = {"default", "key_points"}


def is_text_card(kind: str, scene_type: str) -> bool:
    """True when a section would render as a (mostly) text scene with no central
    moving visual - the case the director tries to upgrade to a diagram."""
    return kind == "minimal" and scene_type in _TEXT_LEANING
