"""Add quota and usage counter tables.

Revision ID: 0003
Revises: 0002_add_provider_meta_to_messages
Create Date: 2026-01-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create quota and usage counter tables."""
    op.create_table(
        "user_quotas",
        sa.Column("user_id", sa.String(36), primary_key=True),
        sa.Column("messages_per_day", sa.Integer(), nullable=True),
        sa.Column("tokens_per_day", sa.Integer(), nullable=True),
        sa.Column("reset_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_quotas_user_id_users"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        op.f("ix_user_quotas_user_id"),
        "user_quotas",
        ["user_id"],
    )

    op.create_table(
        "usage_counters",
        sa.Column("user_id", sa.String(36), primary_key=True),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("messages_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_usage_counters_user_id_users"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        op.f("ix_usage_counters_user_id"),
        "usage_counters",
        ["user_id"],
    )
    op.create_index(
        op.f("ix_usage_counters_date"),
        "usage_counters",
        ["date"],
    )


def downgrade() -> None:
    """Drop quota and usage counter tables."""
    op.drop_index(op.f("ix_usage_counters_date"), table_name="usage_counters")
    op.drop_index(op.f("ix_usage_counters_user_id"), table_name="usage_counters")
    op.drop_table("usage_counters")
    op.drop_index(op.f("ix_user_quotas_user_id"), table_name="user_quotas")
    op.drop_table("user_quotas")
