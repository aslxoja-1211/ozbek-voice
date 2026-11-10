"""Uzbek -> Russian / English contextual translation service."""

import time
from typing import Optional

from google.genai import types
from openai import AsyncOpenAI

from app.config import Settings
from app.models.schemas import TranslateResponse, TranslationLanguage
from app.services.gemini_client import (
    create_gemini_client,
    generate_with_failover,
    ordered_gemini_models,
)

LANGUAGE_LABELS: dict[TranslationLanguage, str] = {
    "ru": "rus tiliga (Russian)",
    "en": "ingliz tiliga (English)",
}


class TranslationConfigurationError(RuntimeError):
    """Raised when no LLM provider is configured for translation."""


def _build_translation_instruction(target_language: TranslationLanguage) -> str:
    lang_label = LANGUAGE_LABELS[target_language]
    return (
        f"Siz professional o'zbek -> {lang_label} tarjimonsiz.\n"
        "QOIDALAR:\n"
        "1. Berilgan o'zbekcha matnni tabiiy, grammatik jihatdan mukammal va ma'nosini to'liq saqlagan holda tarjima qiling.\n"
        "2. Agar matnda Markdown tuzilishi bo'lsa (masalan `- ` ro'yxatlar, `# ` sarlavhalar, `**qalin**`, xatboshilar), ularni aynan saqlab qoling.\n"
        "3. Faqat tarjima qilingan tayyor matnni qaytaring; kirish so'zlari, izoh yoki qo'shtirnoq qo'shmang."
    )


class TranslationService:
    """Translates Uzbek editor content cleanly using Gemini Flash (or OpenAI fallback)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._gemini_client = None

    def _get_gemini_client(self):
        if self._gemini_client is None:
            self._gemini_client = create_gemini_client(
                api_key=self._settings.gemini_api_key,
                timeout_ms=max(10000, int(self._settings.llm_timeout_seconds * 1000)),
            )
        return self._gemini_client

    async def translate(
        self,
        text: str,
        target_language: TranslationLanguage = "ru",
        provider_override: Optional[str] = None,
    ) -> TranslateResponse:
        """Translate `text` from Uzbek into `target_language` ('ru' or 'en')."""
        clean_text = text.strip()
        if not clean_text:
            return TranslateResponse(
                source_text="",
                target_language=target_language,
                translated_text="",
                provider="none",
                latency_ms=0.0,
            )

        choice = (provider_override or self._settings.resolved_llm_provider()).strip().lower()
        if choice == "auto":
            choice = self._settings.resolved_llm_provider()

        if choice == "gemini" or (choice == "mock" and self._settings.gemini_api_key):
            if not self._settings.gemini_api_key:
                raise TranslationConfigurationError(
                    "GEMINI_API_KEY sozlanmagan."
                )
            return await self._translate_with_gemini(clean_text, target_language)

        if choice == "openai":
            if not self._settings.openai_api_key:
                raise TranslationConfigurationError(
                    "OPENAI_API_KEY sozlanmagan."
                )
            return await self._translate_with_openai(clean_text, target_language)

        raise TranslationConfigurationError(
            "Tarjima uchun GEMINI_API_KEY yoki OPENAI_API_KEY sozlanmagan."
        )

    async def _translate_with_gemini(
        self,
        text: str,
        target_language: TranslationLanguage,
    ) -> TranslateResponse:
        start = time.perf_counter()
        client = self._get_gemini_client()
        instruction = _build_translation_instruction(target_language)

        def build_cfg(model_name: str) -> types.GenerateContentConfig:
            use_thinking_budget = "lite" not in model_name.lower()
            return types.GenerateContentConfig(
                system_instruction=instruction,
                temperature=0.15,
                thinking_config=(
                    types.ThinkingConfig(thinking_budget=0)
                    if use_thinking_budget
                    else None
                ),
            )

        response, used_model = await generate_with_failover(
            client=client,
            models=ordered_gemini_models(self._settings.gemini_model),
            contents=text,
            config_builder=build_cfg,
            per_attempt_timeout_s=8.0,
        )
        translated = (response.text or "").strip()
        latency_ms = round((time.perf_counter() - start) * 1000.0, 2)
        note = (
            f"Zaxira Gemini modeli ({used_model})."
            if used_model != self._settings.gemini_model
            else None
        )
        return TranslateResponse(
            source_text=text,
            target_language=target_language,
            translated_text=translated,
            provider="gemini",
            latency_ms=latency_ms,
            note=note,
        )

    async def _translate_with_openai(
        self,
        text: str,
        target_language: TranslationLanguage,
    ) -> TranslateResponse:
        start = time.perf_counter()
        client = AsyncOpenAI(
            api_key=self._settings.openai_api_key,
            timeout=self._settings.llm_timeout_seconds,
        )
        instruction = _build_translation_instruction(target_language)
        completion = await client.chat.completions.create(
            model=self._settings.openai_llm_model,
            temperature=0.15,
            messages=[
                {"role": "system", "content": instruction},
                {"role": "user", "content": text},
            ],
        )
        translated = (completion.choices[0].message.content or "").strip()
        latency_ms = round((time.perf_counter() - start) * 1000.0, 2)
        return TranslateResponse(
            source_text=text,
            target_language=target_language,
            translated_text=translated,
            provider="openai",
            latency_ms=latency_ms,
        )
