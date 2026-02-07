"""Retrieval helpers for memory + knowledge (RAG context).

This is a lightweight first pass:
- Uses stored embeddings when enabled (best-effort).
- Falls back to substring search when embeddings are disabled/unavailable.
- Returns context items that can be injected into the model prompt with stable
  cite labels like [S1], [S2], ...
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session as DBSession

from backend.config import get_settings
from backend.db.models import KnowledgeChunk, KnowledgeDocument, MemoryEntry, User
from backend.services.embeddings_service import cosine_similarity, embed_texts


@dataclass(frozen=True)
class ContextSource:
    label: str
    source_type: str  # "memory" | "knowledge"
    score: float
    title: str
    snippet: str
    meta: dict[str, Any]


def _truncate(s: str, n: int) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[: n - 1].rstrip() + "…"


def extract_citation_labels(text: str) -> list[str]:
    """Extract citation labels like [S1] in order of first appearance."""
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for m in re.finditer(r"\[(S\d+)\]", text):
        label = m.group(1)
        if label not in seen:
            seen.add(label)
            out.append(label)
    return out


def build_rag_context_message(sources: list[ContextSource]) -> str:
    """Build a system message containing sources and citation instructions."""
    if not sources:
        return ""

    lines: list[str] = []
    lines.append("Context sources (use when relevant):")
    for src in sources:
        lines.append(f"[{src.label}] {src.source_type.upper()}: {src.title}")
        if src.snippet:
            lines.append(src.snippet)
        lines.append("")  # separator
    lines.append("Instructions:")
    lines.append("1. Use these sources when they help answer the user.")
    lines.append("2. When you use a source, cite it inline as [S#] (example: [S1]).")
    lines.append("3. Do not invent citations; only cite provided sources.")
    return "\n".join(lines).strip()


async def retrieve_context(
    *,
    db: DBSession,
    user: User,
    registry: Any | None,
    query: str,
    limit_memory: int = 3,
    limit_knowledge: int = 5,
) -> list[ContextSource]:
    """Retrieve relevant memory + knowledge sources for a user query."""
    q = (query or "").strip()
    if not q:
        return []

    settings = get_settings()
    sources: list[ContextSource] = []

    # Try semantic retrieval when enabled and query embedding is available.
    qvec = None
    if settings.embeddings_enabled:
        qvecs = await embed_texts(registry, [q])
        if qvecs and qvecs[0]:
            qvec = qvecs[0]

    if qvec:
        # Memory
        mem_entries = db.query(MemoryEntry).filter(MemoryEntry.user_id == user.id).all()
        mem_scored: list[tuple[float, MemoryEntry]] = []
        for e in mem_entries:
            vec = e.embedding_json
            if isinstance(vec, list) and vec:
                mem_scored.append((cosine_similarity(qvec, vec), e))
        mem_scored.sort(key=lambda t: t[0], reverse=True)

        # Knowledge
        kn_rows = (
            db.query(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.doc_id)
            .filter(KnowledgeChunk.user_id == user.id)
            .all()
        )
        kn_scored: list[tuple[float, KnowledgeChunk, KnowledgeDocument]] = []
        for chunk, doc in kn_rows:
            vec = chunk.embedding_json
            if isinstance(vec, list) and vec:
                kn_scored.append((cosine_similarity(qvec, vec), chunk, doc))
        kn_scored.sort(key=lambda t: t[0], reverse=True)

        # Combine into a single list and label.
        combined: list[tuple[float, ContextSource]] = []
        for score, e in mem_scored[: max(0, limit_memory)]:
            combined.append(
                (
                    score,
                    ContextSource(
                        label="",  # assigned below
                        source_type="memory",
                        score=float(score),
                        title=_truncate(e.title or "Memory", 80),
                        snippet=_truncate(e.content or "", 600),
                        meta={"memory_entry_id": e.id},
                    ),
                )
            )
        for score, chunk, doc in kn_scored[: max(0, limit_knowledge)]:
            combined.append(
                (
                    score,
                    ContextSource(
                        label="",
                        source_type="knowledge",
                        score=float(score),
                        title=_truncate(doc.name or "Document", 80),
                        snippet=_truncate(chunk.content or "", 600),
                        meta={
                            "doc_id": doc.id,
                            "doc_name": doc.name,
                            "chunk_id": chunk.id,
                            "chunk_index": chunk.chunk_index,
                        },
                    ),
                )
            )

        combined.sort(key=lambda t: t[0], reverse=True)
        pruned = [src for _score, src in combined if src.score > 0.0][: (limit_memory + limit_knowledge)]
        for i, src in enumerate(pruned, start=1):
            sources.append(
                ContextSource(
                    label=f"S{i}",
                    source_type=src.source_type,
                    score=src.score,
                    title=src.title,
                    snippet=src.snippet,
                    meta=src.meta,
                )
            )
        return sources

    # Fallback: substring retrieval (simple + predictable).
    needle = q.lower()

    mem_hits = (
        db.query(MemoryEntry)
        .filter(MemoryEntry.user_id == user.id)
        .filter((MemoryEntry.title.ilike(f"%{needle}%")) | (MemoryEntry.content.ilike(f"%{needle}%")))
        .limit(max(0, limit_memory))
        .all()
    )

    kn_hits = (
        db.query(KnowledgeChunk, KnowledgeDocument)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.doc_id)
        .filter(KnowledgeChunk.user_id == user.id)
        .filter(KnowledgeChunk.content.ilike(f"%{needle}%"))
        .limit(max(0, limit_knowledge))
        .all()
    )

    idx = 1
    for e in mem_hits:
        sources.append(
            ContextSource(
                label=f"S{idx}",
                source_type="memory",
                score=0.0,
                title=_truncate(e.title or "Memory", 80),
                snippet=_truncate(e.content or "", 600),
                meta={"memory_entry_id": e.id},
            )
        )
        idx += 1

    for chunk, doc in kn_hits:
        sources.append(
            ContextSource(
                label=f"S{idx}",
                source_type="knowledge",
                score=0.0,
                title=_truncate(doc.name or "Document", 80),
                snippet=_truncate(chunk.content or "", 600),
                meta={
                    "doc_id": doc.id,
                    "doc_name": doc.name,
                    "chunk_id": chunk.id,
                    "chunk_index": chunk.chunk_index,
                },
            )
        )
        idx += 1

    return sources

