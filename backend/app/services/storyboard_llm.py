"""
LLM-authored visual storyboard.

Given the already-simplified narration for each section, ask the LLM (Groq
Llama-3 by default) to author a compact *visual script* describing how the
scene should animate: a scene type, a short on-screen headline, 2-4 on-screen
"beats" anchored to specific narration words, and - for diagram scenes - a
small boxes-and-arrows graph the animation engine builds step-by-step.

This is the engagement moat: instead of one static slide with a canned caption,
every section becomes a narration-synced explainer. The LLM call is free (Groq),
and a deterministic fallback keeps the pipeline working at zero cost when no key
is configured or the model returns junk.

Visual script shape (after validation):
    {
      "scene_type": "diagram" | "numbered" | "comparison" | "analogy"
                    | "key_points" | "default",
      "headline": "Short on-screen title",
      "beats": [{"anchor": "word", "text": "<= 7-word line"}, ...],
      "diagram": {                       # only when scene_type == "diagram"
        "nodes": [{"id": "a", "label": "User Apps", "col": 0, "row": 0,
                   "icon": "user_vms"}],
        "edges": [{"from": "a", "to": "b", "label": "reads"}]
      }
    }
"""
from __future__ import annotations

import json
import re
from typing import Optional

from app import llm
from app.services import icon_library
from app.services.content_parser import ContentSection, ParsedContent

SCENE_TYPES = {"diagram", "numbered", "comparison", "analogy", "key_points", "default"}

MAX_BEATS = 4
MAX_NODES = 6
MAX_EDGES = 8
MAX_BEAT_CHARS = 46
MAX_LABEL_CHARS = 22
MAX_HEADLINE_CHARS = 42

STORYBOARD_PROMPT = """You are an explainer-video art director. You are given the spoken NARRATION \
for one scene of a short educational video. Design how this scene should animate on screen \
so it is visually engaging and the visuals build while the narration is spoken.

Return ONLY a single JSON object (no prose, no markdown fences) with this exact schema:

{{
  "scene_type": one of "diagram", "numbered", "comparison", "analogy", "key_points", "default",
  "headline": "a punchy on-screen title, 3 to 6 words",
  "beats": [
    {{"anchor": "a single distinctive word that appears in the narration", "text": "a short on-screen label, max 7 words"}}
  ],
  "diagram": {{
    "nodes": [{{"id": "a", "label": "short label", "col": 0, "row": 0, "icon": "optional one-word icon hint"}}],
    "edges": [{{"from": "a", "to": "b", "label": "optional short verb"}}]
  }}
}}

Rules:
- Choose "diagram" when the narration describes components, a system, a flow, or how parts connect. Prefer "diagram" whenever it fits - moving diagrams are the goal.
- Use "comparison" for old-vs-new / X-vs-Y, "numbered" for ordered steps/rules, "analogy" for an "imagine..."-style metaphor, "key_points" for a list of benefits/takeaways, "default" otherwise.
- 2 to 4 beats. Each "anchor" MUST be a word that literally appears in the narration so it can be timed to the voice.
- For diagrams: 2 to 6 nodes laid out on a grid using col (0-3) and row (0-2). Connect them with edges that show the relationship/flow. Keep labels to 1-3 words.
- "diagram" key is REQUIRED only when scene_type is "diagram"; otherwise set it to null.
- Keep everything concise. Output must be valid JSON.

TITLE: {title}

NARRATION:
{narration}
"""


async def generate_visual_scripts(content: ParsedContent) -> ParsedContent:
    """Populate `section.visual_script` for every section.

    Mutates the sections in place and returns the same ParsedContent. Always
    succeeds: any section the LLM can't (or won't) script gets a deterministic
    fallback script derived from its text.
    """
    for index, section in enumerate(content.sections):
        # Respect a pre-authored storyboard (e.g. pinned demo scenes or tests).
        if getattr(section, "visual_script", None):
            continue
        script: Optional[dict] = None
        if llm.llm_available():
            script = await _llm_script(section)
        if not script:
            script = _fallback_script(section, index, len(content.sections))
        section.visual_script = script
    return content


async def _llm_script(section: ContentSection) -> Optional[dict]:
    narration = section.body.strip()
    if not narration:
        return None
    prompt = STORYBOARD_PROMPT.format(title=section.title, narration=narration[:1800])
    raw = await llm.chat(
        [{"role": "user", "content": prompt}],
        max_tokens=600,
        temperature=0.4,
    )
    if not raw:
        return None
    data = _extract_json(raw)
    if data is None:
        return None
    return _validate_script(data, section)


