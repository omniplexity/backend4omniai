"""add workflow tables

Revision ID: 009_workflows
Revises: 008_embeddings_columns
Create Date: 2026-02-06
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "009_workflows"
down_revision = "008_embeddings_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "workflow_templates" not in tables:
        op.create_table(
            "workflow_templates",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("steps_json", sa.JSON(), nullable=False),
            sa.Column("category", sa.String(length=64), nullable=True),
            sa.Column("is_builtin", sa.Boolean(), default=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_workflow_templates_user_id", "workflow_templates", ["user_id"])

    if "workflow_runs" not in tables:
        op.create_table(
            "workflow_runs",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("template_id", sa.String(length=32), sa.ForeignKey("workflow_templates.id", ondelete="SET NULL"), nullable=True),
            sa.Column("project_id", sa.String(length=32), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
            sa.Column("conversation_id", sa.String(length=32), sa.ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=32), default="pending"),
            sa.Column("input_json", sa.JSON(), nullable=True),
            sa.Column("output_json", sa.JSON(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_workflow_runs_user_id", "workflow_runs", ["user_id"])
        op.create_index("ix_workflow_runs_user_status", "workflow_runs", ["user_id", "status"])

    if "workflow_steps" not in tables:
        op.create_table(
            "workflow_steps",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("run_id", sa.String(length=32), sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("seq", sa.Integer(), nullable=False),
            sa.Column("type", sa.String(length=32), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("prompt_template", sa.Text(), nullable=True),
            sa.Column("input_json", sa.JSON(), nullable=True),
            sa.Column("output_text", sa.Text(), nullable=True),
            sa.Column("output_json", sa.JSON(), nullable=True),
            sa.Column("status", sa.String(length=32), default="pending"),
            sa.Column("provider", sa.String(length=64), nullable=True),
            sa.Column("model", sa.String(length=128), nullable=True),
            sa.Column("tokens_used", sa.Integer(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
        )
        op.create_index("ix_workflow_steps_run_id", "workflow_steps", ["run_id"])
        op.create_index("ix_workflow_steps_run_seq", "workflow_steps", ["run_id", "seq"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "workflow_steps" in tables:
        op.drop_table("workflow_steps")
    if "workflow_runs" in tables:
        op.drop_table("workflow_runs")
    if "workflow_templates" in tables:
        op.drop_table("workflow_templates")
