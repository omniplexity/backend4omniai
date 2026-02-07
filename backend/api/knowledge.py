"""Knowledge base API endpoints."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from backend.auth.dependencies import get_current_user
from backend.config import get_settings
from backend.db import get_db
from backend.db.models import KnowledgeChunk, KnowledgeDocument, User
from backend.services.embeddings_service import cosine_similarity, embed_texts

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


class KnowledgeDocResponse(BaseModel):
    id: str
    name: str
    mime_type: Optional[str]
    size: Optional[int]
    created_at: datetime
    chunks: Optional[int] = None

    class Config:
        from_attributes = True


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=20)


class KnowledgeSearchResult(BaseModel):
    doc_id: str
    doc_name: str
    chunk_id: str
    snippet: str
    score: Optional[int] = None


def chunk_text(text: str, size: int = 1000, overlap: int = 100) -> List[str]:
    if not text:
        return []
    chunks = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + size, length)
        chunks.append(text[start:end])
        if end >= length:
            break
        start = max(end - overlap, 0)
    return chunks


@router.get("", response_model=List[KnowledgeDocResponse])
async def list_documents(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    docs = (
        db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.user_id == current_user.id)
        .order_by(KnowledgeDocument.created_at.desc())
        .all()
    )
    results: List[KnowledgeDocResponse] = []
    for doc in docs:
        count = (
            db.query(KnowledgeChunk)
            .filter(KnowledgeChunk.doc_id == doc.id)
            .count()
        )
        results.append(
            KnowledgeDocResponse(
                id=doc.id,
                name=doc.name,
                mime_type=doc.mime_type,
                size=doc.size,
                created_at=doc.created_at,
                chunks=count,
            )
        )
    return results


@router.post("/upload", response_model=KnowledgeDocResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    http_request: Request = None,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file encoding")

    doc = KnowledgeDocument(
        user_id=current_user.id,
        name=file.filename or "document",
        mime_type=file.content_type,
        size=len(raw),
    )
    db.add(doc)
    db.flush()

    chunks = chunk_text(text)
    settings = get_settings()
    registry = getattr(http_request.app.state, "provider_registry", None) if http_request is not None else None
    vectors = None
    if settings.embeddings_enabled and registry is not None and chunks:
        vectors = await embed_texts(registry, chunks)

    for idx, chunk in enumerate(chunks):
        vec = None
        if vectors and idx < len(vectors):
            vec = vectors[idx]
        db.add(
            KnowledgeChunk(
                doc_id=doc.id,
                user_id=current_user.id,
                chunk_index=idx,
                content=chunk,
                embedding_model=(settings.embeddings_model or None) if vec else None,
                embedding_json=vec if vec else None,
            )
        )

    db.commit()
    db.refresh(doc)

    return KnowledgeDocResponse(
        id=doc.id,
        name=doc.name,
        mime_type=doc.mime_type,
        size=doc.size,
        created_at=doc.created_at,
        chunks=len(chunks),
    )


@router.post("/search", response_model=List[KnowledgeSearchResult])
async def search_documents(
    request: KnowledgeSearchRequest,
    http_request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = request.query.strip().lower()
    if not query:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Query required")

    settings = get_settings()
    if settings.embeddings_enabled:
        registry = getattr(http_request.app.state, "provider_registry", None)
        qvecs = await embed_texts(registry, [request.query])
        qvec = qvecs[0] if qvecs else None
        if qvec:
            rows = (
                db.query(KnowledgeChunk, KnowledgeDocument)
                .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.doc_id)
                .filter(KnowledgeChunk.user_id == current_user.id)
                .all()
            )
            scored: list[tuple[float, KnowledgeChunk, KnowledgeDocument]] = []
            for chunk, doc in rows:
                vec = chunk.embedding_json or None
                if isinstance(vec, list) and vec:
                    scored.append((cosine_similarity(qvec, vec), chunk, doc))
            scored.sort(key=lambda t: t[0], reverse=True)

            results: List[KnowledgeSearchResult] = []
            for score, chunk, doc in scored[: request.limit]:
                content = chunk.content or ""
                snippet = content[:200].strip()
                results.append(
                    KnowledgeSearchResult(
                        doc_id=doc.id,
                        doc_name=doc.name,
                        chunk_id=chunk.id,
                        snippet=snippet,
                        score=int(score * 1000),
                    )
                )
            return results

    chunks = (
        db.query(KnowledgeChunk, KnowledgeDocument)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.doc_id)
        .filter(KnowledgeChunk.user_id == current_user.id)
        .filter(KnowledgeChunk.content.ilike(f"%{query}%"))
        .limit(request.limit)
        .all()
    )

    results: List[KnowledgeSearchResult] = []
    for chunk, doc in chunks:
        content = chunk.content or ""
        idx = content.lower().find(query)
        start = max(idx - 80, 0) if idx >= 0 else 0
        end = min(start + 200, len(content))
        snippet = content[start:end].strip()
        results.append(
            KnowledgeSearchResult(
                doc_id=doc.id,
                doc_name=doc.name,
                chunk_id=chunk.id,
                snippet=snippet,
                score=None,
            )
        )
    return results


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: str,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = (
        db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.id == doc_id, KnowledgeDocument.user_id == current_user.id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    db.delete(doc)
    db.commit()
    return {"message": "Document deleted"}
