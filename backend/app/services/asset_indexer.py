"""
Indexes Nutanix brand icons into a concept-keyed manifest.

Walks `backend/assets/nutanix_brand/raw/` (PNG icons), tokenizes filenames into
words (CamelCase, &, _, digits split), and classifies each file into one or
more concept buckets. Multiple variants per concept are preserved as ordered
lists. Resizes each PNG to 256/512/1024 px caches for fast loading.

Run as a module to (re)build the manifest:

    cd backend && python -m app.services.asset_indexer
"""
import json
import re
from pathlib import Path
from typing import Iterable

from PIL import Image

ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "nutanix_brand"
RAW_DIR = ASSETS_DIR / "raw"
CACHE_DIR = ASSETS_DIR / "cache"
MANIFEST_PATH = ASSETS_DIR / "manifest.json"
REVIEW_PATH = ASSETS_DIR / "manifest_review.json"

CACHE_SIZES = (256, 512, 1024)


# Concept -> list of keyword token-sequences. A keyword matches when its tokens
# appear as a CONSECUTIVE sub-list of the file's tokens (so "node" doesn't match
# "NoDedicated..." -> ['no','dedicated',...]). More specific concepts come first.
# Each keyword is a string that gets re-tokenized via `tokenize()` so we can write
# multi-token keywords naturally like "self healing" or "1 click".
CONCEPT_RULES: list[tuple[str, list[str]]] = [
    ("cvm", ["cvm", "ncvm"]),
    ("ahv", ["ahv"]),
    ("esxi", ["esxi"]),
    ("hyperv", ["hyper v"]),
    ("hypervisor", ["hypervisor", "hypervisors", "multiple hypervisors"]),
    ("acropolis", ["acropolis"]),
    ("nutanix_kubernetes", ["nutanix kubernetes", "karbon"]),
    ("kubernetes", ["kubernetes", "k8s", "kube"]),
    ("calm", ["calm"]),
    ("blueprint", ["blueprint", "blueprints"]),
    ("prism", ["prism"]),
    ("flow", ["flow"]),
    ("era", ["era"]),
    ("nutanix_files", ["integrated file services", "nutanix files"]),
    ("nutanix_objects", ["nutanix objects"]),
    ("nutanix_volumes", ["acropolis block services", "volumes"]),

    ("web_scale", ["web scale", "webscale"]),
    ("self_healing", ["self healing", "selfhealing"]),
    ("invisible_infra", ["invisible infrastructure"]),
    ("simple_platform", ["simple 1 click platform", "simple"]),
    ("simplified", ["simplified", "simplify"]),
    ("one_click", ["1 click", "one click"]),
    ("agile", ["agile"]),
    ("resilient", ["resilient", "designed for resiliency"]),

    ("three_tier", ["3 tier", "three tier", "3 tier dcs"]),
    ("cloud_node", ["cloud node"]),
    ("node_count", ["2 node", "4 node"]),
    ("node", ["node"]),
    ("server", ["server platforms", "180 server platforms", "key management server"]),
    ("cluster_lockdown", ["cluster lockdown"]),
    ("cluster", ["cluster", "clusters"]),

    ("ssd", ["ssd"]),
    ("hdd", ["hdd"]),
    ("boot_drive", ["boot drive"]),
    ("database", ["database"]),
    ("data_source", ["data source"]),
    ("data_pipeline", ["data pipeline"]),
    ("data_visualization", ["data visualization"]),
    ("data_integrity", ["data integrity"]),
    ("big_data", ["big data"]),
    ("analytics", ["analytics"]),
    ("intelligent_storage", ["intelligent storage"]),
    ("enterprise_storage", ["enterprise storage"]),
    ("storage", ["storage"]),

    ("sdn", ["sdn"]),
    ("vpn", ["vpn", "xi vpn"]),
    ("micro_segmentation", ["micro segmentation"]),
    ("nic", ["nic"]),
    ("hba", ["hba"]),
    ("network", ["network", "generic network"]),

    ("user_vms", ["user vms"]),
    ("vdi", ["vdi", "virtual desktop infrastructure"]),
    ("vm", ["vm", "vms"]),
    ("container", ["container", "containers"]),

    ("multi_cloud", ["multi cloud"]),
    ("hybrid_cloud", ["private hybrid public cloud", "hybrid cloud"]),
    ("private_cloud", ["private cloud"]),
    ("distributed_cloud", ["distributed cloud"]),
    ("cloud_dcs", ["cloud dcs"]),
    ("aws_cloud", ["aws cloud", "aws cloud profile"]),
    ("azure_cloud", ["azure cloud", "azure cloud profile"]),
    ("cloud", ["cloud", "cloud profile", "cloud black", "cloud purple"]),

    ("nofiles", ["no files"]),
    ("files", ["files", "file", "add files"]),

    ("disaster_recovery", ["disaster recovery", "dr", "built in dr", "dr perm to perm"]),
    ("business_continuity", ["business continuity"]),
    ("replication", ["replicate", "replication", "recover anywhere"]),
    ("protect", ["protect"]),
    ("snapshot", ["snapshot", "snapshots"]),
    ("backup", ["backup", "unify primary", "secondary backup"]),
    ("encryption", ["encryptor", "encryption"]),
    ("firewall", ["firewall"]),
    ("lock", ["lock"]),
    ("key", ["key"]),
    ("two_factor", ["two factor", "2 factor"]),
    ("authentication", ["authentication"]),
    ("permissions", ["permissions"]),
    ("policies", ["policies"]),
    ("security", ["security"]),
    ("compliance", ["compliance"]),

    ("lower_cost", ["lower cost", "lower costs", "operational efficiency", "reduced costs", "months to payback", "payback"]),
    ("roi", ["roi", "instant time to value", "quick roi"]),
    ("downtime_reduction", ["less unplanned downtime", "downtime"]),
    ("uptime", ["uptime", "always on"]),
    ("resiliency", ["resiliency"]),
    ("productivity", ["productivity", "higher operations productivity", "increased productivity"]),
    ("competitive", ["competitive", "gain competitive advantage"]),
    ("revenue", ["revenue", "increased revenue"]),
    ("self_driving", ["self driving", "driver assistance"]),
    ("automation", ["automation", "intelligent automation", "conditional automation"]),
    ("ai", ["ai", "artificial intelligence"]),
    ("scalability", ["scalability", "limitless scalability", "robust scalability"]),
    ("specialized_edge", ["specialized edge", "specialized edge hardware"]),
    ("edge", ["edge", "edges", "edge device add"]),

    ("migration", ["migration"]),
    ("deploy", ["deploy", "deployment"]),
    ("dev_test", ["dev test", "devtest"]),
    ("test", ["test"]),
    ("learn", ["learn", "training"]),
    ("assess", ["assess", "assessment"]),
    ("measure", ["measure"]),
    ("optimize", ["optimize", "optimization"]),
    ("sync", ["sync"]),
    ("update", ["update"]),
    ("export", ["export"]),
    ("sell", ["sell"]),
    ("dollar", ["dollar"]),
    ("cost_complexity", ["cost complexity"]),
    ("action", ["action"]),
    ("consumption", ["consumption"]),
    ("improve_infra", ["improve infrastructure"]),
    ("subscription", ["subscription", "subscriptions"]),
    ("licenses", ["licenses", "license"]),

    ("alerts", ["alerts"]),
    ("notifications", ["notifications"]),
    ("schedule", ["schedule", "report schedule"]),
    ("report", ["report"]),
    ("tasks", ["tasks"]),
    ("settings", ["settings"]),
    ("gears", ["gears"]),
    ("cog", ["cog"]),
    ("magnifying_glass", ["magnifying glass"]),
    ("clock", ["clock"]),
    ("lightbulb", ["lightbulb"]),
    ("star", ["star"]),
    ("envelope", ["envelope"]),
    ("document", ["document"]),
    ("chart", ["chart with line graph", "chart"]),
    ("system_logs", ["system logs"]),
    ("category", ["categories"]),
    ("blueprints_calm", ["blueprint", "blueprints"]),

    ("application", ["application", "applications", "enterprise applications", "financial apps", "virtual applications"]),
    ("end_user_computing", ["end user computing"]),
    ("virtualization", ["virtualization", "server virtualization"]),

    ("user", ["user", "users", "person", "people"]),
    ("laptop", ["laptop"]),
    ("mobile_phone", ["mobile phone"]),
    ("telephone", ["telephone"]),
    ("video", ["video"]),
    ("headset", ["headset"]),

    ("healthcare", ["healthcare"]),
    ("entertainment", ["entertainment"]),
    ("education", ["education", "student administrative"]),
    ("retail", ["retail"]),
    ("financial_services", ["financial services"]),
    ("manufacturing", ["manufacturing"]),
    ("government", ["state government", "federal government"]),
    ("insurance", ["insurance"]),

    ("nutanix_profile", ["nutanix cloud profile"]),
    ("nutanix_go", ["nutanix go"]),

    ("datacenter", ["dc", "dcs", "datacenter", "data center"]),
    ("silos", ["silos"]),
    ("footprint", ["footprint", "small footprint"]),
    ("xray", ["x ray", "xray"]),
    ("ncc", ["ncc"]),
    ("nfv", ["nfv"]),
]


