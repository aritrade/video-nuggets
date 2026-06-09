"""
LLM-backed "what changed" summarizer for the Cloud Bible monitor.

Given the previous and current website snapshots for a single section, returns
a 1-2 sentence human-readable summary of what changed. Best-effort: if Ollama
is unreachable or errors, returns None so the caller can fall back to the raw
unified diff.
"""
from __future__ import annotations

import logging
from typing import Optional

import ollama

from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL

logger = logging.getLogger(__name__)

# Each side is trimmed before sending to the LLM. The prompt itself is small,
# so ~3000 chars per side keeps total context comfortably under typical Ollama
# context windows while still giving the model enough signal.
_MAX_CHARS_PER_SIDE = 3000

_PROMPT_TEMPLATE = """You are reviewing a documentation update to nutanixbible.com.

Compare the two versions of the section titled "{title}" below and describe in
ONE OR TWO short sentences what changed. Focus on factual content (added,
removed, reworded, renamed, reordered). Ignore whitespace-only differences.
Do not quote large blocks of text. Do not list line numbers. Respond with the
summary only, no preamble.

PREVIOUS VERSION:
{old_text}

CURRENT VERSION:
{new_text}
"""


def _trim(text: str, limit: int = _MAX_CHARS_PER_SIDE) -> str:
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-limit // 2 :]
    return f"{head}\n...[trimmed {len(text) - limit} chars]...\n{tail}"


async def summarize_change(
    title: str, old_text: str, new_text: str
) -> Optional[str]:
    """Return a 1-2 sentence summary of the change, or None on failure."""
    if not (old_text or "").strip() and not (new_text or "").strip():
        return None

    prompt = _PROMPT_TEMPLATE.format(
        title=title,
        old_text=_trim(old_text or ""),
        new_text=_trim(new_text or ""),
    )

    try:
        client = ollama.AsyncClient(host=OLLAMA_BASE_URL)
        response = await client.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.2, "num_predict": 160},
        )
        summary = (response.get("message", {}) or {}).get("content", "").strip()
        return summary or None
    except Exception as exc:  # noqa: BLE001
        logger.warning("change_summarizer: LLM call failed for '%s': %s", title, exc)
        return None
