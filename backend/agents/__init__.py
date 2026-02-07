"""OmniAI Agents.

This module contains the agent implementations as described in AGENTS.md.
Each agent encapsulates a specific domain responsibility.
"""

from .provider.provider_agent import ProviderAgent
from .auth.auth_agent import AuthAgent
from .conversation.conversation_agent import ConversationAgent
from .chat.chat_agent import ChatAgent
from .tool.tool_agent import ToolAgent
from .voice.voice_agent import VoiceAgent
from .memory.memory_agent import MemoryAgent
from .knowledge.knowledge_agent import KnowledgeAgent
from .admin.admin_agent import AdminAgent

__all__ = [
    "AuthAgent",
    "ChatAgent",
    "ConversationAgent",
    "ProviderAgent",
    "ToolAgent",
    "VoiceAgent",
    "MemoryAgent",
    "KnowledgeAgent",
    "AdminAgent",
]
