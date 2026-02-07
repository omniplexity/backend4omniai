"""Voice service for transcription and TTS."""

from __future__ import annotations

from typing import Optional

from backend.config import Settings
from backend.core.logging import get_logger
from backend.providers.voice import OpenAICompatVoiceProvider, WhisperVoiceProvider, VoiceProvider, VoiceTranscript

logger = get_logger(__name__)

_voice_service = None


def _parse_provider_preference(pref: str) -> list[str]:
    if not pref:
        return []
    return [item.strip() for item in pref.split(",") if item.strip()]


class VoiceService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.providers: list[VoiceProvider] = []
        preference = _parse_provider_preference(settings.voice_provider_preference)

        for name in preference:
            if name == "whisper":
                try:
                    self.providers.append(WhisperVoiceProvider(settings.voice_whisper_model, settings.voice_whisper_device))
                except Exception as exc:
                    logger.warning("Failed to initialize whisper provider", data={"error": str(exc)})
            if name == "openai_compat":
                if settings.openai_compat_base_url and settings.openai_compat_api_key:
                    self.providers.append(
                        OpenAICompatVoiceProvider(
                            settings.openai_compat_base_url,
                            settings.openai_compat_api_key,
                            settings.voice_openai_audio_model,
                        )
                    )

    async def resolve_transcriber(self) -> Optional[VoiceProvider]:
        for provider in self.providers:
            try:
                if await provider.healthcheck():
                    return provider
            except Exception:
                continue
        return None

    async def transcribe(self, audio_bytes: bytes, mime_type: str | None = None, language: str | None = None) -> VoiceTranscript:
        provider = await self.resolve_transcriber()
        if not provider:
            raise RuntimeError("No voice provider available")
        return await provider.transcribe(audio_bytes, mime_type=mime_type, language=language)

    async def text_to_speech(
        self,
        text: str,
        voice_id: str | None = None,
        speed: float = 1.0,
        pitch: float = 1.0,
        volume: float = 1.0,
    ) -> bytes:
        for provider in self.providers:
            try:
                if await provider.healthcheck():
                    return await provider.text_to_speech(text, voice_id=voice_id, speed=speed, pitch=pitch, volume=volume)
            except NotImplementedError:
                continue
        raise RuntimeError("No TTS provider available")


def get_voice_service(settings: Settings) -> VoiceService:
    global _voice_service
    if _voice_service is None:
        _voice_service = VoiceService(settings)
    return _voice_service
