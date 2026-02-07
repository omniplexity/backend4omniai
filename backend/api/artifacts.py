"""Artifacts API endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from backend.auth.dependencies import get_current_user
from backend.db import get_db
from backend.db.models import Artifact, Conversation, Project, User

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


class ArtifactModel(BaseModel):
    id: str
    project_id: Optional[str]
    conversation_id: str
    type: str
    title: Optional[str]
    content: str
    language: Optional[str]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class ArtifactCreateRequest(BaseModel):
    conversation_id: str
    project_id: Optional[str] = None
    type: str = Field(min_length=1, max_length=64)
    title: Optional[str] = None
    content: str = Field(min_length=1)
    language: Optional[str] = None


class ArtifactUpdateRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    language: Optional[str] = None


@router.get("", response_model=List[ArtifactModel])
async def list_artifacts(
    conversation_id: Optional[str] = None,
    project_id: Optional[str] = None,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Artifact).filter(Artifact.user_id == current_user.id)
    if conversation_id:
        query = query.filter(Artifact.conversation_id == conversation_id)
    if project_id:
        query = query.filter(Artifact.project_id == project_id)
    artifacts = query.order_by(Artifact.updated_at.desc()).all()
    return [
        ArtifactModel(
            id=a.id,
            project_id=a.project_id,
            conversation_id=a.conversation_id,
            type=a.type,
            title=a.title,
            content=a.content,
            language=a.language,
            created_at=a.created_at.isoformat(),
            updated_at=a.updated_at.isoformat(),
        )
        for a in artifacts
    ]


@router.post("", response_model=ArtifactModel)
async def create_artifact(
    body: ArtifactCreateRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = (
        db.query(Conversation)
        .filter(Conversation.id == body.conversation_id, Conversation.user_id == current_user.id)
        .first()
    )
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    if body.project_id:
        project = (
            db.query(Project)
            .filter(Project.id == body.project_id, Project.user_id == current_user.id)
            .first()
        )
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    artifact = Artifact(
        user_id=current_user.id,
        project_id=body.project_id or conversation.project_id,
        conversation_id=body.conversation_id,
        type=body.type,
        title=body.title,
        content=body.content,
        language=body.language,
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return ArtifactModel(
        id=artifact.id,
        project_id=artifact.project_id,
        conversation_id=artifact.conversation_id,
        type=artifact.type,
        title=artifact.title,
        content=artifact.content,
        language=artifact.language,
        created_at=artifact.created_at.isoformat(),
        updated_at=artifact.updated_at.isoformat(),
    )


@router.patch("/{artifact_id}", response_model=ArtifactModel)
async def update_artifact(
    artifact_id: str,
    body: ArtifactUpdateRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    artifact = (
        db.query(Artifact)
        .filter(Artifact.id == artifact_id, Artifact.user_id == current_user.id)
        .first()
    )
    if not artifact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    if body.title is not None:
        artifact.title = body.title
    if body.content is not None:
        artifact.content = body.content
    if body.language is not None:
        artifact.language = body.language
    db.commit()
    db.refresh(artifact)
    return ArtifactModel(
        id=artifact.id,
        project_id=artifact.project_id,
        conversation_id=artifact.conversation_id,
        type=artifact.type,
        title=artifact.title,
        content=artifact.content,
        language=artifact.language,
        created_at=artifact.created_at.isoformat(),
        updated_at=artifact.updated_at.isoformat(),
    )


@router.delete("/{artifact_id}")
async def delete_artifact(
    artifact_id: str,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    artifact = (
        db.query(Artifact)
        .filter(Artifact.id == artifact_id, Artifact.user_id == current_user.id)
        .first()
    )
    if not artifact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    db.delete(artifact)
    db.commit()
    return {"status": "deleted"}
