"""Google Gemini Flash multimodal Intent Engine."""

from google.genai import types

from app.models.schemas import EditorEditCommand
from app.services.gemini_client import (
    create_gemini_client,
    generate_with_failover,
    ordered_gemini_models,
)
from app.services.llm.base import IntentEngine, IntentResult
from app.services.llm.prompts import (
    UZBEK_INTENT_SYSTEM_PROMPT,
    build_intent_user_prompt,
)


class GeminiFlashIntentEngine(IntentEngine):
    """Low-latency Intent Engine powered by Google Gemini Flash."""

    name = "gemini"
    is_mock = False

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.5-flash-lite",
        timeout_ms: int = 10000,
        per_attempt_timeout_s: float = 4.0,
    ) -> None:
        self._client = create_gemini_client(api_key=api_key, timeout_ms=timeout_ms)
        self._model = model
        self._per_attempt_timeout_s = per_attempt_timeout_s

    def _candidate_models(self) -> list[str]:
        return ordered_gemini_models(self._model)

    def _build_config(self, model_name: str) -> types.GenerateContentConfig:
        use_thinking_budget = "lite" not in model_name.lower()
        return types.GenerateContentConfig(
            system_instruction=UZBEK_INTENT_SYSTEM_PROMPT,
            temperature=0.1,
            response_mime_type="application/json",
            response_schema=EditorEditCommand,
            thinking_config=(
                types.ThinkingConfig(thinking_budget=0)
                if use_thinking_budget
                else None
            ),
        )

    async def resolve_intent(
        self,
        current_editor_state: str,
        raw_transcript: str,
    ) -> IntentResult:
        """Call Gemini Flash asynchronously with fast failover across Flash variants."""
        prompt = build_intent_user_prompt(current_editor_state, raw_transcript)
        response, used_model = await generate_with_failover(
            client=self._client,
            models=self._candidate_models(),
            contents=prompt,
            config_builder=self._build_config,
            per_attempt_timeout_s=self._per_attempt_timeout_s,
        )

        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, EditorEditCommand):
            command = parsed
        else:
            raw_json = (response.text or "").strip()
            command = EditorEditCommand.model_validate_json(raw_json)

        note = (
            f"Zaxira Gemini modeli ishlatildi ({used_model})."
            if used_model != self._model
            else None
        )
        return IntentResult(
            command=command,
            provider=self.name,
            is_mock=False,
            note=note,
        )
