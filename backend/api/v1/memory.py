"""v1 memory endpoints.

Exposes Memory Agent interfaces for memory management.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from backend.auth.dependencies import get_current_user
from backend.config import get_settings
from backend.db import get_db
from backend.db.models import User, MemoryEntry
from backend.agents.memory import MemoryAgent

router = APIRouter(prefix="/memory", tags=["v1-memory"])


class MemoryEntryResponse(BaseModel):
    """Memory entry response."""
    id: str
    title: str
    content: str
    tags: Optional[List[str]] = None
    created_at: str
    updated_at: str


class MemoryCreateRequest(BaseModel):
    """Create memory request."""
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    tags: Optional[List[str]] = None


class MemoryUpdateRequest(BaseModel):
    """Update memory request."""
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    content: Optional[str] = Field(default=None, min_length=1)
    tags: Optional[List[str]] = None


class MemorySearchResult(BaseModel):
    """Memory search result."""
    id: str
    title: str
    content: str
    score: float = 0.0
    tags: Optional[List[str]] = None
    created_at: str


class MemorySearchRequest(BaseModel):
    """Search memory request."""
    query: str = Field(min_length=1)
    limit: int = Field(default=20, ge=1, le=100)


def _create_memory_agent(db: DBSession) -> MemoryAgent:
    """Create a Memory Agent instance."""
    return MemoryAgent(db)


@router.get("", response_model=List[MemoryEntryResponse])
async def list_memories(
    limit: int = 100,
    offset: int = 0,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[MemoryEntryResponse]:
    """List user's memory entries."""
    agent = _create_memory_agent(db)
    entries = agent.list_memories(current_user, limit, offset)
    
    return [
        MemoryEntryResponse(
            id=entry.id,
            title=entry.title,
            content=entry.content,
            tags=entry.tags,
            created_at=entry.created_at.isoformat(),
            updated_at=entry.updated_at.isoformat(),
        )
        for entry in entries
    ]


@router.post("", response_model=MemoryEntryResponse, status_code=status.HTTP_201_CREATED)
async def create_memory(
    body: MemoryCreateRequest,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MemoryEntryResponse:
    """Create a new memory entry."""
    agent = _create_memory_agent(db)
    
    entry = agent.create_memory(
        user=current_user,
        title=body.title,
        content=body.content,
        tags=body.tags,
    )
    
    return MemoryEntryResponse(
        id=entry.id,
        title=entry.title,
        content=entry.content,
        tags=entry.tags,
        created_at=entry.created_at.isoformat(),
        updated_at=entry.updated_at.isoformat(),
    )


@router.get("/{memory_id}", response_model=MemoryEntryResponse)
async def get_memory(
    memory_id: str,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MemoryEntryResponse:
    """Get a memory entry by ID."""
    agent = _create_memory_agent(db)
    
    entry = agent.get_memory(memory_id, current_user)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory entry not found",
        )
    
    return MemoryEntryResponse(
        id=entry.id,
        title=entry.title,
        content=entry.content,
        tags=entry.tags,
        created_at=entry.created_at.isoformat(),
        updated_at=entry.updated_at.isoformat(),
    )


@router.patch("/{memory_id}", response_model=MemoryEntryResponse)
async def update_memory(
    memory_id: str,
    body: MemoryUpdateRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MemoryEntryResponse:
    """Update a memory entry."""
    agent = _create_memory_agent(db)
    
    entry = agent.get_memory(memory_id, current_user)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory entry not found",
        )
    
    entry = agent.update_memory(
        entry,
        title=body.title,
        content=body.content,
        tags=body.tags,
    )
    
    return MemoryEntryResponse(
        id=entry.id,
        title=entry.title,
        content=entry.content,
        tags=entry.tags,
        created_at=entry.created_at.isoformat(),
        updated_at=entry.updated_at.isoformat(),
    )


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Delete a memory entry."""
    agent = _create_memory_agent(db)
    
    entry = agent.get_memory(memory_id, current_user)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory entry not found",
        )
    
    agent.delete_memory(entry)
    
    return {"status": "deleted", "id": memory_id}


@router.post("/search", response_model=List[MemorySearchResult])
async def search_memories(
    body: MemorySearchRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[MemorySearchResult]:
    """Search memories by content."""
    agent = _create_memory_agent(db)
    
    entries = agent.search_memories(
        user=current_user,
        query=body.query,
        limit=body.limit,
    )
    
    return [
        MemorySearchResult(
            id=entry.id,
            title=entry.title,
            content=entry.content,
            score=0.0,  # Would need semantic search for real scores
            tags=entry.tags,
            created_at=entry.created_at.isoformat(),
        )
        for entry in entries
    ]
