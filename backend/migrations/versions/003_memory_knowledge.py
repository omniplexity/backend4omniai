"""add memory and knowledge tables

Revision ID: 003_memory_knowledge
Revises: 002_tools_media
Create Date: 2026-02-04
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "003_memory_knowledge"
down_revision = "002_tools_media"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "memory_entries" not in tables:
        op.create_table(
            "memory_entries",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("tags", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    if "memory_entries" in inspector.get_table_names():
        indexes = {idx["name"] for idx in inspector.get_indexes("memory_entries")}
        if "ix_memory_entries_user_id" not in indexes:
            op.create_index("ix_memory_entries_user_id", "memory_entries", ["user_id"], unique=False)

    if "knowledge_docs" not in tables:
        op.create_table(
            "knowledge_docs",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("mime_type", sa.String(length=128), nullable=True),
            sa.Column("size", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    if "knowledge_docs" in inspector.get_table_names():
        indexes = {idx["name"] for idx in inspector.get_indexes("knowledge_docs")}
        if "ix_knowledge_docs_user_id" not in indexes:
            op.create_index("ix_knowledge_docs_user_id", "knowledge_docs", ["user_id"], unique=False)

    if "knowledge_chunks" not in tables:
        op.create_table(
            "knowledge_chunks",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("doc_id", sa.String(length=32), sa.ForeignKey("knowledge_docs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("chunk_index", sa.Integer(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    if "knowledge_chunks" in inspector.get_table_names():
        indexes = {idx["name"] for idx in inspector.get_indexes("knowledge_chunks")}
        if "ix_knowledge_chunks_doc_id" not in indexes:
            op.create_index("ix_knowledge_chunks_doc_id", "knowledge_chunks", ["doc_id"], unique=False)
        if "ix_knowledge_chunks_user_id" not in indexes:
            op.create_index("ix_knowledge_chunks_user_id", "knowledge_chunks", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_user_id", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_doc_id", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_index("ix_knowledge_docs_user_id", table_name="knowledge_docs")
    op.drop_table("knowledge_docs")
    op.drop_index("ix_memory_entries_user_id", table_name="memory_entries")
    op.drop_table("memory_entries")
