"""Memory API endpoints."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from backend.auth.dependencies import get_current_user
from backend.config import get_settings
from backend.db import get_db
from backend.db.models import MemoryEntry, User
from backend.services.embeddings_service import cosine_similarity, embed_texts

router = APIRouter(prefix="/api/memory", tags=["memory"])


class MemoryEntryResponse(BaseModel):
    id: str
    title: str
    content: str
    tags: Optional[list[str]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MemoryCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    tags: Optional[list[str]] = None


class MemoryUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    content: Optional[str] = Field(default=None, min_length=1)
    tags: Optional[list[str]] = None


class MemorySearchRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=50)


class MemorySearchResult(BaseModel):
    id: str
    title: str
    content: str
    score: float


@router.get("", response_model=List[MemoryEntryResponse])
async def list_memory(
    limit: int = 100,
    offset: int = 0,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entries = (
        db.query(MemoryEntry)
        .filter(MemoryEntry.user_id == current_user.id)
        .order_by(MemoryEntry.updated_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [MemoryEntryResponse.model_validate(entry) for entry in entries]


@router.post("", response_model=MemoryEntryResponse, status_code=status.HTTP_201_CREATED)
async def create_memory(
    request: MemoryCreateRequest,
    http_request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = MemoryEntry(
        user_id=current_user.id,
        title=request.title,
        content=request.content,
        tags=request.tags or [],
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    settings = get_settings()
    if settings.embeddings_enabled:
        registry = getattr(http_request.app.state, "provider_registry", None)
        text = f"{entry.title}\n{entry.content}"
        vecs = await embed_texts(registry, [text])
        if vecs and vecs[0]:
            entry.embedding_model = settings.embeddings_model or None
            entry.embedding_json = vecs[0]
            db.add(entry)
            db.commit()
            db.refresh(entry)

    return MemoryEntryResponse.model_validate(entry)


@router.patch("/{entry_id}", response_model=MemoryEntryResponse)
async def update_memory(
    entry_id: str,
    request: MemoryUpdateRequest,
    http_request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = (
        db.query(MemoryEntry)
        .filter(MemoryEntry.id == entry_id, MemoryEntry.user_id == current_user.id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory entry not found")

    if request.title is not None:
        entry.title = request.title
    if request.content is not None:
        entry.content = request.content
    if request.tags is not None:
        entry.tags = request.tags

    db.commit()
    db.refresh(entry)

    settings = get_settings()
    if settings.embeddings_enabled and (request.title is not None or request.content is not None):
        registry = getattr(http_request.app.state, "provider_registry", None)
        text = f"{entry.title}\n{entry.content}"
        vecs = await embed_texts(registry, [text])
        if vecs and vecs[0]:
            entry.embedding_model = settings.embeddings_model or None
            entry.embedding_json = vecs[0]
            db.add(entry)
            db.commit()
            db.refresh(entry)

    return MemoryEntryResponse.model_validate(entry)


@router.delete("/{entry_id}")
async def delete_memory(
    entry_id: str,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = (
        db.query(MemoryEntry)
        .filter(MemoryEntry.id == entry_id, MemoryEntry.user_id == current_user.id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory entry not found")

    db.delete(entry)
    db.commit()
    return {"message": "Memory entry deleted"}


@router.post("/search", response_model=List[MemorySearchResult])
async def search_memory(
    request: MemorySearchRequest,
    http_request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings = get_settings()
    query_text = request.query.strip()
    if not query_text:
        raise HTTPException(status_code=400, detail="Query required")

    # Prefer semantic search when embeddings are enabled and available.
    results: list[MemorySearchResult] = []
    if settings.embeddings_enabled:
        registry = getattr(http_request.app.state, "provider_registry", None)
        qvecs = await embed_texts(registry, [query_text])
        qvec = qvecs[0] if qvecs else None
        if qvec:
            entries = (
                db.query(MemoryEntry)
                .filter(MemoryEntry.user_id == current_user.id)
                .all()
            )
            scored: list[tuple[float, MemoryEntry]] = []
            for e in entries:
                vec = e.embedding_json or None
                if isinstance(vec, list) and vec:
                    score = cosine_similarity(qvec, vec)
                    scored.append((score, e))
            scored.sort(key=lambda t: t[0], reverse=True)
            for score, e in scored[: request.limit]:
                results.append(
                    MemorySearchResult(
                        id=e.id,
                        title=e.title,
                        content=e.content,
                        score=float(score),
                    )
                )
            return results

    # Fallback: substring search.
    q = query_text.lower()
    entries = (
        db.query(MemoryEntry)
        .filter(MemoryEntry.user_id == current_user.id)
        .filter(
            (MemoryEntry.title.ilike(f"%{q}%"))
            | (MemoryEntry.content.ilike(f"%{q}%"))
        )
        .limit(request.limit)
        .all()
    )
    for e in entries:
        results.append(MemorySearchResult(id=e.id, title=e.title, content=e.content, score=0.0))
    return results