def tokenize(stem: str) -> list[str]:
    """Split a filename stem into lowercase tokens.

    Handles: CamelCase, snake_case, hyphens, ampersands, digits, plus signs.
    Acronyms (consecutive uppercase) stay together: 'UserVMs' -> ['user','vms'],
    'NCVM' -> ['ncvm'], 'CVM1' -> ['cvm','1'].
    """
    s = re.sub(r"[&_\-+.]", " ", stem)
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    s = re.sub(r"([A-Za-z])(\d)", r"\1 \2", s)
    s = re.sub(r"(\d)([A-Za-z])", r"\1 \2", s)
    parts = [p.lower() for p in s.split() if p]
    return parts


def _contains_subseq(haystack: list[str], needle: list[str]) -> bool:
    """True if `needle` appears as a consecutive sub-list within `haystack`."""
    if not needle:
        return False
    n = len(needle)
    for i in range(len(haystack) - n + 1):
        if haystack[i:i + n] == needle:
            return True
    return False


def classify(filename: str) -> tuple[str | None, int, list[str]]:
    """Match a filename to the first concept whose keyword tokens appear as a
    consecutive sub-list of the filename's tokens.

    Returns (concept, variant_index, tokens). variant_index is the trailing
    digit (e.g. CVM2 -> 2) used to order variants within a concept. 0 if none.
    """
    stem = Path(filename).stem
    tokens = tokenize(stem)

    variant = 0
    if tokens and tokens[-1].isdigit():
        try:
            variant = int(tokens[-1])
        except ValueError:
            variant = 0

    for concept, keywords in CONCEPT_RULES:
        for kw in keywords:
            kw_tokens = tokenize(kw)
            if _contains_subseq(tokens, kw_tokens):
                return concept, variant, tokens
    return None, variant, tokens


