"""Single-shot multimodal Gemini Audio -> Uzbek Transcript + Intent Engine."""

from dataclasses import dataclass
from typing import Optional

from google.genai import types

from app.audio.pcm_utils import (
    compute_pcm16_rms,
    ensure_audio_filename_and_bytes,
    estimate_pcm16_duration_ms,
)
from app.models.schemas import (
    ClientActionType,
    EditorEditCommand,
    SingleShotAudioCommand,
)
from app.services.gemini_client import (
    create_gemini_client,
    generate_with_failover,
    ordered_gemini_models,
)
from app.services.llm.prompts import UZBEK_INTENT_SYSTEM_PROMPT

SINGLE_SHOT_SYSTEM_PROMPT = (
    f"{UZBEK_INTENT_SYSTEM_PROMPT}\n\n"
    "QO'SHIMCHA AUDIO QOIDALARI (SINGLE-SHOT):\n"
    "1. Audioni eshitib, avvalo o'zbek lotin yozuvida (o', g', sh, ch bilan) aniq `raw_transcript` yozing.\n"
    "2. Agar audio bo'sh yoki faqat sukut bo'lsa, `raw_transcript=\"\"`, `replacement=\"\"`, `confidence=0.0` qaytaring.\n"
    "3. Agar foydalanuvchi faqat tahrirni bekor qilish buyrug'ini aytsa "
    "(\"bekor qil\", \"orqaga qaytar\", \"oxirgi amalni bekor qil\"), "
    "`client_action=\"UNDO\"`, `action=\"APPEND\"`, `replacement=\"\"` qiling.\n"
    "4. Agar foydalanuvchi \"oldinga qaytar\" yoki \"qayta tikla\" desa, "
    "`client_action=\"REDO\"`, `action=\"APPEND\"`, `replacement=\"\"` qiling.\n"
    "5. Oddiy gap yoki tahrirlash buyrug'i bo'lsa `client_action=null` qo'ying."
)


@dataclass(slots=True)
class SingleShotResult:
    """Output of single-shot multimodal audio understanding + intent resolution."""

    raw_transcript: str
    command: EditorEditCommand
    client_action: Optional[ClientActionType] = None
    note: Optional[str] = None
    is_silence: bool = False


class GeminiSingleShotAudioEngine:
    """Performs Uzbek audio transcription and intent resolution in a single Gemini call."""

    name = "gemini-multimodal"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.5-flash-lite",
        timeout_ms: int = 10000,
        per_attempt_timeout_s: float = 6.0,
    ) -> None:
        self._client = create_gemini_client(api_key=api_key, timeout_ms=timeout_ms)
        self._model = model
        self._per_attempt_timeout_s = per_attempt_timeout_s

    def _build_config(self, model_name: str) -> types.GenerateContentConfig:
        use_thinking_budget = "lite" not in model_name.lower()
        return types.GenerateContentConfig(
            system_instruction=SINGLE_SHOT_SYSTEM_PROMPT,
            temperature=0.05,
            response_mime_type="application/json",
            response_schema=SingleShotAudioCommand,
            thinking_config=(
                types.ThinkingConfig(thinking_budget=0)
                if use_thinking_budget
                else None
            ),
        )

    async def process_audio(
        self,
        audio_bytes: bytes,
        current_editor_state: str,
        mime_type: str = "audio/pcm",
        sample_rate: int = 16000,
    ) -> SingleShotResult:
        """Transcribe audio and infer EditorEditCommand in a single round-trip."""
        if not audio_bytes:
            return SingleShotResult(
                raw_transcript="",
                command=EditorEditCommand(
                    action="APPEND", target="", replacement="", confidence=0.0
                ),
                is_silence=True,
                note="Bo'sh audio.",
            )

        normalized_mime = (mime_type or "audio/pcm").split(";")[0].strip().lower()
        if normalized_mime in {"audio/pcm", "audio/l16"}:
            duration_ms = estimate_pcm16_duration_ms(
                len(audio_bytes), sample_rate=sample_rate
            )
            rms = compute_pcm16_rms(audio_bytes)
            if duration_ms < 120 or rms < 0.0005:
                return SingleShotResult(
                    raw_transcript="",
                    command=EditorEditCommand(
                        action="APPEND", target="", replacement="", confidence=0.0
                    ),
                    is_silence=True,
                    note="Mikrofondan sukut yoki juda qisqa audio keldi.",
                )

        _, payload, content_type = ensure_audio_filename_and_bytes(
            audio_bytes, mime_type=mime_type, sample_rate=sample_rate
        )
        state_preview = (
            current_editor_state if current_editor_state.strip() else "(bo'sh)"
        )
        prompt = (
            f'current_editor_state:\n"""\n{state_preview}\n"""\n\n'
            "Audioni o'zbek lotin yozuvida transkripsiya qiling va qat'iy JSON buyruq qaytaring."
        )

        response, used_model = await generate_with_failover(
            client=self._client,
            models=ordered_gemini_models(self._model),
            contents=[
                prompt,
                types.Part.from_bytes(data=payload, mime_type=content_type),
            ],
            config_builder=self._build_config,
            per_attempt_timeout_s=self._per_attempt_timeout_s,
        )

        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, SingleShotAudioCommand):
            combined = parsed
        else:
            raw_json = (response.text or "").strip()
            combined = SingleShotAudioCommand.model_validate_json(raw_json)

        transcript = combined.raw_transcript.strip()
        cmd = EditorEditCommand(
            action=combined.action,
            target=combined.target,
            replacement=combined.replacement,
            updated_full_text=combined.updated_full_text,
            confidence=combined.confidence,
        )
        note = (
            f"Zaxira Gemini modeli ({used_model})."
            if used_model != self._model
            else None
        )
        return SingleShotResult(
            raw_transcript=transcript,
            command=cmd,
            client_action=combined.client_action,
            note=note,
        )
