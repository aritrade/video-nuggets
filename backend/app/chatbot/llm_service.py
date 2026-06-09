"""
NuggetBot chat service.

Uses an LLM (Groq Llama-3 by default, Ollama for local dev) grounded in the
RAG context; when no LLM is configured it falls back to a deterministic
retrieval answer synthesized from the indexed nugget content, so chat always
works at zero cost.
"""
import json
import re
from typing import Optional

from sqlalchemy.orm import Session

from app import llm
from app.chatbot.prompts import format_system_prompt, SUGGESTION_PROMPT
from app.chatbot.memory import get_or_create_session, save_message
from app.chatbot.embedder import search_knowledge

_DEFAULT_SUGGESTIONS = [
    "How does this work under the hood?",
    "What are the key benefits?",
    "Can you give me a real-world analogy?",
]


async def get_chat_response(
    message: str,
    session_id: Optional[str],
    db: Session,
) -> dict:
    """Generate a chatbot response with RAG context and conversation memory."""
    session_id, history = get_or_create_session(db, session_id)

    relevant_docs = search_knowledge(message, n_results=3)
    context = _format_context(relevant_docs)

    assistant_message = None
    if llm.llm_available():
        system_prompt = format_system_prompt(context)
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history[-4:])
        messages.append({"role": "user", "content": message})
        assistant_message = await llm.chat(messages, max_tokens=700)

    if not assistant_message:
        assistant_message = _deterministic_answer(message, relevant_docs)

    cited_videos = _extract_cited_videos(relevant_docs)

    save_message(db, session_id, "user", message)
    save_message(db, session_id, "assistant", assistant_message, json.dumps(cited_videos))

    suggestions = await _generate_suggestions(message, assistant_message)

    return {
        "response": assistant_message,
        "session_id": session_id,
        "cited_videos": cited_videos,
        "suggestions": suggestions,
    }


def _deterministic_answer(message: str, docs: list[dict]) -> str:
    """Synthesize an answer from the retrieved nugget content (no LLM)."""
    if not docs:
        return (
            "That doesn't seem to be covered in the current video library yet. "
            "Try asking about one of the topics in the lessons on the left."
        )
    top = docs[0]
    content = top.get("content", "")
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", content) if s.strip()]
    qtokens = set(re.findall(r"[a-z0-9]+", message.lower()))
    ranked = sorted(
        sentences,
        key=lambda s: len(qtokens & set(re.findall(r"[a-z0-9]+", s.lower()))),
        reverse=True,
    )
    answer = " ".join(ranked[:3]) if ranked else content[:400]
    title = top["metadata"].get("section_title", top["metadata"].get("title", ""))
    if title:
        answer += f"\n\n[Video: {title}]"
    return answer


def _format_context(docs: list[dict]) -> str:
    if not docs:
        return "No specific context available."
    parts = ["RELEVANT KNOWLEDGE BASE CONTEXT:"]
    for i, doc in enumerate(docs, 1):
        title = doc["metadata"].get("section_title", doc["metadata"].get("title", "Unknown"))
        parts.append(f"\n--- Source {i}: {title} ---")
        parts.append(doc["content"])
    return "\n".join(parts)


def _extract_cited_videos(docs: list[dict]) -> list[dict]:
    cited = {}
    for doc in docs:
        video_id = doc["metadata"].get("video_id")
        if video_id and video_id not in cited:
            cited[video_id] = {
                "video_id": int(video_id) if str(video_id).isdigit() else None,
                "title": doc["metadata"].get("section_title", "Related Video"),
                "relevance": doc.get("relevance", 0),
            }
    return list(cited.values())[:3]


async def _generate_suggestions(user_message: str, assistant_response: str) -> list[str]:
    if not assistant_response or not llm.llm_available():
        return _DEFAULT_SUGGESTIONS
    prompt = f"Previous Q: {user_message}\nPrevious A: {assistant_response[:300]}\n\n{SUGGESTION_PROMPT}"
    text = await llm.chat([{"role": "user", "content": prompt}], max_tokens=200, temperature=0.8)
    if not text:
        return _DEFAULT_SUGGESTIONS
    lines = [s.strip().lstrip("0123456789.-) ") for s in text.strip().split("\n") if s.strip()]
    return lines[:3] or _DEFAULT_SUGGESTIONS
