"""
Storyboard generator: turn a ParsedContent + audio segments + word timelines
into a list of fully-built Scene objects ready for the renderer.

For each audio segment we:
  1. Take the static slide PNG produced by Step A as the background.
  2. Pick an animation template that matches the slide layout produced by
     `slide_image_generator._detect_layout` (so reveal positions line up).
  3. Read the cached word timeline JSON to anchor cues to specific words.
  4. Compute the segment duration from the audio file via ffprobe.
  5. Call `templates.build(template_name, ctx)` for the Scene.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from app.services.animation.templates import TemplateContext, build as build_template
from app.services.animation.types import Scene
from app.services.content_parser import ParsedContent, ContentSection


NODE_ANATOMY_TITLE_KEYWORDS = [
    "node anatomy", "anatomy of a node", "inside a node",
    "what's inside a node", "what is in a node", "controller vm anatomy",
    "anatomy", "what's inside",
]


def _override_template_for_section(section: ContentSection, layout: str) -> str:
    """Possibly override a generic slide layout with a more specific animation
    template when the section is *clearly* about node anatomy.

    We require the override trigger to live in the title (or be an explicit
    phrase in the first sentence) so an offhand mention of CVM doesn't drag
    every section into node_anatomy.
    """
    title_l = section.title.lower()
    if any(kw in title_l for kw in NODE_ANATOMY_TITLE_KEYWORDS):
        return "node_anatomy"
    first_sentence = section.body.lower().split(".", 1)[0]
    if "anatomy of" in first_sentence or "let's open up" in first_sentence:
        return "node_anatomy"
    return layout


def _ffprobe_duration(path: str) -> float:
    if shutil.which("ffprobe") is None:
        return 0.0
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path,
        ], text=True).strip()
        return float(out)
    except Exception:
        return 0.0


def _load_timeline(path: Optional[str]) -> list[dict]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text())
    except Exception:
        return []
    return data.get("words", [])


def _extract_numbered_points(body: str, max_points: int = 4) -> list[str]:
    pattern = re.compile(
        r"\b(?:first|second|third|fourth|finally|next)[\s,:]+([^.!?]+[.!?])",
        re.IGNORECASE,
    )
    matches = pattern.findall(body)
    if len(matches) >= 2:
        return [m.strip() for m in matches[:max_points]]
    pattern2 = re.compile(r"\b\d\.\s+([^.!?]+[.!?])")
    matches = pattern2.findall(body)
    if len(matches) >= 2:
        return [m.strip() for m in matches[:max_points]]
    sents = re.split(r"(?<=[.!?])\s+", body.strip())
    sents = [s.strip() for s in sents if s.strip()]
    return sents[:max_points]


def build_scenes(
    content: ParsedContent,
    audio_segments: list[dict],
    slide_paths: list[str],
    layouts: Optional[list[str]] = None,
    diagrams: Optional[list[Optional[dict]]] = None,
) -> list[Scene]:
    """Build one Scene per audio segment.

    `layouts` is a parallel list of layout names (e.g. "hero", "analogy",
    "default", "bible_diagram", "outro") - when provided, each animation
    template is chosen to match its slide layout.

    `diagrams` is a parallel list of Cloud Bible diagram manifests (or None)
    so the bible_diagram animation template can reveal the matched figure.
    """
    scenes: list[Scene] = []
    sections = content.sections

    for i, seg in enumerate(audio_segments):
        audio_path = seg["path"]
        bg_path = slide_paths[i] if i < len(slide_paths) else slide_paths[-1]
        timeline = _load_timeline(seg.get("timeline_path"))
        duration = _ffprobe_duration(audio_path)
        seg_layout = layouts[i] if layouts and i < len(layouts) else None
        seg_diagram = diagrams[i] if diagrams and i < len(diagrams) else None

        seg_type = seg.get("type")

        if seg_type == "intro":
            ctx = TemplateContext(
                title=content.title, body=seg.get("text", ""),
                duration=duration or 6.0,
                audio_path=audio_path, background_image=bg_path,
                section_index=-1, motion_seed=0,
                word_timeline=timeline, layout="hero",
            )
            scenes.append(build_template("hero", ctx))
            continue

        if seg_type == "outro":
            ctx = TemplateContext(
                title=content.title, body=seg.get("text", ""),
                duration=duration or 6.0,
                audio_path=audio_path, background_image=bg_path,
                section_index=-2, motion_seed=4,
                word_timeline=timeline, layout="outro",
            )
            scenes.append(build_template("outro", ctx))
            continue

        idx = seg.get("section_index", i - 1)
        section = sections[idx] if 0 <= idx < len(sections) else None
        if section is None:
            continue

        layout = seg_layout or "default"
        template_name = _override_template_for_section(section, layout)

        vs = getattr(section, "visual_script", None) or {}

        extra: dict = {
            "beats": vs.get("beats") or [],
            "headline": vs.get("headline") or "",
        }
        if template_name in ("numbered_reveal", "numbered"):
            extra["points"] = _extract_numbered_points(section.body, max_points=4)

        if layout == "bible_diagram" and seg_diagram is not None:
            # A real Cloud Bible figure (factual) always wins over a synthesized graph.
            extra["diagram"] = seg_diagram
            template_name = "bible_diagram"
        elif (
            vs.get("scene_type") == "diagram"
            and vs.get("diagram")
            and layout in ("default", "analogy")
        ):
            # LLM authored a boxes-and-arrows graph and the backdrop is generic:
            # build an animated diagram instead of a static-ish focal-icon scene.
            extra["diagram"] = vs["diagram"]
            template_name = "diagram"

        ctx = TemplateContext(
            title=section.title, body=section.body,
            duration=duration or 30.0,
            audio_path=audio_path, background_image=bg_path,
            section_index=idx, motion_seed=(idx + 1) % 5,
            word_timeline=timeline, layout=layout,
            slide_num=idx + 1, total_slides=len(sections),
            extra=extra,
        )
        scenes.append(build_template(template_name, ctx))

    return scenes
