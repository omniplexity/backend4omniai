"""Tools API endpoints."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from backend.auth.dependencies import get_current_user, get_optional_user
from backend.db import get_db
from backend.db.models import ToolFavorite, ToolReceipt, ToolSetting, User

router = APIRouter(tags=["tools"])


class ToolDescriptor(BaseModel):
    id: str
    name: str
    description: str
    category: str
    enabled: bool = True
    favorite: bool = False


class ToolRunRequest(BaseModel):
    tool_id: str
    input: Dict[str, Any] = Field(default_factory=dict)
    conversation_id: Optional[str] = None


class ToolReceiptResponse(BaseModel):
    id: str
    tool_id: str
    status: str
    input: Optional[Dict[str, Any]]
    output: Optional[Dict[str, Any]]
    error: Optional[str]
    conversation_id: Optional[str]
    created_at: str


TOOLS_REGISTRY = {
    "calculator": {
        "name": "Calculator",
        "description": "Evaluate basic math expressions",
        "category": "productivity",
    },
    "datetime": {
        "name": "DateTime",
        "description": "Return current server time",
        "category": "system",
    },
    "echo": {
        "name": "Echo",
        "description": "Echo back input payload",
        "category": "utilities",
    },
}


def build_tools_list(user: Optional[User], db: DBSession) -> List[ToolDescriptor]:
    favorites = set()
    if user:
        favorites = {
            fav.tool_id
            for fav in db.query(ToolFavorite).filter(ToolFavorite.user_id == user.id).all()
        }

    tools = []
    for tool_id, info in TOOLS_REGISTRY.items():
        tools.append(
            ToolDescriptor(
                id=tool_id,
                name=info["name"],
                description=info["description"],
                category=info["category"],
                enabled=True,
                favorite=tool_id in favorites,
            )
        )
    return tools


@router.get("/tools")
async def list_tools(
    db: DBSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    tools = build_tools_list(current_user, db)
    return {"tools": [tool.model_dump() for tool in tools]}


@router.post("/tools/run")
async def run_tool(
    body: ToolRunRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.tool_id not in TOOLS_REGISTRY:
        raise HTTPException(status_code=404, detail="Tool not found")

    output: Dict[str, Any]
    if body.tool_id == "calculator":
        expression = body.input.get("expression") or body.input.get("value")
        if not expression:
            raise HTTPException(status_code=400, detail="Expression required")
        try:
            result = eval(str(expression), {"__builtins__": {}}, {})
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid expression: {exc}")
        output = {"result": result}
    elif body.tool_id == "datetime":
        output = {"now": datetime.utcnow().isoformat() + "Z"}
    else:
        output = {"echo": body.input}

    receipt = ToolReceipt(
        user_id=current_user.id,
        conversation_id=body.conversation_id,
        tool_id=body.tool_id,
        status="completed",
        input_payload=body.input,
        output_payload=output,
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)

    return {
        "receipt_id": receipt.id,
        "status": receipt.status,
        "output": output,
    }


@router.get("/tools/receipts")
async def list_receipts(
    conversation_id: Optional[str] = None,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(ToolReceipt).filter(ToolReceipt.user_id == current_user.id)
    if conversation_id:
        query = query.filter(ToolReceipt.conversation_id == conversation_id)
    receipts = query.order_by(ToolReceipt.created_at.desc()).limit(100).all()

    return {
        "receipts": [
            {
                "id": r.id,
                "tool_id": r.tool_id,
                "status": r.status,
                "conversation_id": r.conversation_id,
                "created_at": r.created_at.isoformat(),
            }
            for r in receipts
        ]
    }


@router.get("/tools/receipts/{receipt_id}")
async def get_receipt(
    receipt_id: str,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    receipt = (
        db.query(ToolReceipt)
        .filter(ToolReceipt.id == receipt_id, ToolReceipt.user_id == current_user.id)
        .first()
    )
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")

    return ToolReceiptResponse(
        id=receipt.id,
        tool_id=receipt.tool_id,
        status=receipt.status,
        input=receipt.input_payload,
        output=receipt.output_payload,
        error=receipt.error_message,
        conversation_id=receipt.conversation_id,
        created_at=receipt.created_at.isoformat(),
    ).model_dump()


@router.post("/tools/receipts/{receipt_id}/retry")
async def retry_receipt(
    receipt_id: str,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    receipt = (
        db.query(ToolReceipt)
        .filter(ToolReceipt.id == receipt_id, ToolReceipt.user_id == current_user.id)
        .first()
    )
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")

    new_receipt = ToolReceipt(
        user_id=current_user.id,
        conversation_id=receipt.conversation_id,
        tool_id=receipt.tool_id,
        status="completed",
        input_payload=receipt.input_payload,
        output_payload=receipt.output_payload,
    )
    db.add(new_receipt)
    db.commit()
    db.refresh(new_receipt)

    return {"receipt_id": new_receipt.id, "status": new_receipt.status}


@router.post("/tools/enable")
async def enable_tool(
    body: ToolRunRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    setting = (
        db.query(ToolSetting)
        .filter(
            ToolSetting.user_id == current_user.id,
            ToolSetting.tool_id == body.tool_id,
            ToolSetting.conversation_id == body.conversation_id,
        )
        .first()
    )
    if not setting:
        setting = ToolSetting(
            user_id=current_user.id,
            tool_id=body.tool_id,
            conversation_id=body.conversation_id,
            enabled=True,
        )
        db.add(setting)
    else:
        setting.enabled = True
    db.commit()
    return {"status": "enabled"}


@router.post("/tools/disable")
async def disable_tool(
    body: ToolRunRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    setting = (
        db.query(ToolSetting)
        .filter(
            ToolSetting.user_id == current_user.id,
            ToolSetting.tool_id == body.tool_id,
            ToolSetting.conversation_id == body.conversation_id,
        )
        .first()
    )
    if not setting:
        setting = ToolSetting(
            user_id=current_user.id,
            tool_id=body.tool_id,
            conversation_id=body.conversation_id,
            enabled=False,
        )
        db.add(setting)
    else:
        setting.enabled = False
    db.commit()
    return {"status": "disabled"}


@router.post("/tools/favorite")
async def toggle_favorite(
    body: ToolRunRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    favorite = (
        db.query(ToolFavorite)
        .filter(ToolFavorite.user_id == current_user.id, ToolFavorite.tool_id == body.tool_id)
        .first()
    )
    if favorite:
        db.delete(favorite)
        db.commit()
        return {"favorite": False}

    favorite = ToolFavorite(user_id=current_user.id, tool_id=body.tool_id)
    db.add(favorite)
    db.commit()
    return {"favorite": True}


@router.get("/tools/mcp-servers")
async def list_mcp_servers(
    current_user: User = Depends(get_current_user),
):
    return {"servers": []}


@router.get("/tools/connectors")
async def list_connectors(
    current_user: User = Depends(get_current_user),
):
    return {"connectors": []}


@router.get("/tools/capabilities")
async def tool_capabilities():
    from backend.services.tool_capabilities_service import get_tool_capabilities

    return get_tool_capabilities()
