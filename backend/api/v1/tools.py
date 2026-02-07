"""v1 tools endpoint.

Exposes Tool Agent interfaces for tool management and execution.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from backend.auth.dependencies import get_current_user
from backend.config import get_settings
from backend.db import get_db
from backend.db.models import User, ToolReceipt
from backend.agents.tool import ToolAgent, ToolType, ToolSettings

router = APIRouter(prefix="/tools", tags=["v1-tools"])


class ToolInfo(BaseModel):
    """Tool information."""
    id: str
    name: str
    description: str
    category: str
    enabled: bool = True


class ToolSettingsResponse(BaseModel):
    """Tool settings response."""
    web_enabled: bool = True
    web_depth: int = 3
    files_enabled: bool = True
    code_enabled: bool = True
    vision_enabled: bool = True


class ToolExecuteRequest(BaseModel):
    """Tool execution request."""
    tool_id: str
    input: Dict[str, Any] = Field(default_factory=dict)


class ToolExecuteResponse(BaseModel):
    """Tool execution response."""
    receipt_id: str
    status: str
    output: Optional[str] = None
    error: Optional[str] = None


class ToolReceiptResponse(BaseModel):
    """Tool receipt response."""
    id: str
    tool_id: str
    status: str
    input: Optional[Dict[str, Any]]
    output: Optional[Dict[str, Any]]
    error: Optional[str]
    created_at: str


def _create_tool_agent(db: DBSession, request: Request) -> ToolAgent:
    """Create a Tool Agent instance."""
    settings = get_settings()
    # Extract tool settings from settings
    tool_settings = {
        "web_enabled": settings.tool_web_enabled if hasattr(settings, "tool_web_enabled") else True,
        "files_enabled": settings.tool_files_enabled if hasattr(settings, "tool_files_enabled") else True,
        "code_enabled": settings.tool_code_enabled if hasattr(settings, "tool_code_enabled") else True,
        "vision_enabled": settings.tool_vision_enabled if hasattr(settings, "tool_vision_enabled") else True,
    }
    return ToolAgent(db, tool_settings)


# Define available tools registry
TOOLS_REGISTRY = {
    ToolType.WEB.value: {
        "name": "Web Search",
        "description": "Search the web for information",
        "category": "search",
    },
    ToolType.FILES.value: {
        "name": "File Operations",
        "description": "Read and write files",
        "category": "files",
    },
    ToolType.CODE.value: {
        "name": "Code Execution",
        "description": "Execute code snippets",
        "category": "developer",
    },
    ToolType.VISION.value: {
        "name": "Vision",
        "description": "Analyze images",
        "category": "multimodal",
    },
}


@router.get("", response_model=List[ToolInfo])
async def list_tools(
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[ToolInfo]:
    """List available tools."""
    agent = _create_tool_agent(db, request)
    
    results = []
    for tool_id, info in TOOLS_REGISTRY.items():
        enabled = agent.is_tool_enabled(current_user, ToolType(tool_id))
        results.append(ToolInfo(
            id=tool_id,
            name=info["name"],
            description=info["description"],
            category=info["category"],
            enabled=enabled,
        ))
    
    return results


@router.get("/settings", response_model=ToolSettingsResponse)
async def get_tool_settings(
    conversation_id: Optional[str] = None,
    request: Request = None,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ToolSettingsResponse:
    """Get effective tool settings."""
    agent = _create_tool_agent(db, request)
    settings = agent.get_tool_settings(current_user, conversation_id)
    
    return ToolSettingsResponse(
        web_enabled=settings.web_enabled,
        web_depth=settings.web_depth,
        files_enabled=settings.files_enabled,
        code_enabled=settings.code_enabled,
        vision_enabled=settings.vision_enabled,
    )


@router.patch("/settings")
async def update_tool_settings(
    body: ToolSettingsResponse,
    conversation_id: Optional[str] = None,
    request: Request = None,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, str]:
    """Update tool settings."""
    agent = _create_tool_agent(db, request)
    
    # Update each setting
    if hasattr(body, "web_enabled"):
        agent.set_tool_enabled(current_user, ToolType.WEB, body.web_enabled, conversation_id)
    if hasattr(body, "files_enabled"):
        agent.set_tool_enabled(current_user, ToolType.FILES, body.files_enabled, conversation_id)
    if hasattr(body, "code_enabled"):
        agent.set_tool_enabled(current_user, ToolType.CODE, body.code_enabled, conversation_id)
    if hasattr(body, "vision_enabled"):
        agent.set_tool_enabled(current_user, ToolType.VISION, body.vision_enabled, conversation_id)
    
    return {"status": "updated"}


@router.post("/execute", response_model=ToolExecuteResponse)
async def execute_tool(
    body: ToolExecuteRequest,
    conversation_id: Optional[str] = None,
    request: Request = None,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ToolExecuteResponse:
    """Execute a tool."""
    agent = _create_tool_agent(db, request)
    
    # Validate tool exists
    if body.tool_id not in TOOLS_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool not found: {body.tool_id}",
        )
    
    # Check if tool is enabled
    try:
        tool_type = ToolType(body.tool_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tool type: {body.tool_id}",
        )
    
    if not agent.is_tool_enabled(current_user, tool_type, conversation_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Tool is disabled: {body.tool_id}",
        )
    
    # Execute tool
    result = agent.execute_tool(
        user=current_user,
        tool_id=body.tool_id,
        input_payload=body.input,
        conversation_id=conversation_id,
    )
    
    return ToolExecuteResponse(
        receipt_id="",  # Would need to track receipt
        status="completed" if result.success else "failed",
        output=result.output,
        error=result.error,
    )


@router.get("/receipts", response_model=List[ToolReceiptResponse])
async def list_receipts(
    conversation_id: Optional[str] = None,
    limit: int = 50,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[ToolReceiptResponse]:
    """List tool execution receipts."""
    query = db.query(ToolReceipt).filter(ToolReceipt.user_id == current_user.id)
    
    if conversation_id:
        query = query.filter(ToolReceipt.conversation_id == conversation_id)
    
    receipts = query.order_by(ToolReceipt.created_at.desc()).limit(limit).all()
    
    return [
        ToolReceiptResponse(
            id=r.id,
            tool_id=r.tool_id,
            status=r.status,
            input=r.input_payload,
            output=r.output_payload,
            error=r.error_message,
            created_at=r.created_at.isoformat(),
        )
        for r in receipts
    ]


@router.get("/receipts/{receipt_id}", response_model=ToolReceiptResponse)
async def get_receipt(
    receipt_id: str,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ToolReceiptResponse:
    """Get a tool execution receipt."""
    receipt = (
        db.query(ToolReceipt)
        .filter(ToolReceipt.id == receipt_id, ToolReceipt.user_id == current_user.id)
        .first()
    )
    
    if not receipt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt not found",
        )
    
    return ToolReceiptResponse(
        id=receipt.id,
        tool_id=receipt.tool_id,
        status=receipt.status,
        input=receipt.input_payload,
        output=receipt.output_payload,
        error=receipt.error_message,
        created_at=receipt.created_at.isoformat(),
    )
