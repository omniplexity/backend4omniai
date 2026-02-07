"""add tools and media tables

Revision ID: 002_tools_media
Revises: 001_initial_schema
Create Date: 2026-02-03
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "002_tools_media"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "tool_receipts" not in tables:
        op.create_table(
            "tool_receipts",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("conversation_id", sa.String(length=32), sa.ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True),
            sa.Column("tool_id", sa.String(length=128), nullable=False, index=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("input_payload", sa.JSON(), nullable=True),
            sa.Column("output_payload", sa.JSON(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    if "tool_receipts" in inspector.get_table_names():
        indexes = {idx["name"] for idx in inspector.get_indexes("tool_receipts")}
        if "ix_tool_receipts_tool_id" not in indexes:
            op.create_index("ix_tool_receipts_tool_id", "tool_receipts", ["tool_id"], unique=False)

    if "tool_favorites" not in tables:
        op.create_table(
            "tool_favorites",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("tool_id", sa.String(length=128), nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    if "tool_favorites" in inspector.get_table_names():
        indexes = {idx["name"] for idx in inspector.get_indexes("tool_favorites")}
        if "ix_tool_favorites_tool_id" not in indexes:
            op.create_index("ix_tool_favorites_tool_id", "tool_favorites", ["tool_id"], unique=False)

    if "tool_settings" not in tables:
        op.create_table(
            "tool_settings",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("conversation_id", sa.String(length=32), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True),
            sa.Column("tool_id", sa.String(length=128), nullable=False, index=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    if "tool_settings" in inspector.get_table_names():
        indexes = {idx["name"] for idx in inspector.get_indexes("tool_settings")}
        if "ix_tool_settings_tool_id" not in indexes:
            op.create_index("ix_tool_settings_tool_id", "tool_settings", ["tool_id"], unique=False)

    if "media_assets" not in tables:
        op.create_table(
            "media_assets",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("mime_type", sa.String(length=128), nullable=True),
            sa.Column("size", sa.Integer(), nullable=True),
            sa.Column("width", sa.Integer(), nullable=True),
            sa.Column("height", sa.Integer(), nullable=True),
            sa.Column("storage_path", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    if "media_jobs" not in tables:
        op.create_table(
            "media_jobs",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("type", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("input_asset_id", sa.String(length=32), sa.ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True),
            sa.Column("prompt", sa.Text(), nullable=True),
            sa.Column("params", sa.JSON(), nullable=True),
            sa.Column("result", sa.JSON(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("progress", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    op.drop_table("media_jobs")
    op.drop_table("media_assets")
    op.drop_index("ix_tool_settings_tool_id", table_name="tool_settings")
    op.drop_table("tool_settings")
    op.drop_index("ix_tool_favorites_tool_id", table_name="tool_favorites")
    op.drop_table("tool_favorites")
    op.drop_index("ix_tool_receipts_tool_id", table_name="tool_receipts")
    op.drop_table("tool_receipts")
