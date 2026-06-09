"""
RAG engine that coordinates retrieval-augmented generation.
Provides high-level interface for chatbot to query the knowledge base.
"""
from app.chatbot.embedder import search_knowledge, index_raw_text, get_collection


async def query_with_reasoning(question: str, n_results: int = 5) -> dict:
    """Query the knowledge base with relevance scoring and source tracking."""
    results = search_knowledge(question, n_results=n_results)

    if not results:
        return {
            "context": "",
            "sources": [],
            "confidence": 0.0,
        }

    avg_relevance = sum(r["relevance"] for r in results) / len(results)

    sources = []
    context_parts = []
    for r in results:
        if r["relevance"] > 0.3:
            context_parts.append(r["content"])
            sources.append({
                "title": r["metadata"].get("section_title", r["metadata"].get("title", "")),
                "video_id": r["metadata"].get("video_id"),
                "relevance": r["relevance"],
            })

    return {
        "context": "\n\n".join(context_parts),
        "sources": sources,
        "confidence": avg_relevance,
    }


async def refresh_index_for_section(section_key: str, content: str, title: str):
    """Refresh the vector index for a specific content section (called on updates)."""
    collection = get_collection()

    existing = collection.get(where={"source_key": section_key})
    if existing and existing["ids"]:
        collection.delete(ids=existing["ids"])

    await index_raw_text(content, section_key, title)


def get_knowledge_stats() -> dict:
    """Get statistics about the knowledge base."""
    collection = get_collection()
    count = collection.count()
    return {
        "total_chunks": count,
        "collection_name": "video_nuggets_knowledge",
    }
