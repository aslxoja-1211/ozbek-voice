"""Factory for constructing configured Speech-to-Text providers."""

from typing import Optional

from app.config import Settings
from app.services.stt.base import STTConfigurationError, STTProvider
from app.services.stt.gemini_stt import GeminiSTTProvider
from app.services.stt.local_whisper import LocalWhisperSTTProvider
from app.services.stt.mock import MockSTTProvider
from app.services.stt.mohirpool import MohirpoolSTTProvider
from app.services.stt.openai_whisper import OpenAIWhisperProvider


def create_stt_provider(
    settings: Settings,
    override: Optional[str] = None,
) -> STTProvider:
    """Instantiate an STTProvider based on settings and optional request override."""
    choice = (override or settings.resolved_stt_provider()).strip().lower()
    if choice == "auto":
        choice = settings.resolved_stt_provider()

    if choice == "gemini":
        if not settings.gemini_api_key:
            raise STTConfigurationError(
                "GEMINI_API_KEY sozlanmagan. .env faylida kiriting yoki STT_PROVIDER=auto qiling."
            )
        return GeminiSTTProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            timeout_ms=max(10000, int(settings.stt_timeout_seconds * 1000)),
        )

    if choice == "local_whisper":
        return LocalWhisperSTTProvider(
            model_size=settings.local_whisper_model,
            device=settings.local_whisper_device,
            compute_type=settings.local_whisper_compute_type,
        )

    if choice == "mohirpool":
        if not settings.mohirpool_api_key:
            raise STTConfigurationError(
                "MOHIRPOOL_API_KEY sozlanmagan. .env faylida kiriting yoki STT_PROVIDER=auto qiling."
            )
        return MohirpoolSTTProvider(
            api_key=settings.mohirpool_api_key,
            api_url=settings.mohirpool_stt_url,
            timeout_seconds=settings.stt_timeout_seconds,
        )

    if choice == "openai":
        if not settings.openai_api_key:
            raise STTConfigurationError(
                "OPENAI_API_KEY sozlanmagan. .env faylida kiriting yoki STT_PROVIDER=auto qiling."
            )
        return OpenAIWhisperProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_stt_model,
            timeout_seconds=settings.stt_timeout_seconds,
        )

    if choice == "mock":
        return MockSTTProvider()

    raise STTConfigurationError(f"Noma'lum STT provayderi: {choice}")
