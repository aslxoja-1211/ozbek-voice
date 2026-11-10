"""OpenAI Whisper STT adapter optimized for Uzbek dictation and editing commands."""

import io

from openai import AsyncOpenAI

from app.audio.pcm_utils import ensure_audio_filename_and_bytes
from app.services.stt.base import STTProvider, STTResult, UZBEK_WHISPER_PROMPT


class OpenAIWhisperProvider(STTProvider):
    """Calls OpenAI Audio Transcriptions API (whisper-1 / gpt-4o-transcribe)."""

    name = "openai"
    is_mock = False

    def __init__(
        self,
        api_key: str,
        model: str = "whisper-1",
        timeout_seconds: float = 15.0,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key, timeout=timeout_seconds)
        self._model = model

    async def transcribe(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/pcm",
        sample_rate: int = 16000,
        language: str = "uz",
    ) -> STTResult:
        """Convert audio buffer to WAV/supported format and transcribe via OpenAI."""
        filename, payload, content_type = ensure_audio_filename_and_bytes(
            audio_bytes, mime_type=mime_type, sample_rate=sample_rate
        )
        file_obj = io.BytesIO(payload)
        file_obj.name = filename

        response = await self._client.audio.transcriptions.create(
            model=self._model,
            file=(filename, file_obj, content_type),
            language=language,
            prompt=UZBEK_WHISPER_PROMPT,
            response_format="text",
        )
        transcript = response.strip() if isinstance(response, str) else getattr(response, "text", "").strip()
        return STTResult(text=transcript, provider=self.name, is_mock=False)
