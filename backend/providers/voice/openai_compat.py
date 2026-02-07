"""OpenAI-compatible voice provider."""

from __future__ import annotations

import httpx

from backend.core.logging import get_logger
from backend.providers.voice.base import VoiceProvider, VoiceTranscript

logger = get_logger(__name__)


class OpenAICompatVoiceProvider(VoiceProvider):
    name = "openai_compat"

    def __init__(self, base_url: str, api_key: str, audio_model: str = "whisper-1") -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.audio_model = audio_model

    async def healthcheck(self) -> bool:
        return bool(self.base_url and self.api_key)

    async def transcribe(self, audio_bytes: bytes, mime_type: str | None = None, language: str | None = None) -> VoiceTranscript:
        url = f"{self.base_url}/audio/transcriptions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        data = {"model": self.audio_model}
        if language:
            data["language"] = language
        files = {
            "file": ("audio", audio_bytes, mime_type or "application/octet-stream"),
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url, headers=headers, data=data, files=files)
            response.raise_for_status()
            payload = response.json()
        return VoiceTranscript(text=payload.get("text", ""), language=language)

    async def text_to_speech(
        self,
        text: str,
        voice_id: str | None = None,
        speed: float = 1.0,
        pitch: float = 1.0,
        volume: float = 1.0,
    ) -> bytes:
        url = f"{self.base_url}/audio/speech"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "tts-1",
            "input": text,
            "voice": voice_id or "alloy",
            "speed": speed,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.content
