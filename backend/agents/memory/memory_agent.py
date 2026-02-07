"""Memory Agent.

Manages long-term user memories and semantic search.
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session as DBSession

from backend.db.models import User, MemoryEntry
from backend.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MemoryEntryInfo:
    """Memory entry information."""
    id: str
    title: str
    content: str
    tags: Optional[List[str]]
    created_at: datetime
    updated_at: datetime


class MemoryAgent:
    """Agent for managing user memories."""

    def __init__(self, db: DBSession):
        """Initialize the Memory Agent.
        
        Args:
            db: Database session
        """
        self.db = db

    def create_memory(
        self,
        user: User,
        title: str,
        content: str,
        tags: Optional[List[str]] = None,
    ) -> MemoryEntry:
        """Create a new memory entry.
        
        Args:
            user: User creating the memory
            title: Memory title
            content: Memory content
            tags: Optional tags
            
        Returns:
            Created MemoryEntry
        """
        entry = MemoryEntry(
            user_id=user.id,
            title=title,
            content=content,
            tags=tags,
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        
        logger.info(f"Created memory {entry.id} for user {user.id}")
        return entry

    def get_memory(self, memory_id: str, user: User) -> Optional[MemoryEntry]:
        """Get a memory entry by ID.
        
        Args:
            memory_id: Memory ID
            user: User requesting the memory
            
        Returns:
            MemoryEntry if found, None otherwise
        """
        return (
            self.db.query(MemoryEntry)
            .filter(MemoryEntry.id == memory_id, MemoryEntry.user_id == user.id)
            .first()
        )

    def list_memories(
        self,
        user: User,
        limit: int = 100,
        offset: int = 0,
    ) -> List[MemoryEntry]:
        """List user's memory entries.
        
        Args:
            user: User to list memories for
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of MemoryEntry objects
        """
        return (
            self.db.query(MemoryEntry)
            .filter(MemoryEntry.user_id == user.id)
            .order_by(MemoryEntry.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def update_memory(
        self,
        entry: MemoryEntry,
        title: Optional[str] = None,
        content: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> MemoryEntry:
        """Update a memory entry.
        
        Args:
            entry: Entry to update
            title: New title
            content: New content
            tags: New tags
            
        Returns:
            Updated MemoryEntry
        """
        if title is not None:
            entry.title = title
        if content is not None:
            entry.content = content
        if tags is not None:
            entry.tags = tags
            
        self.db.commit()
        self.db.refresh(entry)
        
        return entry

    def delete_memory(self, entry: MemoryEntry) -> None:
        """Delete a memory entry.
        
        Args:
            entry: Entry to delete
        """
        self.db.delete(entry)
        self.db.commit()
        logger.info(f"Deleted memory {entry.id}")

    def search_memories(
        self,
        user: User,
        query: str,
        limit: int = 20,
    ) -> List[MemoryEntry]:
        """Search memories by content.
        
        Args:
            user: User to search for
            query: Search query
            limit: Maximum results
            
        Returns:
            List of matching MemoryEntry objects
        """
        # Simple ILIKE search for now
        # Can be upgraded to semantic search with embeddings
        search_pattern = f"%{query}%"
        return (
            self.db.query(MemoryEntry)
            .filter(
                MemoryEntry.user_id == user.id,
            )
            .filter(
                (MemoryEntry.title.ilike(search_pattern)) |
                (MemoryEntry.content.ilike(search_pattern))
            )
            .order_by(MemoryEntry.updated_at.desc())
            .limit(limit)
            .all()
        )
