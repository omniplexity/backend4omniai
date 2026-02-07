"""Planning API endpoints.

Thin wrapper around the workflow engine that runs a single planning step
to decompose a goal into structured sub-steps.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from backend.auth.dependencies import get_current_user
from backend.db import get_db
from backend.db.models import User
from backend.providers.base import ChatMessage, ChatRequest
from backend.providers.registry import ProviderRegistry

router = APIRouter(prefix="/api/plan", tags=["plan"])


class PlanRequest(BaseModel):
    goal: str = Field(min_length=1)
    constraints: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None


class PlanStep(BaseModel):
    title: str
    detail: str


class PlanResponse(BaseModel):
    goal: str
    steps: List[PlanStep]


def _get_registry(request: Request) -> ProviderRegistry:
    registry = getattr(request.app.state, "provider_registry", None)
    if not registry:
        raise HTTPException(status_code=503, detail="Provider registry not available")
    return registry


@router.post("/execute", response_model=PlanResponse)
async def execute_plan(
    payload: PlanRequest,
    request: Request,
    _user: User = Depends(get_current_user),
):
    """Generate a structured plan for a goal using the LLM provider."""
    registry = _get_registry(request)

    provider_name = payload.provider or registry.default_provider
    provider = registry.get_provider(provider_name)
    if not provider:
        raise HTTPException(status_code=502, detail=f"Provider not available: {provider_name}")

    resolved_model = payload.model
    if not resolved_model:
        try:
            models = await provider.list_models()
            if models:
                resolved_model = models[0].id
        except Exception:
            pass
    resolved_model = resolved_model or "default"

    constraint_text = ""
    if payload.constraints:
        constraint_text = f"\n\nConstraints to consider:\n{payload.constraints}"

    prompt = (
        "You are a planning assistant. Break the following goal into 3-7 clear, actionable steps.\n\n"
        f"Goal: {payload.goal}{constraint_text}\n\n"
        "Return ONLY a numbered list where each line has the format:\n"
        "N. Title: Detail\n"
        "Do not include any other text."
    )

    chat_request = ChatRequest(
        messages=[ChatMessage(role="user", content=prompt)],
        model=resolved_model,
        temperature=0.5,
        stream=False,
    )

    try:
        response = await provider.chat_once(chat_request)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Provider error: {exc}")

    # Parse the numbered list response
    steps: List[PlanStep] = []
    for line in (response.content or "").strip().splitlines():
        line = line.strip()
        if not line:
            continue
        # Strip leading number and punctuation: "1. Title: Detail" or "1) Title: Detail"
        match = re.match(r"^\d+[\.\)]\s*(.+)", line)
        if match:
            text = match.group(1)
            if ":" in text:
                title, detail = text.split(":", 1)
                steps.append(PlanStep(title=title.strip(), detail=detail.strip()))
            else:
                steps.append(PlanStep(title=text.strip(), detail=""))

    # Fallback if parsing failed
    if not steps:
        steps = [PlanStep(title="Execute goal", detail=payload.goal)]

    return PlanResponse(goal=payload.goal, steps=steps)
