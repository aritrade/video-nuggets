"""
Video composer that combines slide images + audio into 1080p MP4 using ffmpeg.
Also generates VTT transcripts with timestamps.

Two render paths are supported:
  - "animated" (default): Step B's word-timeline driven animation engine.
    Step A renders the static slide as backdrop; the animation renderer adds
    icon reveals, arrows, pulses, captions, etc. on top, frame-by-frame.
  - "static": legacy path that loops the slide image with ffmpeg zoompan.
    Faster but no per-frame overlays. Used as a fallback when the animation
    engine isn't available or `use_animation=False`.

Slide images come from `slide_image_generator` directly (no PPTX/LibreOffice
dependency).
"""
import subprocess
import json
import os
from pathlib import Path
from typing import Optional

from app.config import (
    VIDEOS_DIR, TRANSCRIPTS_DIR, THUMBNAILS_DIR, VIDEO_RESOLUTION,
    RENDER_W, RENDER_H, VIDEO_FPS, VIDEO_X264_PRESET, VIDEO_X264_CRF,
)
from app.services import slide_image_generator
from app.services.slide_image_generator import render_slide_images, render_slide_images_with_layouts


def compose_video(
    video_id: int,
    slides_pptx: str,
    audio_segments: list[dict],
    visualizations: list[str] = None,
    parsed_content=None,
    use_animation: bool = True,
) -> dict:
    """Compose final video from slides and audio segments.

    Slide images come from `parsed_content` via the rich PIL renderer and act
    as backdrops. When `use_animation=True` (default) the animation engine
    layers icon reveals + arrows + pulses + captions on top of those slides
    using word-level audio timing. When False, the legacy ffmpeg zoompan path
    is used.

    The `slides_pptx` arg is retained for downloadable PPTX/PDF generation
    only; video frames are not derived from it.
    """
    if parsed_content is None:
        raise ValueError("compose_video requires parsed_content for slide rendering")

    slides_dir = Path(VIDEOS_DIR) / f"slides_{video_id}"

    transcript_entries: list[dict] = []
    cumulative_time = 0.0

    if use_animation:
        try:
            from app.services.animation.renderer import render_scene
            from app.services.animation.storyboard import build_scenes
        except ImportError as e:
            print(f"[compose_video] animation engine import failed ({e}); falling back to static path")
            use_animation = False

    prev_omit = slide_image_generator.OMIT_FOCAL_ICONS
    prev_omit_body = slide_image_generator.OMIT_BODY_TEXT
    try:
        slide_image_generator.OMIT_FOCAL_ICONS = bool(use_animation)
        # Clean backdrops on generic layouts; kinetic beat captions carry the body.
        slide_image_generator.OMIT_BODY_TEXT = bool(use_animation)
        slide_images, slide_layouts, slide_diagrams = render_slide_images_with_layouts(parsed_content, video_id, slides_dir)
    finally:
        slide_image_generator.OMIT_FOCAL_ICONS = prev_omit
        slide_image_generator.OMIT_BODY_TEXT = prev_omit_body

    if not slide_images:
        raise RuntimeError("No slide images were rendered")

    segment_videos: list[str] = []

    if use_animation:
        scenes = build_scenes(
            parsed_content, audio_segments, slide_images,
            layouts=slide_layouts, diagrams=slide_diagrams,
        )
        for i, scene in enumerate(scenes):
            seg_path = str(VIDEOS_DIR / f"segment_{video_id}_{i:03d}.mp4")
            print(
                f"[compose_video] animated scene {i + 1}/{len(scenes)} "
                f"template={scene.template} duration={scene.duration:.1f}s"
            )
            try:
                render_scene(scene, seg_path, fps=VIDEO_FPS, log_progress=False)
            except Exception as e:
                print(f"[compose_video] animated render failed for segment {i}: {e}; using static fallback")
                seg = audio_segments[i]
                bg = slide_images[min(i, len(slide_images) - 1)]
                seg_path = _create_segment_video(
                    video_id, i, bg, seg["path"], scene.duration, motion_seed=i
                )
            segment_videos.append(seg_path)

            text = audio_segments[i].get("text", "")
            transcript_entries.append({
                "start": cumulative_time,
                "end": cumulative_time + scene.duration,
                "text": text,
            })
            cumulative_time += scene.duration
    else:
        for i, segment in enumerate(audio_segments):
            slide_idx = min(i, len(slide_images) - 1)
            slide_image = slide_images[slide_idx]
            audio_path = segment["path"]
            duration = _get_audio_duration(audio_path)
            seg_path = _create_segment_video(
                video_id, i, slide_image, audio_path, duration, motion_seed=i
            )
            segment_videos.append(seg_path)
            transcript_entries.append({
                "start": cumulative_time,
                "end": cumulative_time + duration,
                "text": segment["text"],
            })
            cumulative_time += duration

    final_video = _concatenate_segments(video_id, segment_videos)
    transcript_path = _generate_vtt_transcript(video_id, transcript_entries)

    thumbnail_path = str(THUMBNAILS_DIR / f"{video_id}.png")
    if slide_images:
        _generate_thumbnail(final_video, thumbnail_path)

    for sv in segment_videos:
        try:
            os.remove(sv)
        except OSError:
            pass

    return {
        "video_path": final_video,
        "transcript_path": transcript_path,
        "thumbnail_path": thumbnail_path,
        "duration_seconds": cumulative_time,
    }


