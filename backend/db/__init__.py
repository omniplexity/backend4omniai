"""Database module for OmniAI backend."""

from backend.db.database import (
    Base,
    dispose_engine,
    get_db,
    get_engine,
    verify_database_connection,
)
from backend.db.models import (
    Artifact,
    AuditLog,
    ChatPreset,
    ChatRun,
    ChatRunEvent,
    ContextBlock,
    Conversation,
    InviteCode,
    KnowledgeChunk,
    KnowledgeDocument,
    MediaAsset,
    MediaJob,
    MemoryEntry,
    Message,
    Project,
    Session,
    ToolFavorite,
    ToolReceipt,
    ToolSetting,
    User,
)

__all__ = [
    # Database infrastructure
    "Base",
    "get_db",
    "get_engine",
    "dispose_engine",
    "verify_database_connection",
    # Core entities
    "User",
    "Session",
    "InviteCode",
    "AuditLog",
    # Chat entities
    "Conversation",
    "Message",
    "ChatPreset",
    "ChatRun",
    "ChatRunEvent",
    # Memory & Knowledge
    "MemoryEntry",
    "KnowledgeDocument",
    "KnowledgeChunk",
    # Tools
    "ToolReceipt",
    "ToolFavorite",
    "ToolSetting",
    # Media
    "MediaAsset",
    "MediaJob",
    # Projects & Context
    "Project",
    "ContextBlock",
    "Artifact",
]
