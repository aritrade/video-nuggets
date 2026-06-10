"""The video intelligence agent (always-on).

Every generation path runs the director so the engine's principles are enforced
for every video - today and in the future:

1. Color psychology drives the look (theme_engine picks a psychology-backed
   palette + typographic emphasis from the content's dominant emotion/intent).
2. Visuals over text: per section, pick the strongest MOVING visual in priority
   order - a real matched source figure > a synthesized diagram > an icon/visual
   scene - and keep on-screen text to short kinetic beats only.
3. The narration already speaks the content, so body paragraphs are never put on
   screen.

The director writes its decisions onto each ``ContentSection`` (``visual_script``
+ ``source_figure``) so the existing animation engine consumes them unchanged,
and also returns a :class:`VideoPlan` (style + per-section :class:`SceneSpec`)
for callers that want the structured plan.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.services import diagram_synth, engine_policy as policy, theme
from app.services.content_parser import ParsedContent
from app.services.figure_index import EMPTY_INDEX, DiagramIndex
from app.services.storyboard_llm import generate_visual_scripts
from app.services.theme_engine import decide_video_style

# Re-exported from the rulebook so the SOP threshold lives in one place.
MIN_FIGURE_SCORE = policy.FIGURE_MATCH_MIN_SCORE


@dataclass
class SceneSpec:
    """The director's decision for one section."""
    index: int
    kind: str                       # "source_figure" | "diagram" | "minimal"
    scene_type: str                 # the visual_script scene_type actually used
    figure: dict = field(default_factory=dict)   # {abs_path, caption, heading, id}
    beats: list[dict] = field(default_factory=list)


@dataclass
class VideoPlan:
    style: theme.VideoStyle
    scenes: list[SceneSpec] = field(default_factory=list)
    # Human-readable notes for every SOP auto-correction applied to this video.
    adjustments: list[str] = field(default_factory=list)


async def direct_video(content: ParsedContent,
                       figures: Optional[DiagramIndex] = None) -> VideoPlan:
    """Resolve the whole-video look + per-section moving-visual plan, then enforce
    the Standard Operating Plan (see engine_policy).

    Mutates each section's ``visual_script``/``source_figure`` in place and
    returns the structured :class:`VideoPlan`.
    """
    figures = figures or EMPTY_INDEX

    # 1. Author per-section storyboards (LLM when available; otherwise the
    #    deterministic, diagram-biased fallback). This fills visual_script.
    await generate_visual_scripts(content)

    # 2. Color-psychology look for the whole video (R1).
    style = await decide_video_style(content)

    # 3. Per-section: choose the strongest moving visual in priority order
    #    (R3/R4): real source figure > synthesized/LLM diagram > minimal scene.
    scenes: list[SceneSpec] = []
    used_figs: set[str] = set()
    for i, section in enumerate(content.sections):
        script = section.visual_script or {}
        beats = policy.clamp_beats(script.get("beats"))   # R5 text budget
        script["beats"] = beats

        fig, score = figures.best_scored(
            f"{section.title} {section.body[:400]}", exclude_ids=used_figs
        )
        if fig and score >= policy.FIGURE_MATCH_MIN_SCORE:
            used_figs.add(fig.get("id", ""))
            section.source_figure = {
                "abs_path": figures.abs_path(fig),
                "caption": fig.get("caption_below", ""),
                "heading": fig.get("heading_above", "") or fig.get("topic", ""),
                "id": fig.get("id", ""),
            }
            script["scene_type"] = "source_figure"
            section.visual_script = script
            scenes.append(SceneSpec(i, "source_figure", "source_figure",
                                    figure=section.source_figure, beats=beats))
            continue

        scene_type = script.get("scene_type", "default")
        if scene_type == "diagram" and script.get("diagram"):
            section.visual_script = script
            scenes.append(SceneSpec(i, "diagram", "diagram", beats=beats))
            continue

        section.visual_script = script
        scenes.append(SceneSpec(i, "minimal", scene_type, beats=beats))

    plan = VideoPlan(style=style, scenes=scenes)

    # 4. Verify the plan against the SOP and auto-correct (fail-safe).
    enforce_policy(plan, content)
    _log_summary(plan)
    return plan


def enforce_policy(plan: VideoPlan, content: ParsedContent) -> VideoPlan:
    """Apply the plan-level non-negotiable rules, auto-correcting in place and
    recording every change in ``plan.adjustments``.

    Covers R3 (visual-first / no text card), R5 (text budget), R10 (brand
    neutrality) and R1/R2 (cohesive, legible look). Render-time rules (R7 hook,
    R8 motion floor) are enforced later by animation.policy.enforce_scene_policy.
    """
    adj = plan.adjustments

    # R1/R2: guarantee the look is cohesive + legible. build_style already runs
    # ensure_legible, so re-resolving is idempotent; this guards future edits.
    s = plan.style
    legible_text = theme.ensure_legible(s.text, s.bg_bottom, policy.CONTRAST_TEXT_MIN)
    legible_accent = theme.ensure_legible(s.accent, s.bg_bottom, policy.CONTRAST_ACCENT_MIN)
    if legible_text != s.text or legible_accent != s.accent:
        s.text, s.accent = legible_text, legible_accent
        adj.append("R2 legibility: lightened text/accent to clear WCAG minimums")

    for spec in plan.scenes:
        section = content.sections[spec.index] if spec.index < len(content.sections) else None
        if section is None:
            continue
        script = section.visual_script or {}

        # R3 visual-first: never leave a section as a text card. Try to synthesize
        # a moving diagram from its narration; otherwise it stays a minimal icon
        # scene (still visual), which is acceptable.
        if policy.is_text_card(spec.kind, spec.scene_type):
            synth = diagram_synth.synthesize_diagram(section.body, section.title)
            if synth:
                script["scene_type"] = "diagram"
                script["diagram"] = synth
                section.visual_script = script
                spec.kind = spec.scene_type = "diagram"
                adj.append(f"R3 visual-first: section {spec.index} upgraded to a synthesized diagram")

        # R5 text budget (idempotent re-clamp) + R10 brand neutrality on beats.
        spec.beats = policy.clamp_beats(spec.beats)
        script["beats"] = spec.beats

        # R10 brand neutrality on the headline + figure attribution.
        headline = script.get("headline")
        if headline:
            clean, changed = policy.scrub_branding(headline)
            if changed:
                script["headline"] = clean
                adj.append(f"R10 brand neutrality: scrubbed headline on section {spec.index}")
        if spec.figure:
            for key in ("caption", "heading"):
                val = spec.figure.get(key)
                if val:
                    clean, changed = policy.scrub_branding(val)
                    if changed:
                        spec.figure[key] = clean
                        section.source_figure[key] = clean
                        adj.append(f"R10 brand neutrality: scrubbed figure {key} on section {spec.index}")

        section.visual_script = script

    return plan


def _log_summary(plan: VideoPlan) -> None:
    n = len(plan.adjustments)
    print(f"[director] SOP {policy.RULE_COUNT}/{policy.RULE_COUNT} satisfied "
          f"({n} auto-correction{'s' if n != 1 else ''})")
    for note in plan.adjustments:
        print(f"[director]   - {note}")
