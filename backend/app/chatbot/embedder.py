"""
Content chunking and embedding service for the RAG knowledge base.
Indexes video transcripts, parsed content, and Bible sections into ChromaDB.
"""
import hashlib
from typing import Optional

import chromadb
from chromadb.config import Settings

from app.config import CHROMA_DIR, EMBEDDING_MODEL, CHUNK_SIZE, CHUNK_OVERLAP
from app.services.content_parser import ParsedContent

_client: Optional[chromadb.ClientAPI] = None
_collection = None


def get_chroma_client():
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return _client


def get_collection():
    global _collection
    if _collection is None:
        client = get_chroma_client()
        _collection = client.get_or_create_collection(
            name="video_nuggets_knowledge",
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


async def index_video_content(
    video_id: int,
    content: ParsedContent,
    audio_segments: list[dict],
):
    """Index video content into the vector store for RAG retrieval."""
    collection = get_collection()

    documents = []
    metadatas = []
    ids = []

    for i, section in enumerate(content.sections):
        chunks = _chunk_text(section.body, CHUNK_SIZE, CHUNK_OVERLAP)
        for j, chunk in enumerate(chunks):
            doc_id = f"video_{video_id}_section_{i}_chunk_{j}"
            documents.append(chunk)
            metadatas.append({
                "video_id": str(video_id),
                "section_title": section.title,
                "section_key": section.key,
                "chunk_index": j,
                "source_type": content.source_type,
            })
            ids.append(doc_id)

    for segment in audio_segments:
        if segment["text"] and segment["type"] == "section":
            doc_id = f"video_{video_id}_narration_{segment['section_index']}"
            documents.append(segment["text"])
            metadatas.append({
                "video_id": str(video_id),
                "type": "narration",
                "section_index": str(segment["section_index"]),
            })
            ids.append(doc_id)

    if documents:
        batch_size = 100
        for i in range(0, len(documents), batch_size):
            batch_docs = documents[i:i + batch_size]
            batch_meta = metadatas[i:i + batch_size]
            batch_ids = ids[i:i + batch_size]
            collection.upsert(
                documents=batch_docs,
                metadatas=batch_meta,
                ids=batch_ids,
            )


async def index_raw_text(text: str, source_key: str, title: str):
    """Index raw text content (e.g., from Bible scraping) into vector store."""
    collection = get_collection()
    chunks = _chunk_text(text, CHUNK_SIZE, CHUNK_OVERLAP)

    documents = []
    metadatas = []
    ids = []

    for i, chunk in enumerate(chunks):
        doc_id = f"raw_{source_key}_chunk_{i}"
        documents.append(chunk)
        metadatas.append({
            "source_key": source_key,
            "title": title,
            "chunk_index": i,
            "source_type": "bible",
        })
        ids.append(doc_id)

    if documents:
        collection.upsert(documents=documents, metadatas=metadatas, ids=ids)


def search_knowledge(query: str, n_results: int = 5) -> list[dict]:
    """Search the knowledge base for relevant content."""
    collection = get_collection()

    try:
        results = collection.query(
            query_texts=[query],
            n_results=n_results,
        )
    except Exception:
        return []

    if not results or not results["documents"]:
        return []

    retrieved = []
    for i, doc in enumerate(results["documents"][0]):
        metadata = results["metadatas"][0][i] if results["metadatas"] else {}
        distance = results["distances"][0][i] if results["distances"] else 0
        retrieved.append({
            "content": doc,
            "metadata": metadata,
            "relevance": 1 - distance,
        })

    return retrieved


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split text into overlapping chunks."""
    if not text:
        return []

    words = text.split()
    if len(words) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start = end - overlap

    return chunks
