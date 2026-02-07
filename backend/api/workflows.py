"""Workflow API endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from backend.auth.dependencies import get_current_user
from backend.core.logging import get_logger
from backend.db import get_db
from backend.db.models import User, WorkflowRun, WorkflowStep, WorkflowTemplate
from backend.providers.registry import ProviderRegistry
from backend.services.workflow_service import WorkflowService
from backend.services.workflow_templates import get_builtin_templates

logger = get_logger(__name__)
router = APIRouter(prefix="/api/workflows", tags=["workflows"])


# ---------- Pydantic models ----------

class StepDefinition(BaseModel):
    seq: int
    type: str = "custom"
    title: str
    prompt_template: Optional[str] = None


class TemplateResponse(BaseModel):
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    is_builtin: bool = False
    steps: List[Dict[str, Any]]
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CreateTemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = None
    steps: List[StepDefinition] = Field(min_length=1)


class UpdateTemplateRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    steps: Optional[List[StepDefinition]] = None


class StartRunRequest(BaseModel):
    template_id: Optional[str] = None
    title: Optional[str] = None
    goal: str = Field(min_length=1)
    steps: Optional[List[StepDefinition]] = None
    project_id: Optional[str] = None
    conversation_id: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None


class StepResponse(BaseModel):
    id: str
    seq: int
    type: str
    title: str
    status: str
    output_text: Optional[str] = None
    tokens_used: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class RunResponse(BaseModel):
    id: str
    title: str
    status: str
    template_id: Optional[str] = None
    project_id: Optional[str] = None
    conversation_id: Optional[str] = None
    input_json: Optional[Dict[str, Any]] = None
    output_json: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    steps: List[StepResponse] = []
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RunListItem(BaseModel):
    id: str
    title: str
    status: str
    template_id: Optional[str] = None
    project_id: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------- Helpers ----------

def _get_registry(request: Request) -> ProviderRegistry:
    registry = getattr(request.app.state, "provider_registry", None)
    if not registry:
        raise HTTPException(status_code=503, detail="Provider registry not available")
    return registry


def _run_to_response(run: WorkflowRun) -> RunResponse:
    return RunResponse(
        id=run.id,
        title=run.title,
        status=run.status,
        template_id=run.template_id,
        project_id=run.project_id,
        conversation_id=run.conversation_id,
        input_json=run.input_json,
        output_json=run.output_json,
        error_message=run.error_message,
        steps=[
            StepResponse(
                id=s.id,
                seq=s.seq,
                type=s.type,
                title=s.title,
                status=s.status,
                output_text=s.output_text,
                tokens_used=s.tokens_used,
                started_at=s.started_at,
                completed_at=s.completed_at,
                error_message=s.error_message,
            )
            for s in sorted(run.steps, key=lambda s: s.seq)
        ],
        created_at=run.created_at,
        updated_at=run.updated_at,
        completed_at=run.completed_at,
    )


# ---------- Template endpoints ----------

@router.get("/templates", response_model=List[TemplateResponse])
async def list_templates(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List available workflow templates (built-in + user-created)."""
    # Built-in templates (not stored in DB)
    builtins = [
        TemplateResponse(
            id=f"builtin:{idx}",
            name=t["name"],
            description=t["description"],
            category=t["category"],
            is_builtin=True,
            steps=t["steps"],
        )
        for idx, t in enumerate(get_builtin_templates())
    ]

    # User-created templates
    user_templates = (
        db.query(WorkflowTemplate)
        .filter(WorkflowTemplate.user_id == current_user.id)
        .order_by(WorkflowTemplate.created_at.desc())
        .all()
    )
    user_responses = [
        TemplateResponse(
            id=t.id,
            name=t.name,
            description=t.description,
            category=t.category,
            is_builtin=False,
            steps=t.steps_json,
            created_at=t.created_at,
        )
        for t in user_templates
    ]

    return builtins + user_responses


