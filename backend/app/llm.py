"""
Shared LLM helper used by the simplifier and the NuggetBot chat.

Provider order:
  1. Groq (free Llama-3, OpenAI-compatible) when GROQ_API_KEY is set.
  2. Ollama for local development (LLM_PROVIDER=ollama).
  3. None -> callers fall back to a deterministic, zero-cost path.

The API key lives server-side only and is never returned to the client.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from app import config

logger = logging.getLogger(__name__)


def llm_available() -> bool:
    if config.GROQ_API_KEY:
        return True
    return config.LLM_PROVIDER == "ollama"


async def chat(
    messages: list[dict],
    *,
    max_tokens: int = 600,
    temperature: float = 0.7,
) -> Optional[str]:
    """Return assistant text, or None if no provider is configured / it failed."""
    # 1. Groq (preferred, free).
    if config.GROQ_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    config.GROQ_URL,
                    headers={
                        "Authorization": f"Bearer {config.GROQ_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": config.GROQ_MODEL,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    },
                )
            if resp.status_code != 200:
                logger.warning("Groq upstream %s: %s", resp.status_code, resp.text[:300])
                return None
            data = resp.json()
            return (data["choices"][0]["message"]["content"] or "").strip()
        except Exception as exc:  # never break the pipeline
            logger.warning("Groq call failed: %s", exc)
            return None

    # 2. Ollama (local dev).
    if config.LLM_PROVIDER == "ollama":
        try:
            import ollama

            client = ollama.AsyncClient(host=config.OLLAMA_BASE_URL, timeout=httpx.Timeout(120.0))
            resp = await client.chat(
                model=config.OLLAMA_MODEL,
                messages=messages,
                options={"temperature": temperature, "num_predict": max_tokens},
            )
            return (resp["message"]["content"] or "").strip()
        except Exception as exc:
            logger.warning("Ollama call failed: %s", exc)
            return None

    # 3. No provider.
    return None
