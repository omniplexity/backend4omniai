"""add chat workspace tables and columns

Revision ID: 004_chat_workspace
Revises: 003_memory_knowledge
Create Date: 2026-02-04
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "004_chat_workspace"
down_revision = "003_memory_knowledge"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    return column in {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    is_sqlite = bind.dialect.name == "sqlite"

    if "projects" not in tables:
        op.create_table(
            "projects",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("instructions", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    if "projects" in inspector.get_table_names():
        indexes = {idx["name"] for idx in inspector.get_indexes("projects")}
        if "ix_projects_user_id" not in indexes:
            op.create_index("ix_projects_user_id", "projects", ["user_id"], unique=False)

    if "context_blocks" not in tables:
        op.create_table(
            "context_blocks",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("project_id", sa.String(length=32), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
            sa.Column("conversation_id", sa.String(length=32), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    if "context_blocks" in inspector.get_table_names():
        indexes = {idx["name"] for idx in inspector.get_indexes("context_blocks")}
        if "ix_context_blocks_user_id" not in indexes:
            op.create_index("ix_context_blocks_user_id", "context_blocks", ["user_id"], unique=False)
        if "ix_context_blocks_project_id" not in indexes:
            op.create_index("ix_context_blocks_project_id", "context_blocks", ["project_id"], unique=False)
        if "ix_context_blocks_conversation_id" not in indexes:
            op.create_index("ix_context_blocks_conversation_id", "context_blocks", ["conversation_id"], unique=False)

    if "chat_runs" not in tables:
        op.create_table(
            "chat_runs",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("conversation_id", sa.String(length=32), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("provider", sa.String(length=64), nullable=True),
            sa.Column("model", sa.String(length=128), nullable=True),
            sa.Column("settings_json", sa.JSON(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'running'")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("cancelled_at", sa.DateTime(), nullable=True),
            sa.Column("error_code", sa.String(length=64), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
        )
    if "chat_runs" in inspector.get_table_names():
        indexes = {idx["name"] for idx in inspector.get_indexes("chat_runs")}
        if "ix_chat_runs_user_id" not in indexes:
            op.create_index("ix_chat_runs_user_id", "chat_runs", ["user_id"], unique=False)
        if "ix_chat_runs_conversation_id" not in indexes:
            op.create_index("ix_chat_runs_conversation_id", "chat_runs", ["conversation_id"], unique=False)

    if "chat_run_events" not in tables:
        op.create_table(
            "chat_run_events",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("run_id", sa.String(length=32), sa.ForeignKey("chat_runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("seq", sa.Integer(), nullable=False),
            sa.Column("type", sa.String(length=64), nullable=False),
            sa.Column("payload_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("run_id", "seq", name="uq_chat_run_events_run_seq"),
        )
    if "chat_run_events" in inspector.get_table_names():
        indexes = {idx["name"] for idx in inspector.get_indexes("chat_run_events")}
        if "ix_chat_run_events_run_id" not in indexes:
            op.create_index("ix_chat_run_events_run_id", "chat_run_events", ["run_id"], unique=False)
        if "ix_chat_run_events_run_seq" not in indexes:
            op.create_index("ix_chat_run_events_run_seq", "chat_run_events", ["run_id", "seq"], unique=False)

    if "artifacts" not in tables:
        op.create_table(
            "artifacts",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("project_id", sa.String(length=32), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
            sa.Column("conversation_id", sa.String(length=32), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("type", sa.String(length=64), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("language", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    if "artifacts" in inspector.get_table_names():
        indexes = {idx["name"] for idx in inspector.get_indexes("artifacts")}
        if "ix_artifacts_user_id" not in indexes:
            op.create_index("ix_artifacts_user_id", "artifacts", ["user_id"], unique=False)
        if "ix_artifacts_project_id" not in indexes:
            op.create_index("ix_artifacts_project_id", "artifacts", ["project_id"], unique=False)
        if "ix_artifacts_conversation_id" not in indexes:
            op.create_index("ix_artifacts_conversation_id", "artifacts", ["conversation_id"], unique=False)

    if "conversations" in tables:
        if is_sqlite:
            with op.batch_alter_table("conversations") as batch:
                if not _has_column(inspector, "conversations", "project_id"):
                    batch.add_column(sa.Column("project_id", sa.String(length=32), nullable=True))
                    batch.create_foreign_key(
                        "fk_conversations_project_id", "projects", ["project_id"], ["id"], ondelete="SET NULL"
                    )
                if not _has_column(inspector, "conversations", "parent_conversation_id"):
                    batch.add_column(sa.Column("parent_conversation_id", sa.String(length=32), nullable=True))
                    batch.create_foreign_key(
                        "fk_conversations_parent_id", "conversations", ["parent_conversation_id"], ["id"], ondelete="SET NULL"
                    )
                if not _has_column(inspector, "conversations", "branched_from_message_id"):
                    batch.add_column(sa.Column("branched_from_message_id", sa.String(length=32), nullable=True))
                    batch.create_foreign_key(
                        "fk_conversations_branched_message_id", "messages", ["branched_from_message_id"], ["id"], ondelete="SET NULL"
                    )
        else:
            if not _has_column(inspector, "conversations", "project_id"):
                op.add_column("conversations", sa.Column("project_id", sa.String(length=32), nullable=True))
                op.create_foreign_key(
                    "fk_conversations_project_id", "conversations", "projects", ["project_id"], ["id"], ondelete="SET NULL"
                )
            if not _has_column(inspector, "conversations", "parent_conversation_id"):
                op.add_column("conversations", sa.Column("parent_conversation_id", sa.String(length=32), nullable=True))
                op.create_foreign_key(
                    "fk_conversations_parent_id", "conversations", "conversations", ["parent_conversation_id"], ["id"], ondelete="SET NULL"
                )
            if not _has_column(inspector, "conversations", "branched_from_message_id"):
                op.add_column("conversations", sa.Column("branched_from_message_id", sa.String(length=32), nullable=True))
                op.create_foreign_key(
                    "fk_conversations_branched_message_id", "conversations", "messages", ["branched_from_message_id"], ["id"], ondelete="SET NULL"
                )

    if "messages" in tables:
        if is_sqlite:
            with op.batch_alter_table("messages") as batch:
                if not _has_column(inspector, "messages", "parent_message_id"):
                    batch.add_column(sa.Column("parent_message_id", sa.String(length=32), nullable=True))
                    batch.create_foreign_key(
                        "fk_messages_parent_id", "messages", ["parent_message_id"], ["id"], ondelete="SET NULL"
                    )
                if not _has_column(inspector, "messages", "revision_of_message_id"):
                    batch.add_column(sa.Column("revision_of_message_id", sa.String(length=32), nullable=True))
                    batch.create_foreign_key(
                        "fk_messages_revision_of_id", "messages", ["revision_of_message_id"], ["id"], ondelete="SET NULL"
                    )
                if not _has_column(inspector, "messages", "content_parts_json"):
                    batch.add_column(sa.Column("content_parts_json", sa.JSON(), nullable=True))
                if not _has_column(inspector, "messages", "citations_json"):
                    batch.add_column(sa.Column("citations_json", sa.JSON(), nullable=True))
                if not _has_column(inspector, "messages", "tool_events_json"):
                    batch.add_column(sa.Column("tool_events_json", sa.JSON(), nullable=True))
        else:
            if not _has_column(inspector, "messages", "parent_message_id"):
                op.add_column("messages", sa.Column("parent_message_id", sa.String(length=32), nullable=True))
                op.create_foreign_key(
                    "fk_messages_parent_id", "messages", "messages", ["parent_message_id"], ["id"], ondelete="SET NULL"
                )
            if not _has_column(inspector, "messages", "revision_of_message_id"):
                op.add_column("messages", sa.Column("revision_of_message_id", sa.String(length=32), nullable=True))
                op.create_foreign_key(
                    "fk_messages_revision_of_id", "messages", "messages", ["revision_of_message_id"], ["id"], ondelete="SET NULL"
                )
            if not _has_column(inspector, "messages", "content_parts_json"):
                op.add_column("messages", sa.Column("content_parts_json", sa.JSON(), nullable=True))
            if not _has_column(inspector, "messages", "citations_json"):
                op.add_column("messages", sa.Column("citations_json", sa.JSON(), nullable=True))
            if not _has_column(inspector, "messages", "tool_events_json"):
                op.add_column("messages", sa.Column("tool_events_json", sa.JSON(), nullable=True))

    if "tool_receipts" in tables and not _has_column(inspector, "tool_receipts", "run_id"):
        if is_sqlite:
            with op.batch_alter_table("tool_receipts") as batch:
                batch.add_column(sa.Column("run_id", sa.String(length=32), nullable=True))
                batch.create_foreign_key(
                    "fk_tool_receipts_run_id", "chat_runs", ["run_id"], ["id"], ondelete="SET NULL"
                )
        else:
            op.add_column("tool_receipts", sa.Column("run_id", sa.String(length=32), nullable=True))
            op.create_foreign_key(
                "fk_tool_receipts_run_id", "tool_receipts", "chat_runs", ["run_id"], ["id"], ondelete="SET NULL"
            )

    if is_sqlite:
        op.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chat_messages_fts USING fts5(message_id UNINDEXED, conversation_id UNINDEXED, content)"
        )
        op.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chat_conversations_fts USING fts5(conversation_id UNINDEXED, title)"
        )
        op.execute(
            "INSERT INTO chat_messages_fts(rowid, message_id, conversation_id, content) SELECT rowid, id, conversation_id, content FROM messages"
        )
        op.execute(
            "INSERT INTO chat_conversations_fts(rowid, conversation_id, title) SELECT rowid, id, title FROM conversations"
        )
        op.execute(
            """
            CREATE TRIGGER IF NOT EXISTS chat_messages_ai AFTER INSERT ON messages
            BEGIN
              INSERT INTO chat_messages_fts(rowid, message_id, conversation_id, content)
              VALUES (new.rowid, new.id, new.conversation_id, new.content);
            END;
            """
        )
        op.execute(
            """
            CREATE TRIGGER IF NOT EXISTS chat_messages_ad AFTER DELETE ON messages
            BEGIN
              DELETE FROM chat_messages_fts WHERE rowid = old.rowid;
            END;
            """
        )
        op.execute(
            """
            CREATE TRIGGER IF NOT EXISTS chat_messages_au AFTER UPDATE ON messages
            BEGIN
              UPDATE chat_messages_fts
              SET message_id = new.id, conversation_id = new.conversation_id, content = new.content
              WHERE rowid = old.rowid;
            END;
            """
        )
        op.execute(
            """
            CREATE TRIGGER IF NOT EXISTS chat_conversations_ai AFTER INSERT ON conversations
            BEGIN
              INSERT INTO chat_conversations_fts(rowid, conversation_id, title)
              VALUES (new.rowid, new.id, new.title);
            END;
            """
        )
        op.execute(
            """
            CREATE TRIGGER IF NOT EXISTS chat_conversations_ad AFTER DELETE ON conversations
            BEGIN
              DELETE FROM chat_conversations_fts WHERE rowid = old.rowid;
            END;
            """
        )
        op.execute(
            """
            CREATE TRIGGER IF NOT EXISTS chat_conversations_au AFTER UPDATE ON conversations
            BEGIN
              UPDATE chat_conversations_fts
              SET conversation_id = new.id, title = new.title
              WHERE rowid = old.rowid;
            END;
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    if is_sqlite:
        op.execute("DROP TRIGGER IF EXISTS chat_messages_ai")
        op.execute("DROP TRIGGER IF EXISTS chat_messages_ad")
        op.execute("DROP TRIGGER IF EXISTS chat_messages_au")
        op.execute("DROP TRIGGER IF EXISTS chat_conversations_ai")
        op.execute("DROP TRIGGER IF EXISTS chat_conversations_ad")
        op.execute("DROP TRIGGER IF EXISTS chat_conversations_au")
        op.execute("DROP TABLE IF EXISTS chat_messages_fts")
        op.execute("DROP TABLE IF EXISTS chat_conversations_fts")

    if is_sqlite:
        with op.batch_alter_table("tool_receipts") as batch:
            batch.drop_constraint("fk_tool_receipts_run_id", type_="foreignkey")
            batch.drop_column("run_id")

        with op.batch_alter_table("messages") as batch:
            batch.drop_constraint("fk_messages_revision_of_id", type_="foreignkey")
            batch.drop_constraint("fk_messages_parent_id", type_="foreignkey")
            batch.drop_column("tool_events_json")
            batch.drop_column("citations_json")
            batch.drop_column("content_parts_json")
            batch.drop_column("revision_of_message_id")
            batch.drop_column("parent_message_id")

        with op.batch_alter_table("conversations") as batch:
            batch.drop_constraint("fk_conversations_branched_message_id", type_="foreignkey")
            batch.drop_constraint("fk_conversations_parent_id", type_="foreignkey")
            batch.drop_constraint("fk_conversations_project_id", type_="foreignkey")
            batch.drop_column("branched_from_message_id")
            batch.drop_column("parent_conversation_id")
            batch.drop_column("project_id")
    else:
        op.drop_constraint("fk_tool_receipts_run_id", "tool_receipts", type_="foreignkey")
        op.drop_column("tool_receipts", "run_id")

        op.drop_constraint("fk_messages_revision_of_id", "messages", type_="foreignkey")
        op.drop_constraint("fk_messages_parent_id", "messages", type_="foreignkey")
        op.drop_column("messages", "tool_events_json")
        op.drop_column("messages", "citations_json")
        op.drop_column("messages", "content_parts_json")
        op.drop_column("messages", "revision_of_message_id")
        op.drop_column("messages", "parent_message_id")

        op.drop_constraint("fk_conversations_branched_message_id", "conversations", type_="foreignkey")
        op.drop_constraint("fk_conversations_parent_id", "conversations", type_="foreignkey")
        op.drop_constraint("fk_conversations_project_id", "conversations", type_="foreignkey")
        op.drop_column("conversations", "branched_from_message_id")
        op.drop_column("conversations", "parent_conversation_id")
        op.drop_column("conversations", "project_id")

    op.drop_index("ix_artifacts_conversation_id", table_name="artifacts")
    op.drop_index("ix_artifacts_project_id", table_name="artifacts")
    op.drop_index("ix_artifacts_user_id", table_name="artifacts")
    op.drop_table("artifacts")

    op.drop_index("ix_chat_run_events_run_seq", table_name="chat_run_events")
    op.drop_index("ix_chat_run_events_run_id", table_name="chat_run_events")
    op.drop_table("chat_run_events")

    op.drop_index("ix_chat_runs_conversation_id", table_name="chat_runs")
    op.drop_index("ix_chat_runs_user_id", table_name="chat_runs")
    op.drop_table("chat_runs")

    op.drop_index("ix_context_blocks_conversation_id", table_name="context_blocks")
    op.drop_index("ix_context_blocks_project_id", table_name="context_blocks")
    op.drop_index("ix_context_blocks_user_id", table_name="context_blocks")
    op.drop_table("context_blocks")

    op.drop_index("ix_projects_user_id", table_name="projects")
    op.drop_table("projects")
