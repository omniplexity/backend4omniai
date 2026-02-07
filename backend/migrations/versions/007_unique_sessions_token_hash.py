"""unique sessions token_hash

Revision ID: 007_unique_sessions_token_hash
Revises: 006_audit_logs
Create Date: 2026-02-06
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "007_unique_sessions_token_hash"
down_revision = "006_audit_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "sessions" not in inspector.get_table_names():
        return

    indexes = {idx["name"] for idx in inspector.get_indexes("sessions")}
    # Add a deterministic name for both sqlite/postgres.
    if "uq_sessions_token_hash" not in indexes:
        op.create_index(
            "uq_sessions_token_hash",
            "sessions",
            ["token_hash"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "sessions" not in inspector.get_table_names():
        return

    indexes = {idx["name"] for idx in inspector.get_indexes("sessions")}
    if "uq_sessions_token_hash" in indexes:
        op.drop_index("uq_sessions_token_hash", table_name="sessions")

