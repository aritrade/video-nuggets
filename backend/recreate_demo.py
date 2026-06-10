"""
Recreate one committed demo nugget ("What is Hyperconverged Infrastructure?")
with the new video intelligence: narration-synced animated diagrams + kinetic
beats.

The diagram/beat engine is identical to the live (Groq) path; here the visual
storyboard is hand-authored so it runs without an LLM key, and pinned onto the
sections (generate_visual_scripts respects a pre-authored visual_script).
On Render with GROQ_API_KEY set, this storyboard is produced automatically.

    cd backend && .venv/bin/python recreate_demo.py
    # -> overwrites seed/videos/hci-basics.mp4 (+ thumbnail + transcript)
"""
from __future__ import annotations

import asyncio
import shutil

from app import config
from app.services.content_parser import parse_source
from app.services.content_simplifier import simplify_content
from app.services.storyboard_llm import generate_visual_scripts
from app.services.tts_service import generate_narration
from app.services.video_composer import compose_video

VIDEO_ID = 101  # scratch id; output is copied onto the seed by key

# One storyboard per section (indices match the simplified HCI nugget).
# Anchors are words that appear in the narration so beats/nodes time to the voice;
# unmatched anchors gracefully fall back to even spacing.
SCRIPTS = [
    {
        "scene_type": "diagram",
        "headline": "Three silos become one box",
        "beats": [
            {"anchor": "servers", "text": "Servers do the thinking"},
            {"anchor": "storage", "text": "Storage arrays hold data"},
            {"anchor": "network", "text": "A network wires them"},
            {"anchor": "box", "text": "HCI: one all-in-one box"},
        ],
        "diagram": {
            "nodes": [
                {"id": "srv", "label": "Servers", "col": 0, "row": 0, "icon": "server"},
                {"id": "stor", "label": "Storage Arrays", "col": 0, "row": 1, "icon": "storage"},
                {"id": "net", "label": "Network", "col": 0, "row": 2, "icon": "network"},
                {"id": "hci", "label": "HCI Node", "col": 2, "row": 1, "icon": "cloud_node"},
            ],
            "edges": [
                {"from": "srv", "to": "hci", "label": "merge"},
                {"from": "stor", "to": "hci", "label": "merge"},
                {"from": "net", "to": "hci", "label": "merge"},
            ],
        },
    },
    {
        "scene_type": "diagram",
        "headline": "Nodes group into a cluster",
        "beats": [
            {"anchor": "node", "text": "A node is one server"},
            {"anchor": "group", "text": "Group several nodes"},
            {"anchor": "cluster", "text": "They form one cluster"},
            {"anchor": "magic", "text": "Capacity grows as you add"},
        ],
        "diagram": {
            "nodes": [
                {"id": "n1", "label": "Node 1", "col": 0, "row": 0, "icon": "server"},
                {"id": "n2", "label": "Node 2", "col": 1, "row": 0, "icon": "server"},
                {"id": "n3", "label": "Node 3", "col": 2, "row": 0, "icon": "server"},
                {"id": "cl", "label": "One Cluster", "col": 1, "row": 1, "icon": "cluster"},
            ],
            "edges": [
                {"from": "n1", "to": "cl", "label": "join"},
                {"from": "n2", "to": "cl", "label": "join"},
                {"from": "n3", "to": "cl", "label": "join"},
            ],
        },
    },
    {
        "scene_type": "diagram",
        "headline": "Local drives, one shared pool",
        "beats": [
            {"anchor": "node", "text": "Every node has local drives"},
            {"anchor": "contributes", "text": "Each contributes its drives"},
            {"anchor": "pool", "text": "One shared storage pool"},
            {"anchor": "virtual", "text": "One virtual storage system"},
        ],
        "diagram": {
            "nodes": [
                {"id": "a", "label": "Node A drives", "col": 0, "row": 0, "icon": "storage"},
                {"id": "b", "label": "Node B drives", "col": 1, "row": 0, "icon": "storage"},
                {"id": "c", "label": "Node C drives", "col": 2, "row": 0, "icon": "storage"},
                {"id": "pool", "label": "Shared Storage Pool", "col": 1, "row": 1, "icon": "database"},
            ],
            "edges": [
                {"from": "a", "to": "pool", "label": "contributes"},
                {"from": "b", "to": "pool", "label": "contributes"},
                {"from": "c", "to": "pool", "label": "contributes"},
            ],
        },
    },
    {
        # "Why teams choose HCI": NOT ordered steps - so no big card numerals.
        # Pinned to the clean `default` layout; each reason types in as the
        # narration reaches its anchor word (kinetic bullet list).
        "scene_type": "key_points",
        "headline": "Why teams choose HCI",
        "beats": [
            {"anchor": "simplicity", "text": "Simplicity: one console"},
            {"anchor": "console", "text": "One team manages it all"},
            {"anchor": "predictable", "text": "Predictable, linear growth"},
        ],
    },
]

# Sections forced onto a specific slide layout (overrides keyword detection).
PREFERRED_LAYOUT = {3: "default"}


async def main() -> None:
    src = config.UPLOADS_DIR / "hci-basics.txt"
    parsed = parse_source(str(src))
    parsed = await simplify_content(parsed)

    for i, script in enumerate(SCRIPTS):
        if i < len(parsed.sections):
            parsed.sections[i].visual_script = script
    for i, layout in PREFERRED_LAYOUT.items():
        if i < len(parsed.sections):
            parsed.sections[i].preferred_layout = layout
    await generate_visual_scripts(parsed)  # respects the pinned scripts above

    audio = await generate_narration(parsed, VIDEO_ID)
    result = compose_video(VIDEO_ID, None, audio, [], parsed_content=parsed)
    print(f"[recreate_demo] rendered {result['video_path']} "
          f"({result['duration_seconds']:.1f}s)")

    # Overwrite the committed seed for this nugget (key: hci-basics).
    pairs = [
        (result["video_path"], config.SEED_DIR / "videos" / "hci-basics.mp4"),
        (result["thumbnail_path"], config.SEED_DIR / "thumbnails" / "hci-basics.png"),
        (result["transcript_path"], config.SEED_DIR / "transcripts" / "hci-basics.vtt"),
    ]
    for srcf, dst in pairs:
        if srcf:
            shutil.copy(srcf, dst)
            print(f"[recreate_demo] -> {dst}")


if __name__ == "__main__":
    asyncio.run(main())
