"""Mohirpool / Mohir.ai Uzbek STT REST adapter."""

from typing import Any

import httpx

from app.audio.pcm_utils import ensure_audio_filename_and_bytes
from app.services.stt.base import STTProvider, STTResult


def _extract_transcript(payload: Any) -> str:
    """Extract transcript string from common Mohirpool/Mohir.ai JSON payload shapes."""
    if isinstance(payload, str):
        return payload.strip()
    if not isinstance(payload, dict):
        return ""

    for key in ("text", "transcript", "utterance"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    for nested_key in ("result", "data"):
        nested = payload.get(nested_key)
        if isinstance(nested, dict):
            extracted = _extract_transcript(nested)
            if extracted:
                return extracted
        elif isinstance(nested, str) and nested.strip():
            return nested.strip()

    return ""


class MohirpoolSTTProvider(STTProvider):
    """Async adapter for Mohirpool / Mohir.ai Uzbek Speech-to-Text API."""

    name = "mohirpool"
    is_mock = False

    def __init__(
        self,
        api_key: str,
        api_url: str = "https://mohir.ai/api/v1/stt",
        timeout_seconds: float = 15.0,
    ) -> None:
        self._api_key = api_key
        self._api_url = api_url
        self._timeout = timeout_seconds

    async def transcribe(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/pcm",
        sample_rate: int = 16000,
        language: str = "uz",
    ) -> STTResult:
        """Upload WAV/audio payload to Mohirpool STT endpoint."""
        filename, payload, content_type = ensure_audio_filename_and_bytes(
            audio_bytes, mime_type=mime_type, sample_rate=sample_rate
        )
        headers = {"Authorization": f"Bearer {self._api_key}"}

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                self._api_url,
                headers=headers,
                files={"file": (filename, payload, content_type)},
                data={"language": language},
            )
            response.raise_for_status()
            data = response.json()

        transcript = _extract_transcript(data)
        return STTResult(text=transcript, provider=self.name, is_mock=False)
