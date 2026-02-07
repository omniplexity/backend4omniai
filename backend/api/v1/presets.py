"""v1 chat presets endpoints."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from backend.auth.dependencies import get_current_user
from backend.db import get_db
from backend.db.models import ChatPreset, User

router = APIRouter(prefix="/presets", tags=["v1-presets"])


class PresetModel(BaseModel):
    id: str
    name: str
    settings: Optional[Dict[str, Any]] = None
    created_at: str
    updated_at: str


class CreatePresetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    settings: Optional[Dict[str, Any]] = None


class UpdatePresetRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    settings: Optional[Dict[str, Any]] = None


@router.get("", response_model=List[PresetModel])
async def list_presets(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    presets = db.query(ChatPreset).filter(ChatPreset.user_id == current_user.id).order_by(ChatPreset.updated_at.desc()).all()
    return [
        PresetModel(
            id=p.id,
            name=p.name,
            settings=p.settings_json or None,
            created_at=p.created_at.isoformat(),
            updated_at=p.updated_at.isoformat(),
        )
        for p in presets
    ]


@router.post("", response_model=PresetModel)
async def create_preset(
    body: CreatePresetRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    preset = ChatPreset(
        user_id=current_user.id,
        name=body.name,
        settings_json=body.settings or {},
    )
    db.add(preset)
    db.commit()
    db.refresh(preset)
    return PresetModel(
        id=preset.id,
        name=preset.name,
        settings=preset.settings_json or None,
        created_at=preset.created_at.isoformat(),
        updated_at=preset.updated_at.isoformat(),
    )


@router.patch("/{preset_id}", response_model=PresetModel)
async def update_preset(
    preset_id: str,
    body: UpdatePresetRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    preset = db.query(ChatPreset).filter(ChatPreset.id == preset_id, ChatPreset.user_id == current_user.id).first()
    if not preset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preset not found")
    if body.name:
        preset.name = body.name
    if body.settings is not None:
        preset.settings_json = body.settings
    db.commit()
    db.refresh(preset)
    return PresetModel(
        id=preset.id,
        name=preset.name,
        settings=preset.settings_json or None,
        created_at=preset.created_at.isoformat(),
        updated_at=preset.updated_at.isoformat(),
    )


@router.delete("/{preset_id}")
async def delete_preset(
    preset_id: str,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    preset = db.query(ChatPreset).filter(ChatPreset.id == preset_id, ChatPreset.user_id == current_user.id).first()
    if not preset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preset not found")
    db.delete(preset)
    db.commit()
    return {"status": "deleted", "id": preset_id}