def build_manifest(raw_dir: Path = RAW_DIR, cache_dir: Path = CACHE_DIR) -> dict:
    """Walk raw_dir, classify, resize and emit manifest.json."""
    raw_dir = Path(raw_dir)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    for size in CACHE_SIZES:
        (cache_dir / str(size)).mkdir(parents=True, exist_ok=True)

    concepts: dict[str, list[dict]] = {}
    unclassified: list[dict] = []

    for png in sorted(raw_dir.glob("*.png")):
        concept, variant, tokens = classify(png.name)
        entry = {
            "filename": png.name,
            "stem": png.stem,
            "tokens": tokens,
            "variant": variant,
            "raw_path": str(png.relative_to(raw_dir.parent.parent.parent)),
            "sizes": {},
        }

        try:
            img = Image.open(png).convert("RGBA")
        except Exception as e:
            unclassified.append({**entry, "error": f"open: {e}"})
            continue

        for size in CACHE_SIZES:
            out = cache_dir / str(size) / png.name
            if not out.exists() or out.stat().st_mtime < png.stat().st_mtime:
                resized = img.resize((size, size), Image.LANCZOS)
                resized.save(out, "PNG")
            entry["sizes"][str(size)] = str(out.relative_to(raw_dir.parent.parent.parent))

        if concept is None:
            unclassified.append(entry)
            continue

        concepts.setdefault(concept, []).append(entry)

    for c in concepts:
        concepts[c].sort(key=lambda e: (
            0 if e["variant"] > 0 else 1,
            e["variant"],
            e["filename"],
        ))

    manifest = {
        "version": 1,
        "raw_dir": str(raw_dir.relative_to(raw_dir.parent.parent.parent)),
        "cache_dir": str(cache_dir.relative_to(raw_dir.parent.parent.parent)),
        "concepts": concepts,
        "concept_count": len(concepts),
        "icon_count": sum(len(v) for v in concepts.values()),
        "unclassified_count": len(unclassified),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    REVIEW_PATH.write_text(json.dumps({"unclassified": unclassified}, indent=2))
    return manifest


def main():
    print(f"[asset_indexer] Scanning {RAW_DIR}...")
    manifest = build_manifest()
    print(f"[asset_indexer] Mapped {manifest['icon_count']} icons across {manifest['concept_count']} concepts")
    print(f"[asset_indexer] Unclassified: {manifest['unclassified_count']} (see {REVIEW_PATH})")
    print(f"[asset_indexer] Manifest: {MANIFEST_PATH}")
    print()
    print("Top concepts by variant count:")
    items = sorted(manifest["concepts"].items(), key=lambda kv: -len(kv[1]))
    for concept, entries in items[:20]:
        names = ", ".join(e["filename"] for e in entries[:3])
        more = f" (+{len(entries) - 3})" if len(entries) > 3 else ""
        print(f"  {concept:24s}  {len(entries)}  {names}{more}")


if __name__ == "__main__":
    main()
