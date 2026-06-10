"""
Full video generation pipeline orchestrator.
Coordinates: parse -> simplify -> visualize -> slides -> TTS -> compose
"""
import asyncio
import traceback
from sqlalchemy.orm import Session

from app.models.database import SessionLocal, Video, VideoStatus
from app.services.content_parser import parse_source
from app.services.content_simplifier import simplify_content
from app.services.storyboard_llm import generate_visual_scripts
from app.services.visualization_gen import (
    generate_comparison_chart,
    generate_architecture_diagram,
    generate_flow_diagram,
    generate_key_points_visual,
)
from app.services.slide_generator import generate_slides
from app.services.tts_service import generate_narration
from app.services.video_composer import compose_video


def run_video_pipeline(video_id: int, source_path: str):
    """Run the full video generation pipeline synchronously (called from background task)."""
    asyncio.run(_async_pipeline(video_id, source_path))


def run_direct_pipeline(video_id: int, parsed):
    """
    Run the video generation pipeline using pre-authored content (no LLM simplification).
    Useful for batch scripts that have already produced 6-year-old-friendly narration.
    """
    asyncio.run(_async_direct_pipeline(video_id, parsed))


async def _async_direct_pipeline(video_id: int, parsed):
    """Async direct pipeline: skip Ollama simplification step."""
    db = SessionLocal()
    try:
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            print(f"[DirectPipeline] Video {video_id} not found")
            return

        video.status = VideoStatus.PROCESSING
        db.commit()

        if (not video.title or video.title == "Untitled") and parsed.title:
            video.title = parsed.title
            db.commit()

        # Pre-authored narration still gets an animated storyboard.
        await generate_visual_scripts(parsed)

        visualizations = _generate_visualizations(parsed)
        slides_path = generate_slides(parsed, video_id, visualizations)
        video.slides_path = slides_path
        db.commit()

        audio_segments = await generate_narration(parsed, video_id)

        result = compose_video(
            video_id,
            slides_path,
            audio_segments,
            visualizations,
            parsed_content=parsed,
        )

        video.video_path = result["video_path"]
        video.transcript_path = result["transcript_path"]
        video.thumbnail_path = result["thumbnail_path"]
        video.duration_seconds = result["duration_seconds"]
        video.status = VideoStatus.READY
        db.commit()

        try:
            from app.chatbot.embedder import index_video_content
            await index_video_content(video_id, parsed, audio_segments)
        except Exception as idx_err:
            print(f"[DirectPipeline] RAG indexing skipped for {video_id}: {idx_err}")

        print(f"[DirectPipeline] Video {video_id} ready: {result['video_path']}")

    except Exception as e:
        print(f"[DirectPipeline] Failed for video {video_id}: {e}")
        traceback.print_exc()
        video = db.query(Video).filter(Video.id == video_id).first()
        if video:
            video.status = VideoStatus.FAILED
            db.commit()
    finally:
        db.close()


async def _async_pipeline(video_id: int, source_path: str):
    """Async video generation pipeline."""
    db = SessionLocal()
    try:
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            return

        video.status = VideoStatus.PROCESSING
        db.commit()

        parsed = parse_source(source_path)

        if video.title == "Untitled" or not video.title:
            video.title = parsed.title
            db.commit()

        simplified = await simplify_content(parsed)

        # Author the per-section visual storyboard (scene type + beats + diagram)
        # used by the animation engine. Always succeeds (deterministic fallback).
        await generate_visual_scripts(simplified)

        visualizations = _generate_visualizations(simplified)

        slides_path = generate_slides(simplified, video_id, visualizations)
        video.slides_path = slides_path
        db.commit()

        audio_segments = await generate_narration(simplified, video_id)

        result = compose_video(
            video_id,
            slides_path,
            audio_segments,
            visualizations,
            parsed_content=simplified,
        )

        video.video_path = result["video_path"]
        video.transcript_path = result["transcript_path"]
        video.thumbnail_path = result["thumbnail_path"]
        video.duration_seconds = result["duration_seconds"]
        video.status = VideoStatus.READY
        db.commit()

        from app.chatbot.embedder import index_video_content
        await index_video_content(video_id, simplified, audio_segments)

    except Exception as e:
        print(f"[Pipeline] Failed for video {video_id}: {e}")
        traceback.print_exc()
        video = db.query(Video).filter(Video.id == video_id).first()
        if video:
            video.status = VideoStatus.FAILED
            db.commit()
    finally:
        db.close()


def _generate_visualizations(content) -> list[str]:
    """Generate appropriate visualizations based on content analysis."""
    visualizations = []

    for i, section in enumerate(content.sections):
        body = section.body.lower()

        if any(kw in body for kw in ["vs", "versus", "compared to", "traditional", "legacy"]):
            viz = generate_comparison_chart(
                title=section.title,
                categories=["Complexity", "Scale", "Management", "Cost"],
                values_a=[8, 4, 9, 8],
                values_b=[3, 9, 2, 4],
                label_a="Traditional",
                label_b="Hyperconverged",
            )
            visualizations.append(viz)
        elif any(kw in body for kw in ["layer", "stack", "architecture", "platform"]):
            viz = generate_architecture_diagram(
                title=section.title,
                layers=[
                    {"name": "Applications", "components": ["VMs", "Containers", "Databases"]},
                    {"name": "Platform Services", "components": ["Files", "Objects", "Volumes"]},
                    {"name": "Core Platform", "components": ["Storage", "Compute", "Network"]},
                    {"name": "Infrastructure", "components": ["Hardware", "Hypervisor"]},
                ],
            )
            visualizations.append(viz)
        elif any(kw in body for kw in ["step", "process", "flow", "first", "then", "finally"]):
            steps = _extract_steps(section.body)
            if len(steps) >= 3:
                viz = generate_flow_diagram(title=section.title, steps=steps[:6])
                visualizations.append(viz)
        elif any(kw in body for kw in ["key", "point", "benefit", "advantage", "feature"]):
            points = _extract_key_points(section.body)
            if points:
                viz = generate_key_points_visual(title=section.title, points=points)
                visualizations.append(viz)

        if len(visualizations) >= len(content.sections) * 0.6:
            break

    return visualizations


def _extract_steps(text: str) -> list[str]:
    """Extract process steps from text."""
    import re
    lines = text.split("\n")
    steps = []
    for line in lines:
        line = line.strip()
        if re.match(r"^\d+[.)]\s*", line):
            step = re.sub(r"^\d+[.)]\s*", "", line)
            steps.append(step[:40])
        elif line.startswith(("- ", "• ")):
            steps.append(line[2:40])
    if not steps:
        sentences = text.split(".")
        steps = [s.strip()[:40] for s in sentences[:5] if s.strip()]
    return steps


def _extract_key_points(text: str) -> list[dict]:
    """Extract key points from text."""
    lines = text.split("\n")
    points = []
    for line in lines:
        line = line.strip()
        if line and (line.startswith(("- ", "• ", "* ")) or len(line) < 80):
            clean = line.lstrip("-•* ").strip()
            if clean:
                points.append({"icon": str(len(points) + 1), "title": clean[:50]})
        if len(points) >= 4:
            break
    return points
