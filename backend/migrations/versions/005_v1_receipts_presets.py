"""add chat presets and provider meta

Revision ID: 005_v1_receipts_presets
Revises: 004_chat_workspace
Create Date: 2026-02-04
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "005_v1_receipts_presets"
down_revision = "004_chat_workspace"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    return column in {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    is_sqlite = bind.dialect.name == "sqlite"

    if "chat_presets" not in tables:
        op.create_table(
            "chat_presets",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("settings_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    if "chat_presets" in inspector.get_table_names():
        indexes = {idx["name"] for idx in inspector.get_indexes("chat_presets")}
        if "ix_chat_presets_user_id" not in indexes:
            op.create_index("ix_chat_presets_user_id", "chat_presets", ["user_id"], unique=False)

    if "conversations" in tables:
        if is_sqlite:
            with op.batch_alter_table("conversations") as batch:
                if not _has_column(inspector, "conversations", "settings_json"):
                    batch.add_column(sa.Column("settings_json", sa.JSON(), nullable=True))
                if not _has_column(inspector, "conversations", "system_prompt"):
                    batch.add_column(sa.Column("system_prompt", sa.Text(), nullable=True))
                if not _has_column(inspector, "conversations", "preset_id"):
                    batch.add_column(sa.Column("preset_id", sa.String(length=32), nullable=True))
                    batch.create_foreign_key(
                        "fk_conversations_preset_id", "chat_presets", ["preset_id"], ["id"], ondelete="SET NULL"
                    )
        else:
            if not _has_column(inspector, "conversations", "settings_json"):
                op.add_column("conversations", sa.Column("settings_json", sa.JSON(), nullable=True))
            if not _has_column(inspector, "conversations", "system_prompt"):
                op.add_column("conversations", sa.Column("system_prompt", sa.Text(), nullable=True))
            if not _has_column(inspector, "conversations", "preset_id"):
                op.add_column("conversations", sa.Column("preset_id", sa.String(length=32), nullable=True))
                op.create_foreign_key(
                    "fk_conversations_preset_id", "conversations", "chat_presets", ["preset_id"], ["id"], ondelete="SET NULL"
                )

    if "messages" in tables and not _has_column(inspector, "messages", "provider_meta_json"):
        op.add_column("messages", sa.Column("provider_meta_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    is_sqlite = bind.dialect.name == "sqlite"

    if "messages" in tables and _has_column(inspector, "messages", "provider_meta_json"):
        op.drop_column("messages", "provider_meta_json")

    if "conversations" in tables:
        if is_sqlite:
            with op.batch_alter_table("conversations") as batch:
                if _has_column(inspector, "conversations", "preset_id"):
                    batch.drop_constraint("fk_conversations_preset_id", type_="foreignkey")
                    batch.drop_column("preset_id")
                if _has_column(inspector, "conversations", "system_prompt"):
                    batch.drop_column("system_prompt")
                if _has_column(inspector, "conversations", "settings_json"):
                    batch.drop_column("settings_json")
        else:
            if _has_column(inspector, "conversations", "preset_id"):
                op.drop_constraint("fk_conversations_preset_id", "conversations", type_="foreignkey")
                op.drop_column("conversations", "preset_id")
            if _has_column(inspector, "conversations", "system_prompt"):
                op.drop_column("conversations", "system_prompt")
            if _has_column(inspector, "conversations", "settings_json"):
                op.drop_column("conversations", "settings_json")

    if "chat_presets" in tables:
        indexes = {idx["name"] for idx in inspector.get_indexes("chat_presets")}
        if "ix_chat_presets_user_id" in indexes:
            op.drop_index("ix_chat_presets_user_id", table_name="chat_presets")
        op.drop_table("chat_presets")
