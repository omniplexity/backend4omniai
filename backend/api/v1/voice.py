"""v1 voice endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.auth.dependencies import get_current_user
from backend.config import get_settings
from backend.core.logging import get_logger
from backend.db.models import User
from backend.services.voice_service import get_voice_service

logger = get_logger(__name__)
router = APIRouter(prefix="/voice", tags=["v1-voice"])


class TTSRequest(BaseModel):
    text: str = Field(min_length=1)
    voice_id: Optional[str] = None
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    pitch: float = Field(default=1.0, ge=0.5, le=2.0)
    volume: float = Field(default=1.0, ge=0.0, le=1.0)


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    language: Optional[str] = Form(default=None),
    current_user: User = Depends(get_current_user),
):
    settings = get_settings()
    service = get_voice_service(settings)
    try:
        audio_bytes = await file.read()
        transcript = await service.transcribe(audio_bytes, mime_type=file.content_type, language=language)
        return {
            "text": transcript.text,
            "language": transcript.language,
            "segments": transcript.segments,
        }
    except RuntimeError as exc:
        logger.warning("Voice transcription unavailable", data={"error": str(exc), "user_id": current_user.id})
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        logger.error("Voice transcription failed", data={"error": str(exc), "user_id": current_user.id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Transcription failed")


@router.post("/tts")
async def text_to_speech(
    body: TTSRequest,
    current_user: User = Depends(get_current_user),
):
    settings = get_settings()
    service = get_voice_service(settings)
    try:
        audio = await service.text_to_speech(
            body.text,
            voice_id=body.voice_id,
            speed=body.speed,
            pitch=body.pitch,
            volume=body.volume,
        )
        return Response(content=audio, media_type="audio/mpeg")
    except RuntimeError as exc:
        logger.warning("Voice TTS unavailable", data={"error": str(exc), "user_id": current_user.id})
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        logger.error("Voice TTS failed", data={"error": str(exc), "user_id": current_user.id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="TTS failed")
