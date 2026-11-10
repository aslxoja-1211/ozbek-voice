"""Abstract base classes for Speech-to-Text providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

UZBEK_WHISPER_PROMPT = (
    "O'zbek tilidagi diktovka va ovozli tahrirlash buyruqlari: "
    "o'chir, o'zgartir, almashtir, bosh harf, xatboshi, ro'yxat, nuqta."
)


@dataclass(slots=True)
class STTResult:
    """Normalized output from any STT adapter."""

    text: str
    provider: str
    is_mock: bool = False
    note: Optional[str] = None


class STTConfigurationError(RuntimeError):
    """Raised when an explicitly requested STT provider is misconfigured."""


class STTProvider(ABC):
    """Interface implemented by all STT backends."""

    name: str
    is_mock: bool = False

    @abstractmethod
    async def transcribe(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/pcm",
        sample_rate: int = 16000,
        language: str = "uz",
    ) -> STTResult:
        """Transcribe raw audio bytes into Uzbek text."""
