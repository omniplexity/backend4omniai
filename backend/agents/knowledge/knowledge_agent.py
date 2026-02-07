"""Knowledge Agent.

Manages knowledge documents and search.
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session as DBSession

from backend.db.models import User, KnowledgeDocument, KnowledgeChunk
from backend.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DocumentInfo:
    """Knowledge document information."""
    id: str
    name: str
    mime_type: Optional[str]
    size: Optional[int]
    created_at: datetime
    chunk_count: int


@dataclass
class ChunkInfo:
    """Knowledge chunk information."""
    id: str
    doc_id: str
    chunk_index: int
    content: str
    created_at: datetime


class KnowledgeAgent:
    """Agent for managing knowledge documents."""

    def __init__(self, db: DBSession):
        """Initialize the Knowledge Agent.
        
        Args:
            db: Database session
        """
        self.db = db

    def create_document(
        self,
        user: User,
        name: str,
        mime_type: Optional[str] = None,
        size: Optional[int] = None,
    ) -> KnowledgeDocument:
        """Create a new knowledge document.
        
        Args:
            user: User creating the document
            name: Document name
            mime_type: MIME type
            size: Document size in bytes
            
        Returns:
            Created KnowledgeDocument
        """
        doc = KnowledgeDocument(
            user_id=user.id,
            name=name,
            mime_type=mime_type,
            size=size,
        )
        self.db.add(doc)
        self.db.commit()
        self.db.refresh(doc)
        
        logger.info(f"Created document {doc.id} for user {user.id}")
        return doc

    def get_document(self, doc_id: str, user: User) -> Optional[KnowledgeDocument]:
        """Get a document by ID.
        
        Args:
            doc_id: Document ID
            user: User requesting the document
            
        Returns:
            KnowledgeDocument if found, None otherwise
        """
        return (
            self.db.query(KnowledgeDocument)
            .filter(KnowledgeDocument.id == doc_id, KnowledgeDocument.user_id == user.id)
            .first()
        )

    def list_documents(
        self,
        user: User,
        limit: int = 100,
        offset: int = 0,
    ) -> List[KnowledgeDocument]:
        """List user's knowledge documents.
        
        Args:
            user: User to list documents for
            limit: Maximum results
            offset: Offset for pagination
            
        Returns:
            List of KnowledgeDocument objects
        """
        return (
            self.db.query(KnowledgeDocument)
            .filter(KnowledgeDocument.user_id == user.id)
            .order_by(KnowledgeDocument.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def delete_document(self, doc: KnowledgeDocument) -> None:
        """Delete a document and its chunks.
        
        Args:
            doc: Document to delete
        """
        self.db.delete(doc)
        self.db.commit()
        logger.info(f"Deleted document {doc.id}")

    def create_chunk(
        self,
        doc_id: str,
        user_id: str,
        chunk_index: int,
        content: str,
    ) -> KnowledgeChunk:
        """Create a document chunk.
        
        Args:
            doc_id: Parent document ID
            user_id: User ID
            chunk_index: Chunk position
            content: Chunk content
            
        Returns:
            Created KnowledgeChunk
        """
        chunk = KnowledgeChunk(
            doc_id=doc_id,
            user_id=user_id,
            chunk_index=chunk_index,
            content=content,
        )
        self.db.add(chunk)
        self.db.commit()
        self.db.refresh(chunk)
        
        return chunk

    def get_chunks(self, doc_id: str) -> List[KnowledgeChunk]:
        """Get all chunks for a document.
        
        Args:
            doc_id: Document ID
            
        Returns:
            List of KnowledgeChunk objects
        """
        return (
            self.db.query(KnowledgeChunk)
            .filter(KnowledgeChunk.doc_id == doc_id)
            .order_by(KnowledgeChunk.chunk_index.asc())
            .all()
        )

    def search(
        self,
        user: User,
        query: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Search knowledge documents.
        
        Args:
            user: User to search for
            query: Search query
            limit: Maximum results
            
        Returns:
            List of matching chunks with document info
        """
        search_pattern = f"%{query}%"
        results = (
            self.db.query(KnowledgeChunk)
            .join(KnowledgeDocument)
            .filter(
                KnowledgeDocument.user_id == user.id,
                KnowledgeChunk.content.ilike(search_pattern),
            )
            .order_by(KnowledgeChunk.created_at.desc())
            .limit(limit)
            .all()
        )
        
        return [
            {
                "chunk_id": chunk.id,
                "doc_id": chunk.doc_id,
                "doc_name": chunk.doc.name if chunk.doc else None,
                "content": chunk.content[:200] + "..." if len(chunk.content) > 200 else chunk.content,
                "chunk_index": chunk.chunk_index,
            }
            for chunk in results
        ]
