"""add audit logs

Revision ID: 006_audit_logs
Revises: 005_v1_receipts_presets
Create Date: 2026-02-06
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "006_audit_logs"
down_revision = "005_v1_receipts_presets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "audit_logs" not in tables:
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("event_type", sa.String(length=128), nullable=False),
            sa.Column("ip", sa.String(length=64), nullable=True),
            sa.Column("user_agent", sa.String(length=512), nullable=True),
            sa.Column("path", sa.String(length=255), nullable=True),
            sa.Column("method", sa.String(length=16), nullable=True),
            sa.Column("data_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    # Indexes (idempotent-ish)
    if "audit_logs" in inspector.get_table_names():
        indexes = {idx["name"] for idx in inspector.get_indexes("audit_logs")}
        if "ix_audit_logs_created_at" not in indexes:
            op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"], unique=False)
        if "ix_audit_logs_user_id" not in indexes:
            op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"], unique=False)
        if "ix_audit_logs_event_type" not in indexes:
            op.create_index("ix_audit_logs_event_type", "audit_logs", ["event_type"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "audit_logs" in tables:
        indexes = {idx["name"] for idx in inspector.get_indexes("audit_logs")}
        if "ix_audit_logs_event_type" in indexes:
            op.drop_index("ix_audit_logs_event_type", table_name="audit_logs")
        if "ix_audit_logs_user_id" in indexes:
            op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
        if "ix_audit_logs_created_at" in indexes:
            op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
        op.drop_table("audit_logs")