def _get_audio_duration(audio_path: str) -> float:
    """Get duration of audio file in seconds using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", audio_path,
            ],
            capture_output=True, text=True, timeout=10,
        )
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except Exception:
        return 10.0


def _create_segment_video(
    video_id: int,
    index: int,
    slide_image: str,
    audio_path: str,
    duration: float,
    motion_seed: int = 0,
) -> str:
    """Create a video segment from a single slide image + audio with Ken Burns motion.

    The image is upscaled, then a slow zoom + slight pan is applied so static
    slides feel alive. Different segments use slightly different motion to
    keep the experience varied.
    """
    output_path = str(VIDEOS_DIR / f"segment_{video_id}_{index:03d}.mp4")

    fps = VIDEO_FPS
    total_frames = max(int(duration * fps), 1)
    target_w, target_h = RENDER_W, RENDER_H

    motions = [
        {"zoom_start": 1.00, "zoom_end": 1.06, "x": "iw/2-(iw/zoom/2)", "y": "ih/2-(ih/zoom/2)"},
        {"zoom_start": 1.06, "zoom_end": 1.00, "x": "iw/2-(iw/zoom/2)", "y": "ih/2-(ih/zoom/2)"},
        {"zoom_start": 1.00, "zoom_end": 1.05, "x": "(iw-iw/zoom)/2 + (iw-iw/zoom)*0.15*on/{tf}", "y": "ih/2-(ih/zoom/2)"},
        {"zoom_start": 1.00, "zoom_end": 1.05, "x": "(iw-iw/zoom)/2 - (iw-iw/zoom)*0.15*on/{tf}", "y": "ih/2-(ih/zoom/2)"},
        {"zoom_start": 1.00, "zoom_end": 1.04, "x": "iw/2-(iw/zoom/2)", "y": "(ih-ih/zoom)/2 + (ih-ih/zoom)*0.10*on/{tf}"},
    ]
    motion = motions[motion_seed % len(motions)]
    zs = motion["zoom_start"]
    ze = motion["zoom_end"]
    zoom_expr = f"{zs}+({ze}-{zs})*on/{total_frames}"
    x_expr = motion["x"].format(tf=total_frames)
    y_expr = motion["y"].format(tf=total_frames)

    sw = target_w * 2
    sh = target_h * 2
    vf = (
        f"scale={sw}:{sh}:flags=lanczos,"
        f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':"
        f"d={total_frames}:s={target_w}x{target_h}:fps={fps}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-framerate", str(fps), "-i", slide_image,
        "-i", audio_path,
        "-c:v", "libx264", "-preset", VIDEO_X264_PRESET, "-crf", VIDEO_X264_CRF,
        "-c:a", "aac", "-b:a", "192k",
        "-vf", vf,
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        "-shortest",
        "-t", str(duration),
        output_path,
    ]

    subprocess.run(cmd, capture_output=True, timeout=120)
    return output_path


def _concatenate_segments(video_id: int, segment_paths: list[str]) -> str:
    """Concatenate all segment videos into final output."""
    final_path = str(VIDEOS_DIR / f"{video_id}.mp4")
    concat_file = str(VIDEOS_DIR / f"concat_{video_id}.txt")

    with open(concat_file, "w") as f:
        for path in segment_paths:
            f.write(f"file '{path}'\n")

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_file,
        "-c", "copy",
        final_path,
    ]

    subprocess.run(cmd, capture_output=True, timeout=300)

    try:
        os.remove(concat_file)
    except OSError:
        pass

    return final_path


def _generate_vtt_transcript(video_id: int, entries: list[dict]) -> str:
    """Generate a WebVTT transcript file."""
    transcript_path = str(TRANSCRIPTS_DIR / f"{video_id}.vtt")

    with open(transcript_path, "w") as f:
        f.write("WEBVTT\n\n")
        for i, entry in enumerate(entries):
            start = _format_vtt_time(entry["start"])
            end = _format_vtt_time(entry["end"])
            f.write(f"{i + 1}\n")
            f.write(f"{start} --> {end}\n")
            f.write(f"{entry['text']}\n\n")

    return transcript_path


def _format_vtt_time(seconds: float) -> str:
    """Format seconds to VTT timestamp (HH:MM:SS.mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def _generate_thumbnail(video_path: str, output_path: str):
    """Extract first frame as thumbnail."""
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vframes", "1", "-q:v", "2",
        output_path,
    ]
    subprocess.run(cmd, capture_output=True, timeout=10)
