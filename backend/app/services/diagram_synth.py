"""Deterministic diagram synthesis (offline, zero-cost).

When there is no LLM and no real source figure, we still want moving visuals -
not text cards. This module reads a section's narration and auto-builds a small
boxes-and-arrows graph (the same schema ``build_diagram`` consumes), so even the
free path produces animated diagrams.

Heuristic, fully offline:
- Pull candidate *entities* (the things being talked about): multi-word
  Capitalized phrases, known technical nouns, and otherwise the most frequent
  salient content words.
- Order them by first appearance and link them as a left-to-right *flow*,
  labeling each edge with a connecting verb found between the two entities when
  one is present (else a neutral arrow).
- Lay 2-6 nodes on the col(0-3) x row(0-2) grid and attach an icon concept per
  node via the icon library.

If fewer than two solid entities are found, returns ``None`` so the caller can
fall back to an icon / key-points scene instead of an empty canvas.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Optional

from app.services import icon_library

MAX_NODES = 6
MAX_LABEL_CHARS = 22

_STOP = {
    "the", "a", "an", "and", "or", "of", "in", "on", "to", "for", "with", "by",
    "is", "are", "be", "been", "being", "this", "that", "these", "those", "as",
    "it", "its", "from", "into", "at", "but", "not", "no", "yes", "have", "has",
    "had", "can", "will", "would", "may", "might", "should", "could", "must",
    "we", "you", "they", "i", "he", "she", "their", "your", "our", "via", "per",
    "if", "then", "than", "so", "such", "which", "what", "when", "where", "who",
    "how", "why", "all", "any", "each", "more", "most", "much", "many", "some",
    "one", "two", "also", "very", "just", "like", "about", "over", "up", "out",
    "do", "does", "did", "get", "gets", "use", "uses", "used", "using", "make",
    "makes", "made", "let", "lets", "every", "other", "between", "across", "data",
    "way", "ways", "thing", "things", "lot", "lots", "need", "needs", "want",
}

# Verbs/connectors that imply a relationship between two entities in a sentence.
_REL_VERBS = [
    "sends", "send", "stores", "store", "reads", "read", "writes", "write",
    "connects", "connect", "feeds", "feed", "powers", "power", "runs", "run",
    "manages", "manage", "controls", "control", "routes", "route", "links",
    "link", "talks", "talk", "calls", "call", "queries", "query", "serves",
    "serve", "drives", "drive", "supports", "support", "creates", "create",
    "builds", "build", "uses", "use", "becomes", "become", "enables", "enable",
    "replaces", "replace", "combines", "combine", "syncs", "sync", "flows",
    "flow", "maps", "map", "triggers", "trigger", "passes", "pass",
]


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.replace("\n", " ")) if s.strip()]


_LEAD_ARTICLES = {"the", "a", "an", "this", "that", "these", "those"}


def _short_label(phrase: str) -> str:
    phrase = re.sub(r"\s+", " ", phrase).strip(" ,.;:-")
    words = phrase.split()
    if words and words[0].lower() in _LEAD_ARTICLES:
        words = words[1:]
    if len(words) > 3:
        words = words[:3]
    label = " ".join(words)
    # Prefer dropping a word over an ugly mid-word ellipsis.
    while len(label) > MAX_LABEL_CHARS and len(words) > 1:
        words = words[:-1]
        label = " ".join(words)
    if len(label) > MAX_LABEL_CHARS:
        label = label[:MAX_LABEL_CHARS - 1].rstrip() + "\u2026"
    return label


def _entity_id(label: str, used: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:14] or "n"
    nid = base
    i = 2
    while nid in used:
        nid = f"{base}{i}"
        i += 1
    return nid


_VERB_FORMS = set(_REL_VERBS)


def _extract_entities(text: str) -> list[str]:
    """Return ordered, de-duplicated candidate entity phrases.

    Strong, named multi-word phrases are preferred; single frequent words only
    fill the graph when there aren't enough strong entities, so the result is a
    clean flow rather than a noisy word cloud.
    """
    ordered: list[str] = []
    seen: set[str] = set()

    def _add(phrase: str) -> bool:
        label = _short_label(phrase)
        key = label.lower()
        if not label or len(key) < 3 or key in _STOP or key in _VERB_FORMS:
            return False
        # Drop near-duplicates: if this label contains (or is contained by) an
        # already-accepted one, keep the longer, more specific phrase.
        for existing in list(seen):
            if key == existing or key in existing or existing in key:
                if len(key) > len(existing):
                    idx = next(i for i, e in enumerate(ordered) if e.lower() == existing)
                    ordered[idx] = label
                    seen.discard(existing)
                    seen.add(key)
                return False
        seen.add(key)
        ordered.append(label)
        return True

    # 1. Multi-word Capitalized phrases (proper nouns / named components) - strong.
    for m in re.finditer(r"\b([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+){1,2})\b", text):
        _add(m.group(1))
    strong = len(ordered)

    # 2. Only if we don't have a few strong entities, fill with frequent nouns.
    if strong < 3:
        words = re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", text.lower())
        freq = Counter(w for w in words if w not in _STOP and w not in _VERB_FORMS)
        for word, _count in freq.most_common(12):
            _add(word)
            if len(ordered) >= 4:
                break

    return ordered


def _relation_label(text: str, a: str, b: str) -> str:
    """Find a connecting verb between two entity mentions in the same sentence."""
    al, bl = a.lower(), b.lower()
    for sent in _sentences(text):
        sl = sent.lower()
        ia, ib = sl.find(al.split()[0]), sl.find(bl.split()[0])
        if ia == -1 or ib == -1:
            continue
        lo, hi = (ia, ib) if ia < ib else (ib, ia)
        between = sl[lo:hi]
        for v in _REL_VERBS:
            if re.search(rf"\b{re.escape(v)}\b", between):
                return v
    return ""


def _layout(n: int) -> list[tuple[int, int]]:
    """col(0-3) x row(0-2) positions for a left-to-right reading flow."""
    if n <= 3:
        return [(i, 1) for i in range(n)]
    if n == 4:
        return [(0, 0), (1, 0), (0, 1), (1, 1)]
    if n == 5:
        return [(0, 0), (1, 0), (2, 0), (0, 1), (1, 1)]
    return [(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)]


def synthesize_diagram(narration: str, title: str = "") -> Optional[dict]:
    """Build a {nodes, edges} graph from narration, or None if not enough signal.

    Output matches the schema validated by storyboard_llm/_validate_diagram and
    consumed by the build_diagram template.
    """
    text = f"{title}. {narration}".strip()
    # Entities come from the narration only (the title is a headline, not a node);
    # the full text is used when looking for the verb that connects two entities.
    entities = _extract_entities(narration)
    if len(entities) < 2:
        return None
    entities = entities[:MAX_NODES]

    positions = _layout(len(entities))
    nodes: list[dict] = []
    used_ids: set[str] = set()
    ids: list[str] = []
    for label, (col, row) in zip(entities, positions):
        nid = _entity_id(label, used_ids)
        used_ids.add(nid)
        ids.append(nid)
        icon = icon_library.best_concept_for_text(label, fallback=None, title=title)
        nodes.append({"id": nid, "label": label, "col": col, "row": row, "icon": icon})

    # Link as a flow in reading order; label edges with a verb when we find one.
    edges: list[dict] = []
    for i in range(len(entities) - 1):
        label = _relation_label(text, entities[i], entities[i + 1])
        edges.append({"from": ids[i], "to": ids[i + 1], "label": label})

    return {"nodes": nodes, "edges": edges}