def _extract_json(text: str) -> Optional[dict]:
    """Pull the first balanced JSON object out of an LLM response."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip().rstrip("`").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    snippet = text[start:end + 1]
    try:
        obj = json.loads(snippet)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _clip(text: object, max_chars: int) -> str:
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(s) > max_chars:
        s = s[:max_chars - 1].rstrip() + "\u2026"
    return s


def _validate_script(data: dict, section: ContentSection) -> Optional[dict]:
    scene_type = str(data.get("scene_type", "")).strip().lower()
    if scene_type not in SCENE_TYPES:
        scene_type = "default"

    headline = _clip(data.get("headline") or section.title, MAX_HEADLINE_CHARS)

    narration_l = section.body.lower()
    beats: list[dict] = []
    for b in (data.get("beats") or [])[:MAX_BEATS]:
        if not isinstance(b, dict):
            continue
        text = _clip(b.get("text"), MAX_BEAT_CHARS)
        if not text:
            continue
        anchor = re.sub(r"[^a-z0-9]", "", str(b.get("anchor", "")).lower())
        # Only keep anchors that actually occur in the narration; else leave
        # empty so the template falls back to even spacing.
        if anchor and anchor not in re.sub(r"[^a-z0-9 ]", "", narration_l):
            anchor = ""
        beats.append({"anchor": anchor, "text": text})

    script: dict = {"scene_type": scene_type, "headline": headline, "beats": beats}

    if scene_type == "diagram":
        diagram = _validate_diagram(data.get("diagram"))
        if not diagram:
            # No usable graph -> downgrade so we don't render an empty canvas.
            script["scene_type"] = "key_points" if beats else "default"
        else:
            script["diagram"] = diagram

    return script


def _validate_diagram(raw: object) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    nodes_in = raw.get("nodes")
    if not isinstance(nodes_in, list) or not nodes_in:
        return None

    nodes: list[dict] = []
    seen_ids: set[str] = set()
    for n in nodes_in[:MAX_NODES]:
        if not isinstance(n, dict):
            continue
        nid = re.sub(r"[^a-z0-9_]", "", str(n.get("id", "")).lower())[:16]
        label = _clip(n.get("label"), MAX_LABEL_CHARS)
        if not nid or not label or nid in seen_ids:
            continue
        seen_ids.add(nid)
        col = _clamp_int(n.get("col"), 0, 3)
        row = _clamp_int(n.get("row"), 0, 2)
        icon = _resolve_icon(n.get("icon"))
        nodes.append({"id": nid, "label": label, "col": col, "row": row, "icon": icon})

    if len(nodes) < 2:
        return None

    edges: list[dict] = []
    for e in (raw.get("edges") or [])[:MAX_EDGES]:
        if not isinstance(e, dict):
            continue
        src = re.sub(r"[^a-z0-9_]", "", str(e.get("from", "")).lower())[:16]
        dst = re.sub(r"[^a-z0-9_]", "", str(e.get("to", "")).lower())[:16]
        if src in seen_ids and dst in seen_ids and src != dst:
            edges.append({"from": src, "to": dst, "label": _clip(e.get("label"), 16)})

    return {"nodes": nodes, "edges": edges}


def _clamp_int(value: object, low: int, high: int) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return low
    return max(low, min(high, v))


def _resolve_icon(hint: object) -> Optional[str]:
    """Map an LLM icon hint onto a real concept in the icon library, or None."""
    if not hint:
        return None
    concept = icon_library._resolve_concept(str(hint).strip().lower().replace(" ", "_"))
    return concept


# ---------------- Deterministic fallback ----------------

def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.replace("\n", " ")) if s.strip()]


def _fallback_script(section: ContentSection, index: int, total: int) -> dict:
    """Heuristic visual script when no LLM is available (zero-cost path).

    Scene type reuses the existing slide layout detector so the visual rhythm
    matches what the static slide draws. Beats are short clauses pulled from the
    narration; anchors are the most distinctive word in each clause.
    """
    from app.services.slide_image_generator import _detect_layout

    scene_type = _detect_layout(section, index, total)
    if scene_type not in SCENE_TYPES:
        scene_type = "default"
    # The fallback can't reliably invent a graph, so never claim "diagram".
    if scene_type == "diagram":
        scene_type = "key_points"

    sentences = _split_sentences(section.body)
    beats: list[dict] = []
    for sent in sentences[:MAX_BEATS]:
        words = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", sent)]
        anchor = ""
        if words:
            # Prefer the longest word as the most distinctive anchor.
            anchor = re.sub(r"[^a-z0-9]", "", max(words, key=len).lower())
        # Clean short label: first ~7 words, no mid-word truncation.
        label = " ".join(sent.split()[:7]).rstrip(",.;:")
        beats.append({"anchor": anchor, "text": _clip(label, MAX_BEAT_CHARS)})

    return {
        "scene_type": scene_type,
        "headline": _clip(section.title, MAX_HEADLINE_CHARS),
        "beats": beats,
    }
