"""SQLAlchemy database models."""

import secrets
from typing import List, Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, JSON, UniqueConstraint, Index
from sqlalchemy.orm import relationship

from backend.db.database import Base
from backend.core.time import utcnow


def generate_id() -> str:
    """Generate a unique ID."""
    return secrets.token_urlsafe(16)


class User(Base):
    """User account model."""

    __tablename__ = "users"

    id = Column(String(32), primary_key=True, default=generate_id)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(64), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    # Relationships
    conversations: List["Conversation"] = relationship(
        "Conversation", back_populates="user", cascade="all, delete-orphan"
    )
    projects: List["Project"] = relationship(
        "Project", back_populates="user", cascade="all, delete-orphan"
    )
    sessions: List["Session"] = relationship(
        "Session", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User {self.username}>"


class Session(Base):
    """User session model for authentication."""

    __tablename__ = "sessions"

    id = Column(String(32), primary_key=True, default=generate_id)
    user_id = Column(String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(255), nullable=False, unique=True, index=True)
    csrf_token = Column(String(64), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    # Relationships
    user: User = relationship("User", back_populates="sessions")

    def __repr__(self) -> str:
        return f"<Session {self.id[:8]}...>"


class Conversation(Base):
    """Chat conversation model."""

    __tablename__ = "conversations"

    id = Column(String(32), primary_key=True, default=generate_id)
    user_id = Column(String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), default="New Conversation")
    provider = Column(String(64), nullable=True)
    model = Column(String(128), nullable=True)
    settings_json = Column(JSON, nullable=True)
    system_prompt = Column(Text, nullable=True)
    preset_id = Column(String(32), ForeignKey("chat_presets.id", ondelete="SET NULL"), nullable=True)
    project_id = Column(String(32), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    parent_conversation_id = Column(String(32), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)
    branched_from_message_id = Column(String(32), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    # Relationships
    user: User = relationship("User", back_populates="conversations")
    project: Optional["Project"] = relationship("Project", back_populates="conversations")
    parent_conversation: Optional["Conversation"] = relationship(
        "Conversation", remote_side=[id]
    )
    messages: List["Message"] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        foreign_keys="Message.conversation_id",
    )

    def __repr__(self) -> str:
        return f"<Conversation {self.id[:8]}...>"


class Message(Base):
    """Chat message model."""

    __tablename__ = "messages"

    id = Column(String(32), primary_key=True, default=generate_id)
    conversation_id = Column(
        String(32), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    parent_message_id = Column(String(32), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    revision_of_message_id = Column(String(32), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    role = Column(String(32), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    content_parts_json = Column(JSON, nullable=True)
    citations_json = Column(JSON, nullable=True)
    tool_events_json = Column(JSON, nullable=True)
    provider_meta_json = Column(JSON, nullable=True)
    tokens_prompt = Column(Integer, nullable=True)
    tokens_completion = Column(Integer, nullable=True)
    provider = Column(String(64), nullable=True)
    model = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=utcnow)

    # Relationships
    conversation: Conversation = relationship(
        "Conversation",
        back_populates="messages",
        foreign_keys=[conversation_id],
    )
    parent_message: Optional["Message"] = relationship(
        "Message",
        remote_side=[id],
        foreign_keys=[parent_message_id],
    )

    def __repr__(self) -> str:
        return f"<Message {self.role} {self.id[:8]}...>"


class InviteCode(Base):
    """Invite code for registration."""

    __tablename__ = "invite_codes"

    id = Column(String(32), primary_key=True, default=generate_id)
    code = Column(String(32), unique=True, index=True, nullable=False)
    created_by = Column(String(32), ForeignKey("users.id"), nullable=True)
    used_by = Column(String(32), ForeignKey("users.id"), nullable=True)
    used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    def __repr__(self) -> str:
        return f"<InviteCode {self.code[:8]}...>"


class MemoryEntry(Base):
    """User memory entry."""

    __tablename__ = "memory_entries"

    id = Column(String(32), primary_key=True, default=generate_id)
    user_id = Column(String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    tags = Column(JSON, nullable=True)
    embedding_model = Column(String(128), nullable=True)
    embedding_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    def __repr__(self) -> str:
        return f"<MemoryEntry {self.id[:8]}...>"


class KnowledgeDocument(Base):
    """Knowledge document metadata."""

    __tablename__ = "knowledge_docs"

    id = Column(String(32), primary_key=True, default=generate_id)
    user_id = Column(String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    mime_type = Column(String(128), nullable=True)
    size = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    def __repr__(self) -> str:
        return f"<KnowledgeDocument {self.id[:8]}...>"


class KnowledgeChunk(Base):
    """Knowledge document chunk."""

    __tablename__ = "knowledge_chunks"

    id = Column(String(32), primary_key=True, default=generate_id)
    doc_id = Column(String(32), ForeignKey("knowledge_docs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding_model = Column(String(128), nullable=True)
    embedding_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    def __repr__(self) -> str:
        return f"<KnowledgeChunk {self.id[:8]}...>"


class ChatPreset(Base):
    """Saved chat preset for sampling settings."""

    __tablename__ = "chat_presets"

    id = Column(String(32), primary_key=True, default=generate_id)
    user_id = Column(String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    settings_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    def __repr__(self) -> str:
        return f"<ChatPreset {self.name} {self.id[:8]}...>"


class ToolReceipt(Base):
    """Tool execution receipt."""

    __tablename__ = "tool_receipts"

    id = Column(String(32), primary_key=True, default=generate_id)
    user_id = Column(String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    conversation_id = Column(String(32), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)
    tool_id = Column(String(128), nullable=False, index=True)
    status = Column(String(32), default="completed")
    input_payload = Column(JSON, nullable=True)
    output_payload = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    run_id = Column(String(32), ForeignKey("chat_runs.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class ToolFavorite(Base):
    """User tool favorites."""

    __tablename__ = "tool_favorites"

    id = Column(String(32), primary_key=True, default=generate_id)
    user_id = Column(String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tool_id = Column(String(128), nullable=False, index=True)
    created_at = Column(DateTime, default=utcnow)


class ToolSetting(Base):
    """Per-conversation tool enable/disable."""

    __tablename__ = "tool_settings"

    id = Column(String(32), primary_key=True, default=generate_id)
    user_id = Column(String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    conversation_id = Column(String(32), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True)
    tool_id = Column(String(128), nullable=False, index=True)
    enabled = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class MediaAsset(Base):
    """Uploaded media asset."""

    __tablename__ = "media_assets"

    id = Column(String(32), primary_key=True, default=generate_id)
    user_id = Column(String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(255), nullable=False)
    mime_type = Column(String(128), nullable=True)
    size = Column(Integer, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    storage_path = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow)


class MediaJob(Base):
    """Long-running media job."""

    __tablename__ = "media_jobs"

    id = Column(String(32), primary_key=True, default=generate_id)
    user_id = Column(String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(64), nullable=False)
    status = Column(String(32), default="pending")
    input_asset_id = Column(String(32), ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True)
    prompt = Column(Text, nullable=True)
    params = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    progress = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    completed_at = Column(DateTime, nullable=True)


class Project(Base):
    """Project workspace for organizing conversations."""

    __tablename__ = "projects"

    id = Column(String(32), primary_key=True, default=generate_id)
    user_id = Column(String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    instructions = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    user: User = relationship("User", back_populates="projects")
    conversations: List["Conversation"] = relationship("Conversation", back_populates="project")

    def __repr__(self) -> str:
        return f"<Project {self.name} {self.id[:8]}...>"


class ContextBlock(Base):
    """Pinned context block for a project or conversation."""

    __tablename__ = "context_blocks"

    id = Column(String(32), primary_key=True, default=generate_id)
    user_id = Column(String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String(32), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    conversation_id = Column(String(32), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    def __repr__(self) -> str:
        return f"<ContextBlock {self.title} {self.id[:8]}...>"


class ChatRun(Base):
    """Chat run with persisted event stream."""

    __tablename__ = "chat_runs"

    id = Column(String(32), primary_key=True, default=generate_id)
    user_id = Column(String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(String(32), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(64), nullable=True)
    model = Column(String(128), nullable=True)
    settings_json = Column(JSON, nullable=True)
    status = Column(String(32), default="running")
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    cancelled_at = Column(DateTime, nullable=True)
    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<ChatRun {self.id[:8]}... {self.status}>"


class ChatRunEvent(Base):
    """Event log entry for a chat run."""

    __tablename__ = "chat_run_events"
    __table_args__ = (
        UniqueConstraint("run_id", "seq", name="uq_chat_run_events_run_seq"),
        Index("ix_chat_run_events_run_seq", "run_id", "seq"),
    )

    id = Column(String(32), primary_key=True, default=generate_id)
    run_id = Column(String(32), ForeignKey("chat_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    seq = Column(Integer, nullable=False)
    type = Column(String(64), nullable=False)
    payload_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    def __repr__(self) -> str:
        return f"<ChatRunEvent {self.run_id[:8]} #{self.seq} {self.type}>"


class Artifact(Base):
    """Persisted artifact output from a conversation."""

    __tablename__ = "artifacts"

    id = Column(String(32), primary_key=True, default=generate_id)
    user_id = Column(String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String(32), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    conversation_id = Column(String(32), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(64), nullable=False)
    title = Column(String(255), nullable=True)
    content = Column(Text, nullable=False)
    language = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    def __repr__(self) -> str:
        return f"<Artifact {self.type} {self.id[:8]}...>"


class AuditLog(Base):
    """Audit log entry for security and operational events."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_created_at", "created_at"),
        Index("ix_audit_logs_user_id", "user_id"),
        Index("ix_audit_logs_event_type", "event_type"),
    )

    id = Column(String(32), primary_key=True, default=generate_id)
    user_id = Column(String(32), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    event_type = Column(String(128), nullable=False)
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(512), nullable=True)
    path = Column(String(255), nullable=True)
    method = Column(String(16), nullable=True)
    data_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    def __repr__(self) -> str:
        return f"<AuditLog {self.event_type} {self.id[:8]}...>"


class WorkflowTemplate(Base):
    """Workflow template definition (built-in or user-created)."""

    __tablename__ = "workflow_templates"

    id = Column(String(32), primary_key=True, default=generate_id)
    user_id = Column(String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    steps_json = Column(JSON, nullable=False)
    category = Column(String(64), nullable=True)
    is_builtin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    def __repr__(self) -> str:
        return f"<WorkflowTemplate {self.name} {self.id[:8]}...>"


class WorkflowRun(Base):
    """A single execution of a workflow."""

    __tablename__ = "workflow_runs"
    __table_args__ = (
        Index("ix_workflow_runs_user_status", "user_id", "status"),
    )

    id = Column(String(32), primary_key=True, default=generate_id)
    user_id = Column(String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    template_id = Column(String(32), ForeignKey("workflow_templates.id", ondelete="SET NULL"), nullable=True)
    project_id = Column(String(32), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    conversation_id = Column(String(32), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    status = Column(String(32), default="pending")
    input_json = Column(JSON, nullable=True)
    output_json = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    completed_at = Column(DateTime, nullable=True)

    steps: List["WorkflowStep"] = relationship(
        "WorkflowStep", back_populates="run", cascade="all, delete-orphan",
        order_by="WorkflowStep.seq",
    )

    def __repr__(self) -> str:
        return f"<WorkflowRun {self.id[:8]}... {self.status}>"


class WorkflowStep(Base):
    """A single step within a workflow run."""

    __tablename__ = "workflow_steps"
    __table_args__ = (
        Index("ix_workflow_steps_run_seq", "run_id", "seq"),
    )

    id = Column(String(32), primary_key=True, default=generate_id)
    run_id = Column(String(32), ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    seq = Column(Integer, nullable=False)
    type = Column(String(32), nullable=False)
    title = Column(String(255), nullable=False)
    prompt_template = Column(Text, nullable=True)
    input_json = Column(JSON, nullable=True)
    output_text = Column(Text, nullable=True)
    output_json = Column(JSON, nullable=True)
    status = Column(String(32), default="pending")
    provider = Column(String(64), nullable=True)
    model = Column(String(128), nullable=True)
    tokens_used = Column(Integer, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    run: WorkflowRun = relationship("WorkflowRun", back_populates="steps")

    def __repr__(self) -> str:
        return f"<WorkflowStep {self.run_id[:8]} #{self.seq} {self.type}>"
