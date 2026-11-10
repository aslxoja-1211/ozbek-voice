"""Google Gemini multimodal Speech-to-Text adapter optimized for Uzbek."""

from google.genai import types

from app.audio.pcm_utils import (
    compute_pcm16_rms,
    ensure_audio_filename_and_bytes,
    estimate_pcm16_duration_ms,
)
from app.services.gemini_client import (
    create_gemini_client,
    generate_with_failover,
    ordered_gemini_models,
)
from app.services.stt.base import STTProvider, STTResult

GEMINI_STT_PROMPT = (
    "Ushbu audiodagi nutqni aynan o'zbek lotin yozuvida (o', g', sh, ch bilan) "
    "transkripsiya qiling. Faqat aytilgan matnni qaytaring, qo'shimcha izoh yozmang. "
    "Agar audio bo'sh yoki faqat sukut bo'lsa, bo'sh satr qaytaring."
)


class GeminiSTTProvider(STTProvider):
    """Transcribes audio directly using Gemini Flash multimodal audio understanding."""

    name = "gemini"
    is_mock = False

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.5-flash-lite",
        timeout_ms: int = 10000,
        per_attempt_timeout_s: float = 5.0,
    ) -> None:
        self._client = create_gemini_client(api_key=api_key, timeout_ms=timeout_ms)
        self._model = model
        self._per_attempt_timeout_s = per_attempt_timeout_s

    def _build_config(self, model_name: str) -> types.GenerateContentConfig:
        use_thinking_budget = "lite" not in model_name.lower()
        return types.GenerateContentConfig(
            temperature=0.0,
            thinking_config=(
                types.ThinkingConfig(thinking_budget=0)
                if use_thinking_budget
                else None
            ),
        )

    async def transcribe(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/pcm",
        sample_rate: int = 16000,
        language: str = "uz",
    ) -> STTResult:
        """Wrap raw PCM/audio as WAV and transcribe via Gemini Flash."""
        if not audio_bytes:
            return STTResult(text="", provider=self.name, is_mock=False)

        normalized_mime = (mime_type or "audio/pcm").split(";")[0].strip().lower()
        if normalized_mime in {"audio/pcm", "audio/l16"}:
            duration_ms = estimate_pcm16_duration_ms(len(audio_bytes), sample_rate=sample_rate)
            rms = compute_pcm16_rms(audio_bytes)
            if duration_ms < 120 or rms < 0.0005:
                return STTResult(
                    text="",
                    provider=self.name,
                    is_mock=False,
                    note="Mikrofondan sukut yoki juda qisqa audio keldi.",
                )

        _, payload, content_type = ensure_audio_filename_and_bytes(
            audio_bytes, mime_type=mime_type, sample_rate=sample_rate
        )
        prompt = GEMINI_STT_PROMPT
        if language and language.lower() != "uz":
            prompt = (
                f"Transcribe the speech in this audio accurately in language '{language}'. "
                "Return only the transcript text, with no extra commentary."
            )

        response, used_model = await generate_with_failover(
            client=self._client,
            models=ordered_gemini_models(self._model),
            contents=[prompt, types.Part.from_bytes(data=payload, mime_type=content_type)],
            config_builder=self._build_config,
            per_attempt_timeout_s=self._per_attempt_timeout_s,
        )
        transcript = (response.text or "").strip().strip('"').strip()
        note = (
            f"Zaxira Gemini STT modeli ({used_model})."
            if used_model != self._model
            else None
        )
        return STTResult(text=transcript, provider=self.name, is_mock=False, note=note)
