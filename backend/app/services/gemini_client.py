"""Shared Google Gemini async client and model-failover helpers."""

import asyncio
from collections.abc import Callable
from typing import Any

from google import genai
from google.genai import types

DEFAULT_GEMINI_FLASH_MODELS = (
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
)


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
    """Return deduplicated candidate model names with `primary_model` first."""
    seen: list[str] = []
    for name in (primary_model, *fallbacks):
        clean = name.strip()
        if clean and clean not in seen:
            seen.append(clean)
    return seen


async def generate_with_failover(
    client: genai.Client,
    models: list[str],
    contents: Any,
    config_builder: Callable[[str], types.GenerateContentConfig],
    per_attempt_timeout_s: float = 4.5,
) -> tuple[Any, str]:
    """Run generate_content across candidate models with tight per-attempt timeout."""
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
            return response, model_name
        except Exception as exc:
            last_error = exc
            continue
    assert last_error is not None
    raise last_error
