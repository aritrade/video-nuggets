"""
Fast single-scene preview for iterating on the animation engine.

Renders ONE animated scene (default: an LLM-style "diagram" scene) to an MP4 so
you can eyeball pacing, the diagram build, and narration-synced beats without
running the whole upload -> generate pipeline. Audio is a synthesized silent
track with a hand-made word timeline, so it needs no network and no LLM.

Usage:
    python preview_scene.py                 # diagram demo -> output/videos/preview.mp4
    python preview_scene.py --template default
    python preview_scene.py --seconds 9 --out /tmp/scene.mp4
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from app import config
from app.services import slide_image_generator
from app.services.animation.renderer import render_scene
from app.services.animation.templates import TemplateContext, build as build_template


def _silent_audio(path: Path, seconds: float) -> None:
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", str(seconds), "-c:a", "libmp3lame", str(path),
    ], check=True)


def _fake_timeline(words_at: dict[str, float]) -> list[dict]:
    return [{"word": w, "start": t, "end": t + 0.3, "duration": 0.3}
            for w, t in words_at.items()]


DEMO_DIAGRAM = {
    "nodes": [
        {"id": "user", "label": "User Apps", "col": 0, "row": 0, "icon": "user_vms"},
        {"id": "api", "label": "API Gateway", "col": 1, "row": 0, "icon": "api"},
        {"id": "svc", "label": "Services", "col": 2, "row": 0, "icon": "cluster"},
        {"id": "store", "label": "Shared Storage", "col": 1, "row": 1, "icon": "storage"},
    ],
    "edges": [
        {"from": "user", "to": "api", "label": "request"},
        {"from": "api", "to": "svc", "label": "routes"},
        {"from": "svc", "to": "store", "label": "reads"},
    ],
}

DEMO_BEATS = [
    {"anchor": "apps", "text": "Apps send a request"},
    {"anchor": "gateway", "text": "The gateway routes it"},
    {"anchor": "services", "text": "Services do the work"},
    {"anchor": "storage", "text": "Data lives in shared storage"},
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", default="diagram")
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--out", default=str(config.VIDEOS_DIR / "preview.mp4"))
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    title = "How the system fits together"
    body = ("Imagine your apps need data. The gateway routes each request to the "
            "right services, and those services read and write to one shared storage pool.")

    # Clean backdrop, exactly like the animated pipeline produces.
    slides_dir = config.VIDEOS_DIR / "preview_slides"
    slides_dir.mkdir(parents=True, exist_ok=True)
    prev_i, prev_b = slide_image_generator.OMIT_FOCAL_ICONS, slide_image_generator.OMIT_BODY_TEXT
    slide_image_generator.OMIT_FOCAL_ICONS = True
    slide_image_generator.OMIT_BODY_TEXT = True
    try:
        bg = slide_image_generator.render_default(title, body, 1, 3, title)
    finally:
        slide_image_generator.OMIT_FOCAL_ICONS, slide_image_generator.OMIT_BODY_TEXT = prev_i, prev_b
    bg_path = slides_dir / "bg.png"
    bg.save(bg_path)

    audio_path = config.VIDEOS_DIR / "preview_audio.mp3"
    _silent_audio(audio_path, args.seconds)

    timeline = _fake_timeline({
        "apps": 1.0, "gateway": 3.0, "services": 5.0, "storage": 7.0,
    })

    ctx = TemplateContext(
        title=title, body=body, duration=args.seconds,
        audio_path=str(audio_path), background_image=str(bg_path),
        section_index=0, motion_seed=1, word_timeline=timeline,
        layout="default", slide_num=1, total_slides=3,
        extra={"beats": DEMO_BEATS, "diagram": DEMO_DIAGRAM, "headline": title},
    )

    scene = build_template(args.template, ctx)
    print(f"[preview] template={scene.template} duration={scene.duration:.1f}s "
          f"render={config.RENDER_W}x{config.RENDER_H}@{config.VIDEO_FPS}")
    render_scene(scene, str(out), fps=config.VIDEO_FPS)
    print(f"[preview] wrote {out}")


if __name__ == "__main__":
    main()
