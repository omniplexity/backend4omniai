"""Voice provider base interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class VoiceTranscript:
    text: str
    language: Optional[str] = None
    segments: Optional[list[dict]] = None


class VoiceProvider(ABC):
    name: str

    @abstractmethod
    async def healthcheck(self) -> bool:
        ...

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, mime_type: str | None = None, language: str | None = None) -> VoiceTranscript:
        ...

    @abstractmethod
    async def text_to_speech(
        self,
        text: str,
        voice_id: str | None = None,
        speed: float = 1.0,
        pitch: float = 1.0,
        volume: float = 1.0,
    ) -> bytes:
        ...

    async def list_voices(self) -> list[dict]:
        return []
