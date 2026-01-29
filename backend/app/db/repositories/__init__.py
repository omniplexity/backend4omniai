"""Database repositories for data access."""

from app.db.repositories.audit import (
    AuditAction,
    list_audit_entries,
    log_audit,
    log_invite_create,
    log_login,
    log_logout,
    log_register,
    log_session_create,
    log_user_disable,
)
from app.db.repositories.conversation import (
    create_conversation,
    create_message,
    delete_conversation,
    get_conversation_messages,
    get_last_assistant_message_after,
    get_last_user_message,
    get_user_conversation,
    list_user_conversations,
    update_conversation_title,
)
from app.db.repositories.invite import (
    create_invite,
    generate_invite_code,
    get_all_invites,
    get_invite_by_code,
    get_invites_by_creator,
    use_invite,
    validate_invite,
)
from app.db.repositories.quota import (
    get_usage_counter,
    get_user_quota,
    increment_usage_counter,
    list_usage_entries,
    list_users_with_quota,
    update_user_quota,
)
from app.db.repositories.user import (
    create_user,
    email_exists,
    get_user_by_email,
    get_user_by_id,
    get_user_by_username,
    get_user_by_username_or_email,
    update_last_login,
    update_user_status,
    username_exists,
)

__all__ = [
    # User
    "get_user_by_id",
    "get_user_by_username",
    "get_user_by_email",
    "get_user_by_username_or_email",
    "create_user",
    "update_user_status",
    "update_last_login",
    "username_exists",
    "email_exists",
    # Quota
    "get_user_quota",
    "update_user_quota",
    "list_users_with_quota",
    "list_usage_entries",
    "get_usage_counter",
    "increment_usage_counter",
    # Invite
    "generate_invite_code",
    "create_invite",
    "get_invite_by_code",
    "validate_invite",
    "use_invite",
    "get_invites_by_creator",
    "get_all_invites",
    # Audit
    "AuditAction",
    "list_audit_entries",
    "log_audit",
    "log_login",
    "log_logout",
    "log_register",
    "log_session_create",
    "log_invite_create",
    "log_user_disable",
    # Conversations
    "create_conversation",
    "list_user_conversations",
    "get_user_conversation",
    "update_conversation_title",
    "delete_conversation",
    "get_conversation_messages",
    "create_message",
    "get_last_user_message",
    "get_last_assistant_message_after",
]
