"""
Frame compositor + ffmpeg pipe for the animation engine.

For each Scene we:
  1. Load the static background slide PNG once (Step A's brand-styled slide).
  2. Apply Ken Burns motion to the background (slow zoom) so the canvas always
     feels alive even when no cues are firing.
  3. Walk every active cue at every frame and alpha-composite its overlay.
  4. Pipe raw rgb24 frames to ffmpeg, which muxes the scene audio and emits a
     single MP4 segment.

Performance notes:
- Frames where no cue is "animating" (every active cue has progress 1.0 and
  isn't time-cyclic like pulse_ring) are detected and reused frame-to-frame so
  we save expensive PIL composites.
- Ken Burns is implemented in PIL (not ffmpeg's zoompan) so it composes nicely
  with overlays.
"""
from __future__ import annotations

import math
import shutil
import subprocess
import time
from pathlib import Path

from PIL import Image, ImageEnhance

from app import config
from app.services.animation.primitives import RENDER_W, RENDER_H, render_cue
from app.services.animation.types import Cue, Scene

DEFAULT_FPS = config.VIDEO_FPS


def _zoom_pan_bg(bg: Image.Image, t: float, duration: float, motion_seed: int = 0) -> Image.Image:
    """Apply Ken-Burns-style slow zoom + slight pan to the background.

    Returns an image of size (CANVAS_W, CANVAS_H). The zoom factor goes from
    1.00 -> 1.04 over `duration`. Pan direction varies by motion_seed.
    """
    if duration <= 0:
        return bg

    p = max(0.0, min(1.0, t / duration))
    motions = [
        (1.00, 1.04, 0.0, 0.0),
        (1.04, 1.00, 0.0, 0.0),
        (1.00, 1.04, 0.10, 0.0),
        (1.00, 1.04, -0.10, 0.0),
        (1.00, 1.04, 0.0, 0.06),
    ]
    z0, z1, ax, ay = motions[motion_seed % len(motions)]
    zoom = z0 + (z1 - z0) * p

    src_w = int(bg.size[0] / zoom)
    src_h = int(bg.size[1] / zoom)
    cx = bg.size[0] / 2 + ax * (bg.size[0] - src_w) * (p - 0.5)
    cy = bg.size[1] / 2 + ay * (bg.size[1] - src_h) * (p - 0.5)
    x0 = max(0, int(cx - src_w / 2))
    y0 = max(0, int(cy - src_h / 2))
    x1 = min(bg.size[0], x0 + src_w)
    y1 = min(bg.size[1], y0 + src_h)
    cropped = bg.crop((x0, y0, x1, y1))
    if cropped.size != (RENDER_W, RENDER_H):
        cropped = cropped.resize((RENDER_W, RENDER_H), Image.LANCZOS)
    return cropped


def _is_dynamic(cue: Cue) -> bool:
    """A cue is dynamic if its progress changes per frame OR it cycles."""
    if cue.params.get("cycles", 1) > 1:
        return True
    return cue.start < cue.end


def _frame_key(t: float, cues: list[Cue]) -> tuple:
    """Build a coarse cache key per frame. Two frames with the same key produce
    the same overlay output. Quantize progress to 1/15s buckets so motion stays
    smooth but identical-frame stretches collapse.
    """
    bucket = round(t * 15) / 15
    parts = []
    for c in cues:
        if not c.is_active(t):
            continue
        prog = round(c.progress_at(t), 3)
        parts.append((c.kind, c.start, c.end, prog))
    return (bucket, tuple(parts))


def render_scene(
    scene: Scene,
    output_path: str,
    fps: int = DEFAULT_FPS,
    log_progress: bool = True,
) -> str:
    """Render a single Scene to an MP4 file by piping rgb24 frames into ffmpeg.

    The audio at `scene.audio_path` is muxed with -shortest so the segment
    length matches the audio.
    """
    bg_path = Path(scene.background_image)
    if not bg_path.exists():
        raise FileNotFoundError(f"Background not found: {bg_path}")

    bg = Image.open(bg_path).convert("RGB")
    if bg.size != (RENDER_W, RENDER_H):
        bg = bg.resize((RENDER_W, RENDER_H), Image.LANCZOS)
    bg_upscaled = bg.resize((int(RENDER_W * 1.06), int(RENDER_H * 1.06)), Image.LANCZOS)

    duration = max(scene.duration, 0.1)
    total_frames = max(1, int(duration * fps))
    cues = scene.all_cues()

    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found on PATH")

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo",
        "-pix_fmt", "rgb24",
        "-s", f"{RENDER_W}x{RENDER_H}",
        "-r", str(fps),
        "-i", "-",
        "-i", scene.audio_path,
        "-c:v", "libx264", "-preset", config.VIDEO_X264_PRESET, "-crf", config.VIDEO_X264_CRF,
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        "-movflags", "+faststart",
        output_path,
    ]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    last_key = None
    last_bytes = None
    start_time = time.time()
    log_every = max(30, total_frames // 10)

    for frame_idx in range(total_frames):
        t = frame_idx / fps
        key = _frame_key(t, cues)
        if key == last_key and last_bytes is not None:
            proc.stdin.write(last_bytes)
            continue

        canvas = _zoom_pan_bg(bg_upscaled, t, duration, scene.motion_seed)
        canvas = canvas.convert("RGBA")

        for cue in cues:
            if not cue.is_active(t):
                continue
            prog = cue.progress_at(t)
            canvas = render_cue(canvas, cue.kind, prog, cue.params)

        rgb = canvas.convert("RGB")
        last_bytes = rgb.tobytes()
        proc.stdin.write(last_bytes)
        last_key = key

        if log_progress and frame_idx % log_every == 0:
            elapsed = time.time() - start_time
            print(
                f"   [render] frame {frame_idx + 1}/{total_frames} "
                f"({(frame_idx + 1) / total_frames * 100:.1f}%) "
                f"t={t:.1f}s elapsed={elapsed:.1f}s"
            )

    proc.stdin.close()
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg exited with code {rc}")

    return output_path


def render_scenes(
    scenes: list[Scene],
    video_id: int,
    output_dir: Path | str,
    fps: int = DEFAULT_FPS,
) -> list[str]:
    """Render a list of Scenes into per-segment MP4s. Returns paths in order."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for i, scene in enumerate(scenes):
        seg_path = str(output_dir / f"segment_{video_id}_{i:03d}.mp4")
        print(f"[render] Scene {i + 1}/{len(scenes)}: {scene.title!r} "
              f"({scene.duration:.1f}s, {scene.template})")
        render_scene(scene, seg_path, fps=fps)
        paths.append(seg_path)
    return paths
