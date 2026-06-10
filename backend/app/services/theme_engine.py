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

# Emotion/intent lexicon -> psychological intent. Each intent maps to a curated
# accent via theme.INTENT_TO_ACCENT, so classifying the dominant feeling of the
# content is enough to pick an on-brand, psychology-backed look.
_INTENT_KW: dict[str, list[str]] = {
    "trust": [
        "reliab", "secure", "security", "stable", "stability", "trust", "proven",
        "consistent", "resilien", "protect", "safe", "dependable", "compliance",
    ],
    "growth": [
        "scale", "scaling", "grow", "growth", "efficien", "optimi", "improve",
        "faster", "boost", "save", "savings", "roi", "productiv", "benefit",
    ],
    "focus": [
        "architecture", "internals", "deep", "advanced", "how it works", "kernel",
        "protocol", "distributed", "mechanism", "pipeline", "low-level", "detail",
    ],
    "innovation": [
        "new", "future", "next-gen", "innovat", "modern", "transform", "reinvent",
        "ai", "intelligen", "automate", "cutting-edge", "breakthrough",
    ],
    "creative": [
        "design", "idea", "concept", "imagine", "creative", "story", "analogy",
        "metaphor", "explore", "possibilit",
    ],
    "energy": [
        "fast", "speed", "instant", "power", "accelerat", "real-time", "action",
        "launch", "drive", "momentum", "win", "high-performance",
    ],
    "bold": [
        "why", "matter", "challenge", "problem", "pain", "struggle", "critical",
        "must", "urgent", "revolution", "game-chang", "disrupt",
    ],
}

# Deterministic keyword affinities (lowercased substring match).
_RICH_KW = [
    "architecture", "advanced", "deep", "internals", "distributed", "fabric",
    "security", "performance", "scale",
]

STYLE_PROMPT = """You are an art director choosing a color theme for a short explainer video.
Use COLOR PSYCHOLOGY: pick the emotional intent that best fits the SUBJECT, then a fitting look.

Return ONLY a JSON object (no prose, no markdown):
{{"intent": "<one of: {intents}>", "bg_intensity": "calm|rich"}}

Intent guidance (color psychology):
- trust  -> dependable, secure, stable systems / infrastructure (cool blue-cyan).
- growth -> efficiency, scaling, savings, positive outcomes (green-teal).
- focus  -> deep technical architecture / internals (indigo-teal).
- innovation -> new, modern, AI, transformation (violet).
- creative -> conceptual, design, analogies, ideas (indigo-pink).
- energy -> speed, performance, action, momentum (warm coral-amber).
- bold   -> persuasion, "why it matters", problems, urgency (rose-violet).
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
        intents=", ".join(theme.INTENT_TO_ACCENT.keys()),
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
    intent = str(data.get("intent", "")).strip().lower()
    accent = theme.INTENT_TO_ACCENT.get(intent)
    if accent is None:
        # Back-compat: also accept a raw accent key if the model returned one.
        cand = str(data.get("accent", "")).strip().lower()
        accent = cand if cand in theme.ACCENTS else None
    if accent is None:
        return None  # off-list -> fall back to the heuristic
    intensity = str(data.get("bg_intensity", "")).strip().lower()
    return theme.build_style(
        accent_key=accent,
        bg_intensity=intensity if intensity in _INTENSITIES else "calm",
    )


def classify_intent(content: ParsedContent) -> str:
    """Deterministic dominant-emotion classification from an intent lexicon."""
    text = " ".join([content.title] + [s.title + " " + s.body for s in content.sections]).lower()
    scores = {intent: sum(text.count(k) for k in kws) for intent, kws in _INTENT_KW.items()}
    best_intent, best_score = max(scores.items(), key=lambda kv: kv[1])
    if best_score == 0:
        return "focus"  # neutral, premium default for technical explainers
    return best_intent


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
    """Deterministic, content-aware style pick (free, reproducible).

    Maps the content's dominant emotional intent (color psychology) straight to a
    curated accent, falling back to keyword mood signals only when no intent fires.
    """
    text = " ".join([content.title] + [s.title + " " + s.body for s in content.sections]).lower()
    rich = any(k in text for k in _RICH_KW) or len(content.sections) >= 5

    intent = classify_intent(content)
    accent = theme.INTENT_TO_ACCENT.get(intent, theme.DEFAULT_ACCENT)

    return theme.build_style(
        accent_key=accent,
        bg_intensity="rich" if rich else "calm",
    )
