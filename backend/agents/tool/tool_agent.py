"""Tool Agent.

Manages tool execution, settings, and policy enforcement.
Provides interfaces for file operations, code execution, web browsing, etc.
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.orm import Session as DBSession

from backend.db.models import User, ToolSetting, ToolReceipt
from backend.core.logging import get_logger

logger = get_logger(__name__)


class ToolType(str, Enum):
    """Tool types."""
    WEB = "web"
    FILES = "files"
    CODE = "code"
    VISION = "vision"
    MEMORY = "memory"
    KNOWLEDGE = "knowledge"


@dataclass
class ToolResult:
    """Result from tool execution."""
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ToolSettings:
    """Tool settings for a conversation."""
    web_enabled: bool = True
    web_depth: int = 3
    files_enabled: bool = True
    code_enabled: bool = True
    vision_enabled: bool = True


class ToolAgent:
    """Agent for managing tool execution."""

    def __init__(self, db: DBSession, settings: Dict[str, Any] = None):
        """Initialize the Tool Agent.
        
        Args:
            db: Database session
            settings: Global tool settings
        """
        self.db = db
        self.global_settings = settings or {}

    def is_tool_enabled(
        self,
        user: User,
        tool_type: ToolType,
        conversation_id: Optional[str] = None,
    ) -> bool:
        """Check if a tool is enabled for a user/conversation.
        
        Args:
            user: User to check
            tool_type: Tool type to check
            conversation_id: Optional conversation ID
            
        Returns:
            True if enabled, False otherwise
        """
        # Check global settings first
        global_enabled = self.global_settings.get(f"{tool_type.value}_enabled", True)
        if not global_enabled:
            return False
        
        # Check per-conversation settings
        if conversation_id:
            setting = (
                self.db.query(ToolSetting)
                .filter(
                    ToolSetting.user_id == user.id,
                    ToolSetting.conversation_id == conversation_id,
                    ToolSetting.tool_id == tool_type.value,
                )
                .first()
            )
            if setting:
                return setting.enabled
        
        # Default to global setting
        return global_enabled

    def get_tool_settings(
        self,
        user: User,
        conversation_id: Optional[str] = None,
    ) -> ToolSettings:
        """Get effective tool settings for a user/conversation.
        
        Args:
            user: User to get settings for
            conversation_id: Optional conversation ID
            
        Returns:
            ToolSettings with effective values
        """
        settings = ToolSettings()
        
        # Get per-conversation overrides
        if conversation_id:
            overrides = (
                self.db.query(ToolSetting)
                .filter(
                    ToolSetting.user_id == user.id,
                    ToolSetting.conversation_id == conversation_id,
                )
                .all()
            )
            for override in overrides:
                if override.tool_id == ToolType.WEB.value:
                    settings.web_enabled = override.enabled
                elif override.tool_id == ToolType.FILES.value:
                    settings.files_enabled = override.enabled
                elif override.tool_id == ToolType.CODE.value:
                    settings.code_enabled = override.enabled
                elif override.tool_id == ToolType.VISION.value:
                    settings.vision_enabled = override.enabled
        
        return settings

    def set_tool_enabled(
        self,
        user: User,
        tool_type: ToolType,
        enabled: bool,
        conversation_id: Optional[str] = None,
    ) -> ToolSetting:
        """Enable or disable a tool for a user/conversation.
        
        Args:
            user: User to update
            tool_type: Tool type to update
            enabled: New enabled state
            conversation_id: Optional conversation ID
            
        Returns:
            Updated or created ToolSetting
        """
        setting = (
            self.db.query(ToolSetting)
            .filter(
                ToolSetting.user_id == user.id,
                ToolSetting.conversation_id == conversation_id,
                ToolSetting.tool_id == tool_type.value,
            )
            .first()
        )
        
        if setting:
            setting.enabled = enabled
        else:
            setting = ToolSetting(
                user_id=user.id,
                conversation_id=conversation_id,
                tool_id=tool_type.value,
                enabled=enabled,
            )
            self.db.add(setting)
        
        self.db.commit()
        self.db.refresh(setting)
        
        return setting

    def execute_tool(
        self,
        user: User,
        tool_id: str,
        input_payload: Dict[str, Any],
        conversation_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> ToolResult:
        """Execute a tool.
        
        Args:
            user: User executing the tool
            tool_id: Tool to execute
            input_payload: Tool input
            conversation_id: Optional conversation ID
            run_id: Optional run ID for tracking
            
        Returns:
            ToolResult with output or error
        """
        # Create receipt
        receipt = ToolReceipt(
            user_id=user.id,
            conversation_id=conversation_id,
            tool_id=tool_id,
            status="running",
            input_payload=input_payload,
            run_id=run_id,
        )
        self.db.add(receipt)
        self.db.commit()
        self.db.refresh(receipt)
        
        try:
            # Execute based on tool type
            if tool_id == ToolType.WEB.value:
                result = self._execute_web_tool(input_payload)
            elif tool_id == ToolType.FILES.value:
                result = self._execute_files_tool(input_payload)
            elif tool_id == ToolType.CODE.value:
                result = self._execute_code_tool(input_payload)
            elif tool_id == ToolType.VISION.value:
                result = self._execute_vision_tool(input_payload)
            else:
                result = ToolResult(success=False, error=f"Unknown tool: {tool_id}")
            
            # Update receipt
            receipt.status = "completed" if result.success else "failed"
            receipt.output_payload = {"output": result.output} if result.success else None
            receipt.error_message = result.error
            self.db.commit()
            
            return result
            
        except Exception as e:
            receipt.status = "failed"
            receipt.error_message = str(e)
            self.db.commit()
            
            logger.error(f"Tool execution failed: {e}")
            return ToolResult(success=False, error=str(e))

    def _execute_web_tool(self, input_payload: Dict[str, Any]) -> ToolResult:
        """Execute web browsing tool.
        
        Args:
            input_payload: Tool input
            
        Returns:
            ToolResult with content
        """
        url = input_payload.get("url")
        if not url:
            return