@router.post("/templates", response_model=TemplateResponse, status_code=201)
async def create_template(
    payload: CreateTemplateRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a custom workflow template."""
    template = WorkflowTemplate(
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
        category=payload.category,
        steps_json=[s.model_dump() for s in payload.steps],
        is_builtin=False,
    )
    db.add(template)
    db.commit()
    db.refresh(template)

    return TemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        category=template.category,
        is_builtin=False,
        steps=template.steps_json,
        created_at=template.created_at,
    )


@router.get("/templates/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: str,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a workflow template by ID."""
    # Check built-in templates
    if template_id.startswith("builtin:"):
        idx = int(template_id.split(":")[1])
        builtins = get_builtin_templates()
        if 0 <= idx < len(builtins):
            t = builtins[idx]
            return TemplateResponse(
                id=template_id,
                name=t["name"],
                description=t["description"],
                category=t["category"],
                is_builtin=True,
                steps=t["steps"],
            )
        raise HTTPException(status_code=404, detail="Template not found")

    template = (
        db.query(WorkflowTemplate)
        .filter(WorkflowTemplate.id == template_id, WorkflowTemplate.user_id == current_user.id)
        .first()
    )
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return TemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        category=template.category,
        is_builtin=False,
        steps=template.steps_json,
        created_at=template.created_at,
    )


