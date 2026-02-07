"""add embeddings columns

Revision ID: 008_embeddings_columns
Revises: 007_unique_sessions_token_hash
Create Date: 2026-02-06
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "008_embeddings_columns"
down_revision = "007_unique_sessions_token_hash"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    return column in {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    is_sqlite = bind.dialect.name == "sqlite"

    if "memory_entries" in tables:
        if is_sqlite:
            with op.batch_alter_table("memory_entries") as batch:
                if not _has_column(inspector, "memory_entries", "embedding_model"):
                    batch.add_column(sa.Column("embedding_model", sa.String(length=128), nullable=True))
                if not _has_column(inspector, "memory_entries", "embedding_json"):
                    batch.add_column(sa.Column("embedding_json", sa.JSON(), nullable=True))
        else:
            if not _has_column(inspector, "memory_entries", "embedding_model"):
                op.add_column("memory_entries", sa.Column("embedding_model", sa.String(length=128), nullable=True))
            if not _has_column(inspector, "memory_entries", "embedding_json"):
                op.add_column("memory_entries", sa.Column("embedding_json", sa.JSON(), nullable=True))

    if "knowledge_chunks" in tables:
        if is_sqlite:
            with op.batch_alter_table("knowledge_chunks") as batch:
                if not _has_column(inspector, "knowledge_chunks", "embedding_model"):
                    batch.add_column(sa.Column("embedding_model", sa.String(length=128), nullable=True))
                if not _has_column(inspector, "knowledge_chunks", "embedding_json"):
                    batch.add_column(sa.Column("embedding_json", sa.JSON(), nullable=True))
        else:
            if not _has_column(inspector, "knowledge_chunks", "embedding_model"):
                op.add_column("knowledge_chunks", sa.Column("embedding_model", sa.String(length=128), nullable=True))
            if not _has_column(inspector, "knowledge_chunks", "embedding_json"):
                op.add_column("knowledge_chunks", sa.Column("embedding_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    is_sqlite = bind.dialect.name == "sqlite"

    if "knowledge_chunks" in tables:
        if is_sqlite:
            with op.batch_alter_table("knowledge_chunks") as batch:
                if _has_column(inspector, "knowledge_chunks", "embedding_json"):
                    batch.drop_column("embedding_json")
                if _has_column(inspector, "knowledge_chunks", "embedding_model"):
                    batch.drop_column("embedding_model")
        else:
            if _has_column(inspector, "knowledge_chunks", "embedding_json"):
                op.drop_column("knowledge_chunks", "embedding_json")
            if _has_column(inspector, "knowledge_chunks", "embedding_model"):
                op.drop_column("knowledge_chunks", "embedding_model")

    if "memory_entries" in tables:
        if is_sqlite:
            with op.batch_alter_table("memory_entries") as batch:
                if _has_column(inspector, "memory_entries", "embedding_json"):
                    batch.drop_column("embedding_json")
                if _has_column(inspector, "memory_entries", "embedding_model"):
                    batch.drop_column("embedding_model")
        else:
            if _has_column(inspector, "memory_entries", "embedding_json"):
                op.drop_column("memory_entries", "embedding_json")
            if _has_column(inspector, "memory_entries", "embedding_model"):
                op.drop_column("memory_entries", "embedding_model")

