"""Context blocks API endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from backend.auth.dependencies import get_current_user
from backend.db import get_db
from backend.db.models import ContextBlock, Project, Conversation, User

router = APIRouter(prefix="/api/context-blocks", tags=["context"])


class ContextBlockModel(BaseModel):
    id: str
    project_id: Optional[str]
    conversation_id: Optional[str]
    title: str
    content: str
    enabled: bool
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class ContextBlockCreateRequest(BaseModel):
    project_id: Optional[str] = None
    conversation_id: Optional[str] = None
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    enabled: bool = True


class ContextBlockUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    content: Optional[str] = None
    enabled: Optional[bool] = None


def _validate_scope(project_id: Optional[str], conversation_id: Optional[str]):
    if bool(project_id) == bool(conversation_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide exactly one of project_id or conversation_id",
        )


@router.get("", response_model=List[ContextBlockModel])
async def list_context_blocks(
    project_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _validate_scope(project_id, conversation_id)
    query = db.query(ContextBlock).filter(ContextBlock.user_id == current_user.id)
    if project_id:
        query = query.filter(ContextBlock.project_id == project_id)
    if conversation_id:
        query = query.filter(ContextBlock.conversation_id == conversation_id)
    blocks = query.order_by(ContextBlock.updated_at.desc()).all()
    return [
        ContextBlockModel(
            id=b.id,
            project_id=b.project_id,
            conversation_id=b.conversation_id,
            title=b.title,
            content=b.content,
            enabled=b.enabled,
            created_at=b.created_at.isoformat(),
            updated_at=b.updated_at.isoformat(),
        )
        for b in blocks
    ]


@router.post("", response_model=ContextBlockModel)
async def create_context_block(
    body: ContextBlockCreateRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _validate_scope(body.project_id, body.conversation_id)
    if body.project_id:
        exists = db.query(Project).filter(Project.id == body.project_id, Project.user_id == current_user.id).first()
        if not exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if body.conversation_id:
        exists = (
            db.query(Conversation)
            .filter(Conversation.id == body.conversation_id, Conversation.user_id == current_user.id)
            .first()
        )
        if not exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    block = ContextBlock(
        user_id=current_user.id,
        project_id=body.project_id,
        conversation_id=body.conversation_id,
        title=body.title,
        content=body.content,
        enabled=body.enabled,
    )
    db.add(block)
    db.commit()
    db.refresh(block)
    return ContextBlockModel(
        id=block.id,
        project_id=block.project_id,
        conversation_id=block.conversation_id,
        title=block.title,
        content=block.content,
        enabled=block.enabled,
        created_at=block.created_at.isoformat(),
        updated_at=block.updated_at.isoformat(),
    )


@router.patch("/{block_id}", response_model=ContextBlockModel)
async def update_context_block(
    block_id: str,
    body: ContextBlockUpdateRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    block = (
        db.query(ContextBlock)
        .filter(ContextBlock.id == block_id, ContextBlock.user_id == current_user.id)
        .first()
    )
    if not block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Context block not found")

    if body.title:
        block.title = body.title
    if body.content is not None:
        block.content = body.content
    if body.enabled is not None:
        block.enabled = body.enabled
    db.commit()
    db.refresh(block)
    return ContextBlockModel(
        id=block.id,
        project_id=block.project_id,
        conversation_id=block.conversation_id,
        title=block.title,
        content=block.content,
        enabled=block.enabled,
        created_at=block.created_at.isoformat(),
        updated_at=block.updated_at.isoformat(),
    )


@router.delete("/{block_id}")
async def delete_context_block(
    block_id: str,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    block = (
        db.query(ContextBlock)
        .filter(ContextBlock.id == block_id, ContextBlock.user_id == current_user.id)
        .first()
    )
    if not block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Context block not found")
    db.delete(block)
    db.commit()
    return {"status": "deleted"}