@router.patch("/templates/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: str,
    payload: UpdateTemplateRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a custom workflow template (user-owned only)."""
    if template_id.startswith("builtin:"):
        raise HTTPException(status_code=403, detail="Cannot modify built-in templates")

    template = (
        db.query(WorkflowTemplate)
        .filter(WorkflowTemplate.id == template_id, WorkflowTemplate.user_id == current_user.id)
        .first()
    )
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if payload.name is not None:
        template.name = payload.name
    if payload.description is not None:
        template.description = payload.description
    if payload.steps is not None:
        template.steps_json = [s.model_dump() for s in payload.steps]

    db.commit()
    db.refresh(template)

    return TemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        category=template.category,
        is_builtin=False,
        steps=template.steps_json,
        created_at=template.created_at,
    )


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: str,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a custom workflow template."""
    if template_id.startswith("builtin:"):
        raise HTTPException(status_code=403, detail="Cannot delete built-in templates")

    template = (
        db.query(WorkflowTemplate)
        .filter(WorkflowTemplate.id == template_id, WorkflowTemplate.user_id == current_user.id)
        .first()
    )
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    db.delete(template)
    db.commit()
    return {"message": "Template deleted"}


# ---------- Run endpoints ----------

@router.post("/run", response_model=RunResponse, status_code=201)
async def start_run(
    payload: StartRunRequest,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start a new workflow run from a template or inline steps."""
    registry = _get_registry(request)
    service = WorkflowService(db, registry)

    # Resolve step definitions
    steps_definition: List[Dict[str, Any]]

    if payload.template_id:
        # Load from template
        if payload.template_id.startswith("builtin:"):
            idx = int(payload.template_id.split(":")[1])
            builtins = get_builtin_templates()
            if idx < 0 or idx >= len(builtins):
                raise HTTPException(status_code=404, detail="Template not found")
            steps_definition = builtins[idx]["steps"]
            title = payload.title or builtins[idx]["name"]
        else:
            template = (
                db.query(WorkflowTemplate)
                .filter(
                    WorkflowTemplate.id == payload.template_id,
                    WorkflowTemplate.user_id == current_user.id,
                )
                .first()
            )
            if not template:
                raise HTTPException(status_code=404, detail="Template not found")
            steps_definition = template.steps_json
            title = payload.title or template.name
    elif payload.steps:
        steps_definition = [s.model_dump() for s in payload.steps]
        title = payload.title or "Custom Workflow"
    else:
        raise HTTPException(
            status_code=400,
            detail="Either template_id or steps must be provided",
        )

    run = service.create_run(
        user=current_user,
        title=title,
        steps_definition=steps_definition,
        input_data={"goal": payload.goal},
        template_id=payload.template_id if payload.template_id and not payload.template_id.startswith("builtin:") else None,
        project_id=payload.project_id,
        conversation_id=payload.conversation_id,
        provider_name=payload.provider,
        model=payload.model,
    )

    # Start execution in background
    service.start_run_async(run.id)

    return _run_to_response(run)


@router.get("/runs", response_model=List[RunListItem])
async def list_runs(
    project_id: Optional[str] = None,
    run_status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    request: Request = None,
):
    """List workflow runs for the current user."""
    registry = _get_registry(request)
    service = WorkflowService(db, registry)
    runs = service.list_runs(
        user=current_user,
        project_id=project_id,
        status=run_status,
        limit=limit,
        offset=offset,
    )
    return [
        RunListItem(
            id=r.id,
            title=r.title,
            status=r.status,
            template_id=r.template_id,
            project_id=r.project_id,
            created_at=r.created_at,
            completed_at=r.completed_at,
        )
        for r in runs
    ]


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: str,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    request: Request = None,
):
    """Get a workflow run with all steps."""
    registry = _get_registry(request)
    service = WorkflowService(db, registry)
    run = service.get_run(run_id, current_user)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    return _run_to_response(run)


@router.get("/runs/{run_id}/stream")
async def stream_run(
    run_id: str,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    request: Request = None,
):
    """SSE stream of workflow run progress."""
    import asyncio
    import json

    registry = _get_registry(request)
    service = WorkflowService(db, registry)
    run = service.get_run(run_id, current_user)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")

    async def event_generator():
        """Poll run status and emit SSE events."""
        SessionLocal = get_session_local()
        poll_db = SessionLocal()
        seen_step_statuses: Dict[str, str] = {}

        try:
            while True:
                poll_run = poll_db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
                if not poll_run:
                    break

                steps = (
                    poll_db.query(WorkflowStep)
                    .filter(WorkflowStep.run_id == run_id)
                    .order_by(WorkflowStep.seq)
                    .all()
                )

                # Emit step updates
                for step in steps:
                    key = step.id
                    if seen_step_statuses.get(key) != step.status:
                        seen_step_statuses[key] = step.status
                        data = json.dumps({
                            "type": "step_update",
                            "step": {
                                "id": step.id,
                                "seq": step.seq,
                                "type": step.type,
                                "title": step.title,
                                "status": step.status,
                                "output_text": step.output_text[:500] if step.output_text else None,
                                "error_message": step.error_message,
                            },
                        })
                        yield f"data: {data}\n\n"

                # Emit run status
                data = json.dumps({
                    "type": "run_status",
                    "run_id": poll_run.id,
                    "status": poll_run.status,
                })
                yield f"data: {data}\n\n"

                if poll_run.status in ("completed", "failed", "cancelled"):
                    # Final event with output
                    data = json.dumps({
                        "type": "run_complete",
                        "run_id": poll_run.id,
                        "status": poll_run.status,
                        "output": poll_run.output_json,
                        "error_message": poll_run.error_message,
                    })
                    yield f"data: {data}\n\n"
                    break

                await asyncio.sleep(1)
        finally:
            poll_db.close()

    from backend.db.database import get_session_local

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/runs/{run_id}/cancel", response_model=RunResponse)
async def cancel_run(
    run_id: str,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    request: Request = None,
):
    """Cancel a running workflow."""
    registry = _get_registry(request)
    service = WorkflowService(db, registry)
    run = service.cancel_run(run_id, current_user)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    return _run_to_response(run)


@router.get("/runs/{run_id}/export")
async def export_run(
    run_id: str,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    request: Request = None,
):
    """Export a workflow run with all step outputs."""
    registry = _get_registry(request)
    service = WorkflowService(db, registry)
    run = service.get_run(run_id, current_user)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")

    return {
        "run": {
            "id": run.id,
            "title": run.title,
            "status": run.status,
            "input": run.input_json,
            "output": run.output_json,
            "error": run.error_message,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        },
        "steps": [
            {
                "seq": s.seq,
                "type": s.type,
                "title": s.title,
                "status": s.status,
                "output": s.output_text,
                "tokens_used": s.tokens_used,
                "provider": s.provider,
                "model": s.model,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "error": s.error_message,
            }
            for s in sorted(run.steps, key=lambda s: s.seq)
        ],
    }
