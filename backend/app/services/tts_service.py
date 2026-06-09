"""
Edge TTS narration service that generates audio per slide and captures
word-level timestamps used downstream by the animation engine.

For each segment we produce two cached files:
  - audio file (mp3)
  - timeline.json: list of {word, start, end, duration} in seconds, where the
    start/end are aligned with the audio timeline so animation cues can fire on
    specific words during narration.
"""
import asyncio
import json
from pathlib import Path
from typing import Optional

import edge_tts

from app.config import AUDIO_DIR, EDGE_TTS_VOICE, EDGE_TTS_RATE, VIDEO_MAX_DURATION_MINUTES
from app.services.content_parser import ParsedContent

TIMELINE_DIR = AUDIO_DIR.parent / "timelines"
TIMELINE_DIR.mkdir(parents=True, exist_ok=True)


async def generate_narration(
    content: ParsedContent,
    video_id: int,
    voice: Optional[str] = None,
    rate: Optional[str] = None,
) -> list[dict]:
    """Generate audio narration for each section. Returns list of audio file info."""
    voice = voice or EDGE_TTS_VOICE
    rate = rate or EDGE_TTS_RATE
    audio_segments = []

    intro_text = f"Welcome to Video Nuggets OS. In this lesson, we'll explore {content.title}. Let's get started!"
    intro_path, intro_tl = await _generate_audio(intro_text, video_id, "intro", voice, rate)
    audio_segments.append({
        "path": intro_path,
        "timeline_path": intro_tl,
        "text": intro_text,
        "section_index": -1,
        "type": "intro",
    })

    for i, section in enumerate(content.sections):
        narration_text = _prepare_narration_text(section.title, section.body)
        if not narration_text.strip():
            continue

        segment_path, segment_tl = await _generate_audio(narration_text, video_id, f"section_{i}", voice, rate)
        audio_segments.append({
            "path": segment_path,
            "timeline_path": segment_tl,
            "text": narration_text,
            "section_index": i,
            "type": "section",
        })

    outro_text = (
        f"That wraps up our lesson on {content.title}. "
        "Thanks for watching! If you found this helpful, explore more Video Nuggets "
        "to keep learning. See you next time!"
    )
    outro_path, outro_tl = await _generate_audio(outro_text, video_id, "outro", voice, rate)
    audio_segments.append({
        "path": outro_path,
        "timeline_path": outro_tl,
        "text": outro_text,
        "section_index": -2,
        "type": "outro",
    })

    return audio_segments


async def _generate_audio(
    text: str,
    video_id: int,
    segment_name: str,
    voice: str,
    rate: str,
) -> tuple[str, str]:
    """Generate audio + word timeline for one segment.

    Returns (audio_path, timeline_path). Both are cached on disk by filename;
    if both already exist and are non-empty, regeneration is skipped.
    """
    audio_path = AUDIO_DIR / f"video_{video_id}_{segment_name}.mp3"
    timeline_path = TIMELINE_DIR / f"video_{video_id}_{segment_name}.json"

    audio_ok = audio_path.exists() and audio_path.stat().st_size > 0
    timeline_ok = timeline_path.exists() and timeline_path.stat().st_size > 0

    if audio_ok and timeline_ok:
        return str(audio_path), str(timeline_path)

    communicate = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    timeline: list[dict] = []
    write_audio = not audio_ok
    f = audio_path.open("wb") if write_audio else None
    try:
        async for chunk in communicate.stream():
            ctype = chunk.get("type")
            if ctype == "audio" and f is not None:
                f.write(chunk["data"])
            elif ctype == "WordBoundary":
                start = chunk["offset"] / 10_000_000
                duration = chunk["duration"] / 10_000_000
                timeline.append({
                    "word": chunk["text"],
                    "start": round(start, 4),
                    "end": round(start + duration, 4),
                    "duration": round(duration, 4),
                })
    finally:
        if f is not None:
            f.close()

    timeline_path.write_text(json.dumps({
        "text": text,
        "voice": voice,
        "rate": rate,
        "words": timeline,
    }, indent=2))

    return str(audio_path), str(timeline_path)


def load_timeline(timeline_path: str) -> dict:
    """Load a previously written timeline.json."""
    with open(timeline_path) as f:
        return json.load(f)


def _prepare_narration_text(title: str, body: str) -> str:
    """Clean and prepare text for TTS narration."""
    body = body.strip()
    if not body:
        return f"Now let's talk about {title}."

    lines = body.split("\n")
    cleaned = []
    for line in lines:
        line = line.strip()
        if line.startswith("•") or line.startswith("-"):
            line = line.lstrip("•-").strip()
        if line:
            cleaned.append(line)

    narration = " ".join(cleaned)

    if len(narration) > 1500:
        sentences = narration.split(".")
        truncated = []
        total = 0
        for s in sentences:
            if total + len(s) > 1400:
                break
            truncated.append(s)
            total += len(s)
        narration = ".".join(truncated) + "."

    return narration


async def get_available_voices() -> list[dict]:
    """List available Edge TTS voices."""
    voices = await edge_tts.list_voices()
    return [
        {"name": v["Name"], "gender": v["Gender"], "locale": v["Locale"]}
        for v in voices
        if v["Locale"].startswith("en-")
    ]
