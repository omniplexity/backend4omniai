"""
Voice API endpoints for STT and TTS functionality
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from backend.auth.dependencies import get_current_user
from backend.db.models import User
from backend.core.logging import get_logger
from backend.providers.registry import ProviderRegistry

logger = get_logger(__name__)

router = APIRouter(prefix="/api/voice", tags=["voice"])

class STTRequest(BaseModel):
    """Speech-to-Text request model"""
    language: str = Field(default="en-US", description="Language code for speech recognition")
    interim_results: bool = Field(default=True, description="Whether to return interim results")
    continuous: bool = Field(default=True, description="Whether to continue listening after speech ends")

class STTResponse(BaseModel):
    """Speech-to-Text response model"""
    type: str = Field(description="Event type: transcript, error, end")
    final: Optional[str] = Field(default=None, description="Final transcript")
    interim: Optional[str] = Field(default=None, description="Interim transcript")
    is_final: Optional[bool] = Field(default=None, description="Whether this is a final result")
    message: Optional[str] = Field(default=None, description="Error message")

class TTSRequest(BaseModel):
    """Text-to-Speech request model"""
    text: str = Field(description="Text to convert to speech")
    voice_id: Optional[str] = Field(default=None, description="Voice ID to use")
    speed: float = Field(default=1.0, ge=0.5, le=2.0, description="Speech speed")
    pitch: float = Field(default=1.0, ge=0.5, le=2.0, description="Speech pitch")
    volume: float = Field(default=1.0, ge=0.0, le=1.0, description="Speech volume")

class VoiceInfo(BaseModel):
    """Voice information model"""
    id: str = Field(description="Voice identifier")
    name: str = Field(description="Voice display name")
    language: str = Field(description="Language code")
    gender: Optional[str] = Field(default=None, description="Voice gender")

class VoicesResponse(BaseModel):
    """Voices list response model"""
    voices: List[VoiceInfo] = Field(description="Available voices")

@router.get("/capabilities")
async def get_voice_capabilities(
    request: Request,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get voice capabilities for the current user with enhanced error handling
    """
    try:
        # Get registry from app state
        registry = getattr(request.app.state, "provider_registry", None)
        if not registry:
            return {
                "available": False,
                "providers": [],
                "stt": False,
                "tts": False,
                "voices": False,
                "healthy_providers": 0,
                "total_providers": 0
            }
        
        # Get providers from registry
        providers = []
        for provider_name, provider in registry.providers.items():
            try:
                caps = await provider.capabilities()
            except Exception:
                continue

            provider_info = {
                "name": provider_name,
                "healthy": True,  # Assume healthy if we can access it
                "capabilities": {
                    "stt": bool(caps.stt),
                    "tts": bool(caps.tts),
                    "voices": bool(caps.voices)
                }
            }
            providers.append(provider_info)
        
        healthy_providers = [p for p in providers if p.get("healthy", False)]
        
        return {
            "available": len(healthy_providers) > 0,
            "providers": providers,
            "stt": any(p.get("capabilities", {}).get("stt", False) for p in healthy_providers),
            "tts": any(p.get("capabilities", {}).get("tts", False) for p in healthy_providers),
            "voices": any(p.get("capabilities", {}).get("voices", False) for p in healthy_providers),
            "healthy_providers": len(healthy_providers),
            "total_providers": len(providers)
        }
    except Exception as e:
        logger.error(f"Error getting voice capabilities: {e}", extra={
            "user_id": current_user.id,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get voice capabilities"
        )

@router.post("/stt")
async def speech_to_text(
    stt_request: STTRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user)
) -> StreamingResponse:
    """
    Speech-to-Text endpoint with streaming support
    """
    try:
        # Get registry from app state
        registry = getattr(http_request.app.state, "provider_registry", None)
        if not registry:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No providers available"
            )
        
        # Find a provider that supports STT
        stt_provider = None
        for provider_name, provider in registry.providers.items():
            try:
                caps = await provider.capabilities()
                if caps.stt:
                    stt_provider = provider
                    break
            except Exception:
                continue
        
        if not stt_provider:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No STT provider available"
            )
        
        async def stt_stream():
            """Generate streaming STT responses"""
            try:
                # Initialize STT stream
                stream = stt_provider.start_stt(
                    language=stt_request.language,
                    interim_results=stt_request.interim_results,
                    continuous=stt_request.continuous
                )
                if hasattr(stream, "__await__"):
                    stream = await stream
                
                # Stream responses
                async for result in stream:
                    response = STTResponse(
                        type="transcript",
                        final=result.get("final"),
                        interim=result.get("interim"),
                        is_final=result.get("is_final", False)
                    )
                    yield f"data: {response.json()}\n\n"
                    
            except Exception as e:
                error_response = STTResponse(
                    type="error",
                    message=str(e)
                )
                yield f"data: {error_response.json()}\n\n"
                
                end_response = STTResponse(type="end")
                yield f"data: {end_response.json()}\n\n"
        
        return StreamingResponse(
            stt_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in STT endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="STT service unavailable"
        )

@router.post("/tts")
async def text_to_speech(
    tts_request: TTSRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Text-to-Speech endpoint
    """
    try:
        # Get registry from app state
        registry = getattr(http_request.app.state, "provider_registry", None)
        if not registry:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No providers available"
            )
        
        # Find a provider that supports TTS
        tts_provider = None
        for provider_name, provider in registry.providers.items():
            try:
                caps = await provider.capabilities()
                if caps.tts:
                    tts_provider = provider
                    break
            except Exception:
                continue
        
        if not tts_provider:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No TTS provider available"
            )
        
        # Generate speech
        audio_data = await tts_provider.text_to_speech(
            text=tts_request.text,
            voice_id=tts_request.voice_id,
            speed=tts_request.speed,
            pitch=tts_request.pitch,
            volume=tts_request.volume
        )
        
        if not audio_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate speech"
            )
        
        return Response(
            content=audio_data,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": 'attachment; filename="speech.mp3"'
            },
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in TTS endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="TTS service unavailable"
        )

@router.get("/voices")
async def list_voices(
    request: Request,
    current_user: User = Depends(get_current_user)
) -> VoicesResponse:
    """
    List available voices
    """
    try:
        all_voices = []
        
        # Get registry from app state
        registry = getattr(request.app.state, "provider_registry", None)
        if not registry:
            return VoicesResponse(voices=[])
        
        # Collect voices from all providers
        for provider_name, provider in registry.providers.items():
            try:
                caps = await provider.capabilities()
                if not caps.voices:
                    continue

                voices = await provider.list_voices()
                if voices:
                    for voice in voices:
                        all_voices.append(VoiceInfo(
                            id=f"{provider_name}:{voice.get('id', '')}",
                            name=voice.get('name', ''),
                            language=voice.get('language', ''),
                            gender=voice.get('gender')
                        ))
            except Exception as e:
                logger.warning(f"Failed to get voices from {provider_name}: {e}")
        
        return VoicesResponse(voices=all_voices)
        
    except Exception as e:
        logger.error(f"Error listing voices: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list voices"
        )
