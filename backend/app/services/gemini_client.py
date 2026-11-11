"""Shared Google Gemini async client, model-failover, cooldowns, and clean error formatting."""

import asyncio
import time
from collections.abc import Callable
from typing import Any

from google import genai
from google.genai import types

DEFAULT_GEMINI_FLASH_MODELS = (
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.6-flash",
)

# In-memory model cooldown map (monotonic timestamp until model can be retried).
_MODEL_COOLDOWN_UNTIL: dict[str, float] = {}


def clear_model_cooldowns() -> None:
    """Reset cached Gemini model cooldowns (mainly for tests)."""
    _MODEL_COOLDOWN_UNTIL.clear()


def _mark_cooldown(model_name: str, exc: Exception) -> None:
    msg = str(exc).upper()
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "QUOTA" in msg:
        _MODEL_COOLDOWN_UNTIL[model_name] = time.monotonic() + 900.0
    elif "404" in msg or "NOT_FOUND" in msg:
        _MODEL_COOLDOWN_UNTIL[model_name] = time.monotonic() + 3600.0
    else:
        _MODEL_COOLDOWN_UNTIL[model_name] = time.monotonic() + 45.0


def format_user_friendly_error(exc: Exception) -> str:
    """Convert raw upstream SDK/HTTP errors into concise Uzbek UI messages."""
    raw = str(exc)
    upper = raw.upper()
    if "429" in upper or "RESOURCE_EXHAUSTED" in upper or "QUOTA" in upper:
        return (
            "AI kunlik yoki daqiqalik limiti tugadi (429). "
            "Biroz kuting yoki Google AI Studio’da billing/yangi kalit ulang."
        )
    if "401" in upper or "403" in upper or "API_KEY_INVALID" in upper or "PERMISSION_DENIED" in upper:
        return "API kaliti noto'g'ri yoki ruxsati cheklangan."
    if isinstance(exc, TimeoutError) or "TIMEOUT" in upper:
        return "AI serveridan javob kutish vaqti tugadi. Qayta urinib ko'ring."
    if "503" in upper or "UNAVAILABLE" in upper:
        return "AI serveri hozir band (503). Bir ozdan keyin qayta urinib ko'ring."
    clean = raw.splitlines()[0].strip()
    return clean[:160] + ("..." if len(clean) > 160 else "")


def create_gemini_client(api_key: str, timeout_ms: int = 10000) -> genai.Client:
    """Create a Gemini client enforcing Google's minimum 10s server deadline."""
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=max(10000, timeout_ms),
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )


def ordered_gemini_models(
    primary_model: str,
    fallbacks: tuple[str, ...] = DEFAULT_GEMINI_FLASH_MODELS,
) -> list[str]:
    """Return deduplicated candidate models, deprioritizing models currently on cooldown."""
    seen: list[str] = []
    for name in (primary_model, *fallbacks):
        clean = name.strip()
        if clean and clean not in seen:
            seen.append(clean)

    now = time.monotonic()
    ready = [m for m in seen if _MODEL_COOLDOWN_UNTIL.get(m, 0.0) <= now]
    cooling = [m for m in seen if _MODEL_COOLDOWN_UNTIL.get(m, 0.0) > now]
    # Try ready models first; keep at most one fallback on cooldown if all are cooling.
    return ready if ready else cooling[:2]


async def generate_with_failover(
    client: genai.Client,
    models: list[str],
    contents: Any,
    config_builder: Callable[[str], types.GenerateContentConfig],
    per_attempt_timeout_s: float = 4.5,
) -> tuple[Any, str]:
    """Run generate_content across candidate models with tight timeout and cooldowns."""
    last_error: Exception | None = None
    for model_name in models:
        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config_builder(model_name),
                ),
                timeout=per_attempt_timeout_s,
            )
            _MODEL_COOLDOWN_UNTIL.pop(model_name, None)
            return response, model_name
        except Exception as exc:
            _mark_cooldown(model_name, exc)
            last_error = exc
            continue
    assert last_error is not None
    raise last_error
