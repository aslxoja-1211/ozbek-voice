"""Factory for selecting configured LLM Intent Engines."""

from typing import Optional

from app.config import Settings
from app.services.llm.base import IntentEngine, LLMConfigurationError
from app.services.llm.gemini_flash import GeminiFlashIntentEngine
from app.services.llm.openai_mini import OpenAIMiniIntentEngine
from app.services.llm.rule_fallback import RuleFallbackIntentEngine


def create_intent_engine(
    settings: Settings,
    override: Optional[str] = None,
) -> IntentEngine:
    """Instantiate an IntentEngine based on settings and optional override."""
    choice = (override or settings.resolved_llm_provider()).strip().lower()
    if choice == "auto":
        choice = settings.resolved_llm_provider()

    if choice == "gemini":
        if not settings.gemini_api_key:
            raise LLMConfigurationError(
                "GEMINI_API_KEY sozlanmagan. .env faylida kiriting yoki LLM_PROVIDER=auto qiling."
            )
        return GeminiFlashIntentEngine(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            timeout_ms=max(2000, int(settings.llm_timeout_seconds * 1000)),
        )

    if choice == "openai":
        if not settings.openai_api_key:
            raise LLMConfigurationError(
                "OPENAI_API_KEY sozlanmagan. .env faylida kiriting yoki LLM_PROVIDER=auto qiling."
            )
        return OpenAIMiniIntentEngine(
            api_key=settings.openai_api_key,
            model=settings.openai_llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )

    if choice == "mock":
        return RuleFallbackIntentEngine()

    raise LLMConfigurationError(f"Noma'lum LLM provayderi: {choice}")
