"""Voice Agent.

Handles speech-to-text (transcription) and text-to-speech (synthesis).
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass

from backend.services.voice_service import VoiceService
from backend.config import Settings


@dataclass
class TranscriptionResult:
    """Transcription result."""
    text: str
    language: Optional[str] = None
    duration: Optional[float] = None
    segments: Optional[list] = None


@dataclass
class SynthesisRequest:
    """Text-to-speech request."""
    text: str
    voice_id: Optional[str] = None
    speed: float = 1.0
    pitch: float = 1.0
    volume: float = 1.0


class VoiceAgent:
    """Agent for handling voice operations."""

    def __init__(self, settings: Settings):
        """Initialize the Voice Agent.
        
        Args:
            settings: Application settings
        """
        self.settings = settings
        self._voice_service = None

    @property
    def voice_service(self) -> VoiceService:
        """Get or create the voice service."""
        if self._voice_service is None:
            self._voice_service = VoiceService(self.settings)
        return self._voice_service

    async def transcribe(
        self,
        audio_data: bytes,
        mime_type: str = "audio/webm",
        language: Optional[str] = None,
    ) -> TranscriptionResult:
        """Transcribe audio to text.
        
        Args:
            audio_data: Audio data
            mime_type: MIME type of the audio
            language: Optional language hint
            
        Returns:
            TranscriptionResult with transcribed text
        """
        try:
            result = await self.voice_service.transcribe(
                audio_data=audio_data,
                mime_type=mime_type,
                language=language,
            )
            return TranscriptionResult(
                text=result.get("text", ""),
                language=result.get("language"),
                duration=result.get("duration"),
                segments=result.get("segments"),
            )
        except Exception as e:
            raise RuntimeError(f"Transcription failed: {e}")

    async def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
        speed: float = 1.0,
        pitch: float = 1.0,
        volume: float = 1.0,
    ) -> bytes:
        """Synthesize text to speech.
        
        Args:
            text: Text to synthesize
            voice_id: Optional voice ID
            speed: Speech speed (0.5 - 2.0)
            pitch: Pitch adjustment (0.5 - 2.0)
            volume: Volume level (0.0 - 1.0)
            
        Returns:
            Audio data as bytes (MP3)
        """
        try:
            return await self.voice_service.synthesize(
                text=text,
                voice_id=voice_id,
                speed=speed,
                pitch=pitch,
                volume=volume,
            )
        except Exception as e:
            raise RuntimeError(f"Speech synthesis failed: {e}")

    async def get_voices(self) -> list:
        """Get available voices.
        
        Returns:
            List of available voice IDs
        """
        try:
            return await self.voice_service.get_voices()
        except Exception:
            return []

    async def aclose(self) -> None:
        """Close the voice service."""
        if self._voice_service:
            await self._voice_service.aclose()
