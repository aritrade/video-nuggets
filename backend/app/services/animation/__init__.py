"""Nutanix Video Nuggets animation engine.

Renders narrated explainer videos by composing a static brand-styled background
with animated overlays whose timing is locked to word-level TTS timestamps.

Public types live in `types.py`. Drawing primitives in `primitives.py`. The
frame compositor + ffmpeg pipe in `renderer.py`. Scene templates in
`templates/`. Heuristic storyboard generator in `storyboard.py`.
"""
