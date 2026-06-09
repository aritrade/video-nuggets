#!/usr/bin/env python3
"""Turn the rendered seed library into Vercel deploy artifacts.

Reads backend/seed/ (manifest + media + transcripts) and produces:
  - frontend/public/static/{videos,thumbnails,transcripts}/{id}.{ext}  (static assets)
  - api/_data/library.json   (playlist/section grouping for the Library page)
  - api/_data/videos.json    (id -> detail for the Watch page)
  - api/_data/corpus.json     (transcript chunks for the /api/chat retrieval)

This is the one-time bridge from the real render pipeline to the static,
serverless Vercel demo. Re-run it after re-rendering the seed library.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "backend" / "seed"
PUBLIC_STATIC = ROOT / "frontend" / "public" / "static"
API_DATA = ROOT / "api" / "_data"

SECTION_NAMES = {
    "basic": "Core Foundation",
    "platform_deep_dive": "Platform Deep Dive",
    "advanced": "Advanced",
}
SECTION_ORDER = ["basic", "platform_deep_dive", "advanced"]

# Cues whose text is boilerplate intro/outro narration; skip for retrieval.
_SKIP_CUE = re.compile(r"^(welcome to|that wraps up|thanks for watching)", re.I)


def _parse_vtt_cues(vtt_path: Path) -> list[str]:
    """Return the spoken text of each cue, in order."""
    cues: list[str] = []
    buf: list[str] = []
    for raw in vtt_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            if buf:
                cues.append(" ".join(buf))
                buf = []
            continue
        if line == "WEBVTT" or line.isdigit() or "-->" in line:
            continue
        buf.append(line)
    if buf:
        cues.append(" ".join(buf))
    return cues


def main() -> None:
    manifest = json.loads((SEED / "manifest.json").read_text())
    nuggets = manifest["nuggets"]

    for sub in ("videos", "thumbnails", "transcripts"):
        (PUBLIC_STATIC / sub).mkdir(parents=True, exist_ok=True)
    API_DATA.mkdir(parents=True, exist_ok=True)

    videos: dict[str, dict] = {}
    corpus: list[dict] = []
    by_section: dict[str, list[dict]] = {}

    for i, n in enumerate(nuggets):
        vid = i + 1
        key = n["key"]
        difficulty = n.get("difficulty", "basic")

        shutil.copyfile(SEED / "videos" / n["video_file"], PUBLIC_STATIC / "videos" / f"{vid}.mp4")
        shutil.copyfile(SEED / "thumbnails" / n["thumbnail_file"], PUBLIC_STATIC / "thumbnails" / f"{vid}.png")
        shutil.copyfile(SEED / "transcripts" / n["transcript_file"], PUBLIC_STATIC / "transcripts" / f"{vid}.vtt")

        video_meta = {
            "id": vid,
            "title": n["title"],
            "description": n["description"],
            "status": "ready",
            "video_url": f"/static/videos/{vid}.mp4",
            "transcript_url": f"/static/transcripts/{vid}.vtt",
            "thumbnail_url": f"/static/thumbnails/{vid}.png",
            "slides_url": None,
            "duration_seconds": n["duration_seconds"],
            "difficulty_level": difficulty,
            "visibility": "public",
            "version": 1,
            "playlist_id": 1,
            "playlist_order": i,
            "created_at": "2024-01-01T00:00:00",
        }
        videos[str(vid)] = video_meta
        by_section.setdefault(difficulty, []).append(video_meta)

        for cue in _parse_vtt_cues(SEED / "transcripts" / n["transcript_file"]):
            if _SKIP_CUE.match(cue) or len(cue) < 40:
                continue
            corpus.append({"video_id": vid, "title": n["title"], "text": cue})

    sections = []
    for key in SECTION_ORDER:
        vids = by_section.get(key)
        if not vids:
            continue
        sections.append({"key": key, "name": SECTION_NAMES.get(key, key), "videos": vids})

    library = {
        "playlists": [
            {
                "id": 1,
                "name": "Video Nuggets Library",
                "description": "Auto-generated narrated micro-lessons.",
                "is_default": True,
                "sections": sections,
                "total_videos": len(videos),
            }
        ]
    }

    (API_DATA / "library.json").write_text(json.dumps(library, indent=2))
    (API_DATA / "videos.json").write_text(json.dumps(videos, indent=2))
    (API_DATA / "corpus.json").write_text(json.dumps(corpus, indent=2))

    print(f"[build_vercel_data] videos={len(videos)} corpus_chunks={len(corpus)}")
    print(f"[build_vercel_data] static -> {PUBLIC_STATIC}")
    print(f"[build_vercel_data] data   -> {API_DATA}")


if __name__ == "__main__":
    main()
