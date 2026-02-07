"""Media API endpoints."""

import os
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session as DBSession

from backend.auth.dependencies import get_current_user
from backend.config import get_settings
from backend.db import get_db
from backend.db.database import get_session_local
from backend.db.models import MediaAsset, MediaJob, User

router = APIRouter(prefix="/api/media", tags=["media"])


def ensure_storage(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def save_upload(file: UploadFile, storage_path: str) -> str:
    filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{file.filename}"
    destination = os.path.join(storage_path, filename)
    with open(destination, "wb") as target:
        target.write(file.file.read())
    return destination


def process_job(job_id: str) -> None:
    SessionLocal = get_session_local()
    db = SessionLocal()
    try:
        job = db.query(MediaJob).filter(MediaJob.id == job_id).first()
        if not job:
            return
        job.status = "completed"
        job.progress = 100
        job.result = {"message": "Job completed", "job_id": job.id}
        job.completed_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


@router.post("/upload")
async def upload_asset(
    file: UploadFile = File(...),
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings = get_settings()
    storage_path = settings.media_storage_path
    ensure_storage(storage_path)

    destination = save_upload(file, storage_path)
    size = os.path.getsize(destination)

    asset = MediaAsset(
        user_id=current_user.id,
        filename=file.filename,
        mime_type=file.content_type,
        size=size,
        storage_path=destination,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)

    return {
        "asset_id": asset.id,
        "url": f"/api/media/assets/{asset.id}",
        "mime_type": asset.mime_type,
        "size": asset.size,
        "width": None,
        "height": None,
    }


@router.get("/assets/{asset_id}")
async def get_asset(
    asset_id: str,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    asset = (
        db.query(MediaAsset)
        .filter(MediaAsset.id == asset_id, MediaAsset.user_id == current_user.id)
        .first()
    )
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    if not os.path.exists(asset.storage_path):
        raise HTTPException(status_code=404, detail="File missing")
    from fastapi.responses import FileResponse

    return FileResponse(asset.storage_path, media_type=asset.mime_type)


@router.post("/screenshot/analyze")
async def analyze_screenshot(
    payload: Dict[str, Any],
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    asset_id = payload.get("asset_id")
    prompt = payload.get("prompt") or "Describe the image."
    if not asset_id:
        raise HTTPException(status_code=400, detail="asset_id required")
    asset = (
        db.query(MediaAsset)
        .filter(MediaAsset.id == asset_id, MediaAsset.user_id == current_user.id)
        .first()
    )
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    return {
        "transcript": f"Analysis placeholder for {asset.filename}",
        "analysis": {"prompt": prompt, "note": "Vision analysis not configured"},
        "metadata": {"mime_type": asset.mime_type, "size": asset.size},
    }


@router.post("/jobs")
async def create_job(
    payload: Dict[str, Any],
    background_tasks: BackgroundTasks,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job_type = payload.get("type")
    if not job_type:
        raise HTTPException(status_code=400, detail="type required")

    job = MediaJob(
        user_id=current_user.id,
        type=job_type,
        status="pending",
        input_asset_id=payload.get("input_asset_id"),
        prompt=payload.get("prompt"),
        params=payload.get("params"),
        progress=0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(process_job, job.id)

    return {
        "job_id": job.id,
        "status": job.status,
        "created_at": job.created_at.isoformat(),
    }


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = (
        db.query(MediaJob)
        .filter(MediaJob.id == job_id, MediaJob.user_id == current_user.id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job.id,
        "status": job.status,
        "progress": job.progress,
        "result": job.result,
        "error": job.error_message,
        "created_at": job.created_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.get("/jobs")
async def list_jobs(
    limit: int = 20,
    status: Optional[str] = None,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(MediaJob).filter(MediaJob.user_id == current_user.id)
    if status:
        query = query.filter(MediaJob.status == status)
    jobs = query.order_by(MediaJob.created_at.desc()).limit(limit).all()
    return {"jobs": [
        {
            "job_id": job.id,
            "status": job.status,
            "progress": job.progress,
            "created_at": job.created_at.isoformat(),
        }
        for job in jobs
    ]}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = (
        db.query(MediaJob)
        .filter(MediaJob.id == job_id, MediaJob.user_id == current_user.id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in {"pending", "running"}:
        return {"status": job.status}

    job.status = "cancelled"
    job.error_message = "Cancelled"
    job.completed_at = datetime.utcnow()
    db.commit()

    return {"status": job.status}
