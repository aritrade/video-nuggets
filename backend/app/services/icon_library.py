"""
In-memory loader for the Nutanix brand icon manifest produced by
`asset_indexer.py`. Provides:

- `get_icon(concept, size, variant)` -> PIL.Image (RGBA) or None
- `find_icons_for_text(text)` -> list of concepts mentioned in the text,
  ranked by trigger phrase length (longer = more specific)
- Concept aliases so callers can ask for `node` and we'll fall back to
  `cloud_node` or `cvm` if the kit doesn't have a generic node icon
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from PIL import Image

MANIFEST_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "assets"
    / "nutanix_brand"
    / "manifest.json"
)
ASSETS_ROOT = Path(__file__).resolve().parent.parent.parent


# Aliases: when a concept isn't directly available, try these in order.
CONCEPT_ALIASES: dict[str, list[str]] = {
    "node": ["cloud_node", "node_count", "cvm", "server"],
    "compute": ["server", "cloud_node", "cvm"],
    "vm": ["user_vms", "virtualization"],
    "vms": ["user_vms", "vm"],
    "cloud": ["distributed_cloud", "multi_cloud", "hybrid_cloud", "private_cloud"],
    "datacenter": ["cloud_dcs", "three_tier", "cloud"],
    "save_money": ["lower_cost", "roi", "dollar"],
    "uptime": ["downtime_reduction", "resiliency"],
    "scale": ["scalability", "distributed_cloud"],
    "fast": ["one_click", "agile", "clock"],
    "secure": ["security", "lock", "compliance"],
    "smart": ["lightbulb", "self_driving", "automation"],
    "files_storage": ["nutanix_files", "files", "integrated_files"],
    "kubernetes": ["container", "distributed_cloud", "nutanix_files"],
    "ai": ["automation", "self_driving", "lightbulb"],
    "infrastructure": ["server", "cloud_node", "datacenter"],
    "core": ["server", "node", "cloud_node"],
    "platform": ["nutanix_files", "files", "calm"],
    "magic": ["lightbulb", "self_driving", "automation"],
    "rules": ["lightbulb", "calm", "blueprint"],
    "pillar": ["lightbulb", "category", "blueprint"],
    "speed": ["clock", "agile", "one_click"],
    "data": ["data_source", "storage", "database"],
    "people": ["user", "headset"],
    "office": ["user", "headset"],
    "manage": ["prism", "calm", "settings"],
    "remote": ["edge", "vpn"],
    "send": ["envelope", "data_pipeline"],
    "request": ["envelope", "alerts"],
    "process": ["gears", "settings", "automation"],
    "control": ["cvm", "prism"],
    "controller": ["cvm", "prism"],
}


# Each concept maps to a set of natural-language trigger phrases that, when
# found in narration text, should make us prefer this concept's icon.
# Phrases are matched as substrings on lowercased text.
CONCEPT_TRIGGERS: dict[str, list[str]] = {
    "web_scale": ["web-scale", "web scale", "google scale", "amazon scale", "internet giants", "internet companies"],
    "self_healing": ["self healing", "self-healing", "fix itself", "fix it automatically", "auto-repair", "automatic repair", "heal itself", "fixes itself"],
    "three_tier": ["three tier", "three-tier", "3-tier", "3 tier", "wedding cake", "san", "old way", "traditional architecture", "three layer", "three-layer", "legacy infrastructure"],
    "cvm": ["cvm", "controller vm", "controller virtual machine", "control plane"],
    "ahv": ["ahv", "nutanix hypervisor", "nutanix's hypervisor"],
    "hypervisor": ["hypervisor", "hypervisors", "esx", "vmware", "hyper-v", "stage manager"],
    "node": ["node", "nodes", "small server", "small box", "lego brick", "lego bricks", "individual server", "single brick", "small bricks", "many small"],
    "server": ["server", "servers", "physical server"],
    "storage": ["storage", "storage drive", "disk drive", "hard drive", "shelf of data", "data shelf", "drives"],
    "ssd": ["ssd", "solid state", "flash drive", "fast drive"],
    "database": ["database", "databases"],
    "network": ["network", "networking", "switch", "switches", "fabric"],
    "vm": ["virtual machine", "virtual machines", " vm ", " vms "],
    "user_vms": ["user vm", "user vms"],
    "container": ["container", "containers", "docker"],
    "kubernetes": ["kubernetes", "k8s"],
    "private_cloud": ["private cloud", "on-prem", "on premises", "on-premises"],
    "hybrid_cloud": ["hybrid cloud", "hybrid"],
    "multi_cloud": ["multi-cloud", "multi cloud", "multiple clouds"],
    "distributed_cloud": ["distributed cloud", "spread out", "many locations", "everywhere"],
    "cloud": ["cloud", "public cloud", "aws", "azure", "google cloud"],
    "edge": ["edge", "branch office", "remote site", "remote office"],
    "datacenter": ["data center", "datacenter", "data centers"],
    "lower_cost": ["save money", "saves money", "lower cost", "lower costs", "cheaper", "less expensive", "save cost", "cost savings", "saves dollars"],
    "roi": ["roi", "return on investment", "payback", "value"],
    "downtime_reduction": ["downtime", "always available", "always on", "less downtime", "no downtime"],
    "uptime": ["uptime", "high availability"],
    "resiliency": ["resilient", "resiliency", "fault tolerant", "robust", "rock solid"],
    "productivity": ["productivity", "more productive", "faster work"],
    "ai": ["artificial intelligence", "machine learning", "ai workload", "smart enough"],
    "infrastructure": ["infrastructure", "core infrastructure"],
    "kubernetes": ["kubernetes", "k8s", "container orchestration"],
    "agile": ["agile", "nimble", "quick", "quickly", "fast move"],
    "automation": ["automation", "automated", "auto-magic", "self-driving", "automatic", "software is the boss", "magic"],
    "scalability": ["scale", "scalable", "scalability", "grow", "growing", "scale out", "more nodes", "share the work", "evenly"],
    "cluster": ["cluster", "clusters", "group of nodes", "bunch of nodes", "fleet of", "team of"],
    "disaster_recovery": ["disaster recovery", " dr ", "data recovery"],
    "backup": ["backup", "backups", "make a copy"],
    "replication": ["replicate", "replication", "make copies", "copies of data"],
    "snapshot": ["snapshot", "snapshots", "point in time"],
    "security": ["security", "secure", "protected", "protect"],
    "encryption": ["encrypt", "encryption", "encrypted"],
    "compliance": ["compliance", "compliant", "regulatory", "audit"],
    "firewall": ["firewall"],
    "lock": ["locked"],
    "files": ["file storage", "shared files", "file share", "files"],
    "nutanix_files": ["nutanix files", "platform services"],
    "application": ["application", "applications", "apps", "workload", "workloads"],
    "user": ["user", "users", "people", "person", "team", "teams"],
    "vdi": ["vdi", "virtual desktop", "desktop"],
    "blueprint": ["blueprint", "blueprints", "template"],
    "calm": ["calm "],
    "prism": ["prism"],
    "flow": ["flow"],
    "era": ["era "],
    "one_click": ["one click", "one-click", "1-click", "single click", "click of a button"],
    "simplified": ["simple", "simpler", "easy", "easier", "simplified", "no more complex"],
    "agile": ["agile", "nimble", "quick", "quickly"],
    "lightbulb": ["idea", "innovation", "innovate"],
    "clock": ["minutes", "seconds", "instantly"],
    "magnifying_glass": ["search", "find", "discover", "look at"],
    "alerts": ["alert", "alerts", "notification", "notifications", "warning"],
    "chart": ["chart", "graph", "metrics"],
    "analytics": ["analytics"],
    "big_data": ["big data"],
    "migration": ["migration", "migrate", "move workloads"],
    "deploy": ["deploy", "deployment", "rollout"],
    "silos": ["silo", "silos", "separate teams", "separate parts"],
    "footprint": ["footprint", "small footprint"],
    "lego": ["lego", "lego brick", "lego castle"],
}


_LIBRARY: dict | None = None
_IMAGE_CACHE: dict[tuple[str, int, int], Image.Image] = {}


def load_manifest(path: Path = MANIFEST_PATH) -> dict:
    """Load and cache the manifest.json. Idempotent."""
    global _LIBRARY
    if _LIBRARY is not None:
        return _LIBRARY
    if not path.exists():
        _LIBRARY = {"concepts": {}, "version": 0}
        return _LIBRARY
    with path.open() as f:
        _LIBRARY = json.load(f)
    return _LIBRARY


def reload_manifest(path: Path = MANIFEST_PATH) -> dict:
    """Force a reload (useful after re-indexing)."""
    global _LIBRARY, _IMAGE_CACHE
    _LIBRARY = None
    _IMAGE_CACHE = {}
    return load_manifest(path)


def list_concepts() -> list[str]:
    return sorted(load_manifest()["concepts"].keys())


def has_concept(concept: str) -> bool:
    lib = load_manifest()
    if concept in lib["concepts"]:
        return True
    return any(a in lib["concepts"] for a in CONCEPT_ALIASES.get(concept, []))


def _resolve_concept(concept: str) -> Optional[str]:
    """Return the actual manifest key to use for `concept`, applying aliases."""
    lib = load_manifest()
    if concept in lib["concepts"]:
        return concept
    for alias in CONCEPT_ALIASES.get(concept, []):
        if alias in lib["concepts"]:
            return alias
    return None


def get_icon(
    concept: str,
    size: int = 512,
    variant: int = 0,
) -> Optional[Image.Image]:
    """Return an RGBA PIL.Image for the given concept, or None.

    `variant=0` returns the primary variant; higher numbers walk through
    additional variants if the brand kit has them. The image is cached.
    """
    actual = _resolve_concept(concept)
    if not actual:
        return None
    lib = load_manifest()
    entries = lib["concepts"][actual]
    if not entries:
        return None
    idx = variant % len(entries)
    cache_key = (actual, size, idx)
    if cache_key in _IMAGE_CACHE:
        return _IMAGE_CACHE[cache_key]

    entry = entries[idx]
    sizes = entry.get("sizes", {})
    chosen_path = sizes.get(str(size)) or sizes.get("512") or sizes.get("256") or entry.get("raw_path")
    if not chosen_path:
        return None
    full = ASSETS_ROOT / chosen_path
    if not full.exists():
        return None
    try:
        img = Image.open(full).convert("RGBA")
    except Exception:
        return None
    if img.size != (size, size):
        img = img.resize((size, size), Image.LANCZOS)
    _IMAGE_CACHE[cache_key] = img
    return img


def find_icons_for_text(
    text: str,
    top_k: int = 5,
    exclude: set[str] | None = None,
    title: str | None = None,
) -> list[tuple[str, int]]:
    """Scan `text` for concept trigger phrases. Return ranked (concept, score).

    Score = sum over triggers of (word_count + 1) * occurrences_in_text. If
    `title` is provided, occurrences in the title are counted with a 3x weight
    so the section's headline topic dominates over passing mentions in body.

    Concepts whose icons are not actually available (manifest miss + alias miss)
    are skipped.
    """
    exclude = exclude or set()
    body_lower = text.lower()
    title_lower = (title or "").lower()
    scores: dict[str, int] = {}

    for concept, triggers in CONCEPT_TRIGGERS.items():
        if concept in exclude:
            continue
        if not has_concept(concept):
            continue
        score = 0
        for trig in triggers:
            t = trig.lower().strip()
            if not t:
                continue
            weight = len(t.split()) + 1
            pat = re.compile(r"\b" + re.escape(t) + r"\b")
            body_hits = len(pat.findall(body_lower))
            title_hits = len(pat.findall(title_lower)) if title_lower else 0
            score += weight * (body_hits + 3 * title_hits)
        if score > 0:
            scores[concept] = score

    return sorted(scores.items(), key=lambda kv: -kv[1])[:top_k]


def best_icon_for_text(text: str, fallback: str = "node", title: str | None = None) -> Optional[Image.Image]:
    """Convenience: return the icon for the highest-scoring concept in text."""
    matches = find_icons_for_text(text, top_k=1, title=title)
    if matches:
        return get_icon(matches[0][0])
    return get_icon(fallback)


def best_concept_for_text(text: str, fallback: Optional[str] = None, title: str | None = None) -> Optional[str]:
    matches = find_icons_for_text(text, top_k=1, title=title)
    if matches:
        return matches[0][0]
    return fallback
