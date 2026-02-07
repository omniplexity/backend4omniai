"""Local Whisper voice provider using faster-whisper if available."""

from __future__ import annotations

import tempfile
from typing import Optional

from backend.core.logging import get_logger
from backend.providers.voice.base import VoiceProvider, VoiceTranscript

logger = get_logger(__name__)


class WhisperVoiceProvider(VoiceProvider):
    name = "whisper"

    def __init__(self, model_name: str = "base", device: str = "cpu") -> None:
        self.model_name = model_name
        self.device = device
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except Exception as exc:
            raise RuntimeError("faster-whisper is not installed") from exc
        self._model = WhisperModel(self.model_name, device=self.device)
        return self._model

    async def healthcheck(self) -> bool:
        try:
            self._load_model()
            return True
        except Exception as exc:
            logger.warning("Whisper provider unavailable", data={"error": str(exc)})
            return False

    async def transcribe(self, audio_bytes: bytes, mime_type: str | None = None, language: str | None = None) -> VoiceTranscript:
        model = self._load_model()
        with tempfile.NamedTemporaryFile(suffix=".audio", delete=True) as tmp:
            tmp.write(audio_bytes)
            tmp.flush()
            segments_iter, info = model.transcribe(
                tmp.name,
                language=language,
                vad_filter=True,
            )
            segments = []
            text_parts = []
            for segment in segments_iter:
                segments.append({
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text,
                })
                text_parts.append(segment.text)
        return VoiceTranscript(text=" ".join(text_parts).strip(), language=getattr(info, "language", None), segments=segments)

    async def text_to_speech(
        self,
        text: str,
        voice_id: str | None = None,
        speed: float = 1.0,
        pitch: float = 1.0,
        volume: float = 1.0,
    ) -> bytes:
        raise NotImplementedError("Whisper provider does not support TTS")
