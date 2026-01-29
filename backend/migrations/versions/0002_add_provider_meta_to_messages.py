"""Add provider_meta to messages table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-01-29
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add provider_meta column to messages."""
    op.add_column("messages", sa.Column("provider_meta", sa.Text(), nullable=True))


def downgrade() -> None:
    """Drop provider_meta column."""
    op.drop_column("messages", "provider_meta")
