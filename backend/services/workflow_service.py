"""Workflow orchestration service.

Manages creation, execution, and lifecycle of multi-step workflows
following the plan → execute → synthesize pattern.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DBSession

from backend.core.logging import get_logger
from backend.core.time import utcnow
from backend.db.database import get_session_local
from backend.db.models import WorkflowRun, WorkflowStep, WorkflowTemplate, User
from backend.providers.base import ChatMessage, ChatRequest
from backend.providers.registry import ProviderRegistry

logger = get_logger(__name__)

# Placeholder pattern: {input}, {step_1_output}, {step_2_output}, etc.
_PLACEHOLDER_RE = re.compile(r"\{(input|step_(\d+)_output)\}")


def _resolve_prompt(template: str, input_text: str, step_outputs: Dict[int, str]) -> str:
    """Resolve placeholders in a prompt template."""

    def _replace(match: re.Match) -> str:
        full = match.group(1)
        if full == "input":
            return input_text
        seq = int(match.group(2))
        return step_outputs.get(seq, f"[step {seq} output not available]")

    return _PLACEHOLDER_RE.sub(_replace, template)


class WorkflowService:
    """Service for managing workflow runs."""

    def __init__(self, db: DBSession, registry: ProviderRegistry):
        self.db = db
        self.registry = registry

    def create_run(
        self,
        user: User,
        title: str,
        steps_definition: List[Dict[str, Any]],
        input_data: Dict[str, Any],
        template_id: Optional[str] = None,
        project_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        provider_name: Optional[str] = None,
        model: Optional[str] = None,
    ) -> WorkflowRun:
        """Create a new workflow run with its steps."""
        run = WorkflowRun(
            user_id=user.id,
            template_id=template_id,
            project_id=project_id,
            conversation_id=conversation_id,
            title=title,
            status="pending",
            input_json=input_data,
        )
        self.db.add(run)
        self.db.flush()

        for step_def in steps_definition:
            step = WorkflowStep(
                run_id=run.id,
                seq=step_def["seq"],
                type=step_def.get("type", "custom"),
                title=step_def.get("title", f"Step {step_def['seq']}"),
                prompt_template=step_def.get("prompt_template"),
                status="pending",
                provider=provider_name,
                model=model,
            )
            self.db.add(step)

        self.db.commit()
        self.db.refresh(run)
        return run

    def get_run(self, run_id: str, user: User) -> Optional[WorkflowRun]:
        """Get a workflow run by ID (user-scoped)."""
        return (
            self.db.query(WorkflowRun)
            .filter(WorkflowRun.id == run_id, WorkflowRun.user_id == user.id)
            .first()
        )

    def list_runs(
        self,
        user: User,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[WorkflowRun]:
        """List workflow runs for a user."""
        q = self.db.query(WorkflowRun).filter(WorkflowRun.user_id == user.id)
        if project_id:
            q = q.filter(WorkflowRun.project_id == project_id)
        if status:
            q = q.filter(WorkflowRun.status == status)
        return q.order_by(WorkflowRun.created_at.desc()).offset(offset).limit(limit).all()

    def cancel_run(self, run_id: str, user: User) -> Optional[WorkflowRun]:
        """Cancel a running workflow."""
        run = self.get_run(run_id, user)
        if not run:
            return None
        if run.status in ("completed", "failed", "cancelled"):
            return run
        run.status = "cancelled"
        run.updated_at = utcnow()
        # Mark pending steps as skipped
        for step in run.steps:
            if step.status == "pending":
                step.status = "skipped"
        self.db.commit()
        self.db.refresh(run)
        return run

    def start_run_async(self, run_id: str) -> None:
        """Spawn background task to execute the workflow run."""
        asyncio.create_task(execute_workflow_run(run_id, self.registry))


async def execute_workflow_run(run_id: str, registry: ProviderRegistry) -> None:
    """Background task: execute all steps of a workflow run sequentially."""
    SessionLocal = get_session_local()
    db = SessionLocal()
    try:
        run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
        if not run:
            return

        input_text = (run.input_json or {}).get("goal", "")
        step_outputs: Dict[int, str] = {}

        steps = (
            db.query(WorkflowStep)
            .filter(WorkflowStep.run_id == run.id)
            .order_by(WorkflowStep.seq)
            .all()
        )

        if not steps:
            run.status = "completed"
            run.output_json = {"result": "No steps to execute"}
            run.completed_at = utcnow()
            run.updated_at = utcnow()
            db.commit()
            return

        # Determine provider
        provider_name = steps[0].provider or registry.default_provider
        provider = registry.get_provider(provider_name)
        if not provider:
            run.status = "failed"
            run.error_message = f"Provider not found: {provider_name}"
            run.updated_at = utcnow()
            db.commit()
            return

        # Resolve model
        resolved_model = steps[0].model
        if not resolved_model:
            try:
                models = await provider.list_models()
                if models:
                    resolved_model = models[0].id
            except Exception:
                pass
        resolved_model = resolved_model or "default"

        # Update run status based on first step type
        first_type = steps[0].type
        status_map = {"plan": "planning", "execute": "executing", "synthesize": "synthesizing"}
        run.status = status_map.get(first_type, "executing")
        run.updated_at = utcnow()
        db.commit()

        for step in steps:
            # Check for cancellation
            db.refresh(run)
            if run.status == "cancelled":
                logger.info(f"Workflow run {run.id} cancelled")
                return

            # Update run status based on step type
            new_status = status_map.get(step.type, "executing")
            if run.status != new_status:
                run.status = new_status
                run.updated_at = utcnow()
                db.commit()

            step.status = "running"
            step.started_at = utcnow()
            step.provider = provider_name
            step.model = resolved_model
            db.commit()

            try:
                prompt = step.prompt_template or input_text
                resolved_prompt = _resolve_prompt(prompt, input_text, step_outputs)

                messages = [
                    ChatMessage(role="user", content=resolved_prompt),
                ]

                request = ChatRequest(
                    messages=messages,
                    model=resolved_model,
                    temperature=0.7,
                    stream=False,
                )

                started = time.monotonic()
                response = await provider.chat_once(request)
                elapsed_ms = int((time.monotonic() - started) * 1000)

                output = response.content or ""
                step.output_text = output
                step.output_json = {
                    "content": output,
                    "model": response.model,
                    "tokens": {
                        "prompt": response.prompt_tokens,
                        "completion": response.completion_tokens,
                        "total": response.total_tokens,
                    },
                    "elapsed_ms": elapsed_ms,
                }
                step.tokens_used = response.total_tokens
                step.status = "completed"
                step.completed_at = utcnow()
                db.commit()

                step_outputs[step.seq] = output

                logger.info(
                    f"Workflow step {step.seq} completed",
                    data={"run_id": run.id, "step_type": step.type, "elapsed_ms": elapsed_ms},
                )

            except Exception as exc:
                step.status = "failed"
                step.error_message = str(exc)
                step.completed_at = utcnow()
                db.commit()

                run.status = "failed"
                run.error_message = f"Step {step.seq} ({step.title}) failed: {exc}"
                run.updated_at = utcnow()
                db.commit()

                logger.error(
                    f"Workflow step {step.seq} failed",
                    data={"run_id": run.id, "error": str(exc)},
                )
                return

        # All steps completed successfully
        last_output = step_outputs.get(steps[-1].seq, "")
        run.status = "completed"
        run.output_json = {
            "result": last_output,
            "steps_completed": len(steps),
            "step_outputs": {str(k): v[:500] for k, v in step_outputs.items()},
        }
        run.completed_at = utcnow()
        run.updated_at = utcnow()
        db.commit()

        logger.info(f"Workflow run {run.id} completed", data={"steps": len(steps)})

    except Exception as exc:
        logger.error(f"Workflow execution failed", data={"run_id": run_id, "error": str(exc)})
        try:
            run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
            if run and run.status not in ("completed", "cancelled"):
                run.status = "failed"
                run.error_message = str(exc)
                run.updated_at = utcnow()
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
