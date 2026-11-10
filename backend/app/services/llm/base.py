"""Abstract base class and exceptions for LLM Intent Engines."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from app.models.schemas import EditorEditCommand


class LLMConfigurationError(RuntimeError):
    """Raised when an explicitly requested LLM provider lacks configuration."""


@dataclass(slots=True)
class IntentResult:
    """Output wrapper returned by an IntentEngine."""

    command: EditorEditCommand
    provider: str
    is_mock: bool = False
    note: Optional[str] = None


class IntentEngine(ABC):
    """Interface for detecting editing intent and producing EditorEditCommand JSON."""

    name: str
    is_mock: bool = False

    @abstractmethod
    async def resolve_intent(
        self,
        current_editor_state: str,
        raw_transcript: str,
    ) -> IntentResult:
        """Infer editing intent from `current_editor_state` and `raw_transcript`."""
