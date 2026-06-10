"""Per-video style intelligence.

Decides ONE on-brand look for a whole video - which curated accent pairing,
mood and background intensity from theme.py best fit the content - so the video
feels intentional and cohesive rather than randomly colored.

Hybrid, mirroring storyboard_llm:
- If an LLM (Groq) is available, ask it to pick from the curated options. Its
  answer is whitelisted/clamped to the curated set, so it can never produce an
  off-brand or illegible combination.
- Otherwise (or on junk output) a deterministic heuristic maps topic keywords +
  structure to a style. Always succeeds at zero cost.

The result is a theme.VideoStyle threaded into both the slide generator and the
animation TemplateContext (see pipeline.py / video_composer.py).
"""
from __future__ import annotations

import json
import re
from typing import Optional

from app import llm
from app.services import theme
from app.services.content_parser import ParsedContent

_MOODS = {"cool", "warm", "neutral"}
_INTENSITIES = {"calm", "rich"}

# Deterministic keyword affinities (lowercased substring match).
_COOL_KW = [
    "storage", "architecture", "network", "cluster", "infrastructure", "hypervisor",
    "distributed", "compute", "kernel", "protocol", "database", "system", "node",
    "virtualization", "data center", "platform", "fabric", "server", "pipeline",
]
_WARM_KW = [
    "why", "team", "benefit", "cost", "growth", "customer", "people", "business",
    "adopt", "value", "journey", "experience", "save", "simpl", "choose", "win",
]
_RICH_KW = [
    "architecture", "advanced", "deep", "internals", "distributed", "fabric",
    "security", "performance", "scale",
]

STYLE_PROMPT = """You are an art director choosing a color theme for a short explainer video.
Pick the option that best fits the SUBJECT below.

Return ONLY a JSON object (no prose, no markdown):
{{"accent": "<one of: {accents}>", "mood": "cool|warm|neutral", "bg_intensity": "calm|rich"}}

Guidance:
- cool accents (teal_indigo, blue_cyan, green_teal): technical / infrastructure / data topics.
- warm accents (coral_amber, rose_violet): people, business value, benefits, motivation.
- neutral accents (violet_teal, indigo_pink): conceptual / mixed topics.
- bg_intensity "rich" for deep/advanced/architecture topics, else "calm".

SUBJECT:
Title: {title}
Outline: {outline}
"""


async def decide_video_style(content: ParsedContent) -> theme.VideoStyle:
    """Resolve one VideoStyle for the whole video (LLM-assisted, else heuristic)."""
    if llm.llm_available():
        picked = await _llm_style(content)
        if picked is not None:
            return picked
    return _fallback_style(content)


async def _llm_style(content: ParsedContent) -> Optional[theme.VideoStyle]:
    outline = " | ".join(s.title for s in content.sections[:6]) or content.title
    prompt = STYLE_PROMPT.format(
        accents=", ".join(theme.ACCENTS.keys()),
        title=content.title,
        outline=outline[:400],
    )
    try:
        raw = await llm.chat(
            [{"role": "user", "content": prompt}],
            max_tokens=120,
            temperature=0.3,
        )
    except Exception:
        return None
    data = _extract_json(raw or "")
    if data is None:
        return None
    accent = str(data.get("accent", "")).strip().lower()
    if accent not in theme.ACCENTS:
        return None  # off-list -> fall back to the heuristic
    mood = str(data.get("mood", "")).strip().lower()
    intensity = str(data.get("bg_intensity", "")).strip().lower()
    return theme.build_style(
        accent_key=accent,
        mood=mood if mood in _MOODS else None,
        bg_intensity=intensity if intensity in _INTENSITIES else "calm",
    )


def _extract_json(text: str) -> Optional[dict]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip().rstrip("`").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        obj = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _fallback_style(content: ParsedContent) -> theme.VideoStyle:
    """Deterministic, content-aware style pick (free, reproducible)."""
    text = " ".join([content.title] + [s.title + " " + s.body for s in content.sections]).lower()
    cool = sum(text.count(k) for k in _COOL_KW)
    warm = sum(text.count(k) for k in _WARM_KW)
    rich = any(k in text for k in _RICH_KW) or len(content.sections) >= 5

    # Stable per-title tiebreak so different videos vary but a given video is fixed.
    seed = sum(ord(c) for c in content.title)

    if warm > cool:
        accent = ("coral_amber", "rose_violet")[seed % 2]
        mood = "warm"
    elif cool >= max(2, warm + 1):
        accent = ("teal_indigo", "blue_cyan", "green_teal")[seed % 3]
        mood = "cool"
    else:
        accent = ("violet_teal", "indigo_pink")[seed % 2]
        mood = "neutral"

    return theme.build_style(
        accent_key=accent,
        mood=mood,
        bg_intensity="rich" if rich else "calm",
    )
