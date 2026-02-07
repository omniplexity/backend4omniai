"""Projects API endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from backend.auth.dependencies import get_current_user
from backend.db import get_db
from backend.db.models import Project, Conversation, User

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectModel(BaseModel):
    id: str
    name: str
    instructions: Optional[str]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    instructions: Optional[str] = None


class ProjectUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    instructions: Optional[str] = None


@router.get("", response_model=List[ProjectModel])
async def list_projects(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    projects = (
        db.query(Project)
        .filter(Project.user_id == current_user.id)
        .order_by(Project.updated_at.desc())
        .all()
    )
    return [
        ProjectModel(
            id=p.id,
            name=p.name,
            instructions=p.instructions,
            created_at=p.created_at.isoformat(),
            updated_at=p.updated_at.isoformat(),
        )
        for p in projects
    ]


@router.post("", response_model=ProjectModel)
async def create_project(
    body: ProjectCreateRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = Project(
        user_id=current_user.id,
        name=body.name,
        instructions=body.instructions,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return ProjectModel(
        id=project.id,
        name=project.name,
        instructions=project.instructions,
        created_at=project.created_at.isoformat(),
        updated_at=project.updated_at.isoformat(),
    )


@router.patch("/{project_id}", response_model=ProjectModel)
async def update_project(
    project_id: str,
    body: ProjectUpdateRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.user_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if body.name:
        project.name = body.name
    if body.instructions is not None:
        project.instructions = body.instructions
    db.commit()
    db.refresh(project)
    return ProjectModel(
        id=project.id,
        name=project.name,
        instructions=project.instructions,
        created_at=project.created_at.isoformat(),
        updated_at=project.updated_at.isoformat(),
    )


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.user_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    db.query(Conversation).filter(
        Conversation.user_id == current_user.id,
        Conversation.project_id == project.id,
    ).update({Conversation.project_id: None})
    db.delete(project)
    db.commit()
    return {"status": "deleted"}
