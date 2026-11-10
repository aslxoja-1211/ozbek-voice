"""OpenAI GPT-4o-mini Intent Engine using Structured Outputs."""

from openai import AsyncOpenAI

from app.models.schemas import EditorEditCommand
from app.services.llm.base import IntentEngine, IntentResult
from app.services.llm.prompts import (
    UZBEK_INTENT_SYSTEM_PROMPT,
    build_intent_user_prompt,
)


class OpenAIMiniIntentEngine(IntentEngine):
    """Low-latency Intent Engine powered by OpenAI GPT-4o-mini."""

    name = "openai"
    is_mock = False

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        timeout_seconds: float = 8.0,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key, timeout=timeout_seconds)
        self._model = model

    async def resolve_intent(
        self,
        current_editor_state: str,
        raw_transcript: str,
    ) -> IntentResult:
        """Parse Uzbek voice intent strictly into EditorEditCommand."""
        user_prompt = build_intent_user_prompt(current_editor_state, raw_transcript)
        completion = await self._client.chat.completions.parse(
            model=self._model,
            temperature=0.1,
            messages=[
                {"role": "system", "content": UZBEK_INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format=EditorEditCommand,
        )

        message = completion.choices[0].message
        if message.parsed is not None:
            command = message.parsed
        elif message.content:
            command = EditorEditCommand.model_validate_json(message.content)
        else:
            raise ValueError("OpenAI bo'sh javob qaytardi.")

        return IntentResult(command=command, provider=self.name, is_mock=False)
