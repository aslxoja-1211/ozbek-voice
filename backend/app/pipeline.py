"""Core orchestration pipeline: Audio -> STT -> LLM Intent Engine -> Text Diff Engine."""

import time
from typing import Optional

from app.config import Settings
from app.editor.diff_engine import apply_edit_command
from app.editor.uzbek_text import detect_client_action
from app.models.schemas import (
    ApplyResult,
    ClientActionType,
    EditorEditCommand,
    LatencyMetrics,
    PipelineResponse,
    ProviderInfo,
)
from app.services.llm.base import LLMConfigurationError
from app.services.llm.factory import create_intent_engine
from app.services.llm.gemini_audio_intent import GeminiSingleShotAudioEngine
from app.services.llm.rule_fallback import RuleFallbackIntentEngine
from app.services.stt.base import STTConfigurationError
from app.services.stt.factory import create_stt_provider
from app.services.stt.local_whisper import (
    LocalWhisperSTTProvider,
    is_local_whisper_available,
)


def _client_action_response(
    current_editor_state: str,
    raw_transcript: str,
    client_action: ClientActionType,
    stt_provider_name: str,
    llm_provider_name: str,
    stt_ms: float = 0.0,
    llm_ms: float = 0.0,
    stt_is_mock: bool = False,
    llm_is_mock: bool = False,
    note: Optional[str] = None,
) -> PipelineResponse:
    """Build a PipelineResponse instructing the editor to execute client Undo/Redo."""
    strategy = "client_undo" if client_action == "UNDO" else "client_redo"
    return PipelineResponse(
        raw_transcript=raw_transcript.strip(),
        command=EditorEditCommand(
            action="APPEND",
            target="",
            replacement="",
            updated_full_text=None,
            confidence=0.99,
        ),
        diff=ApplyResult(
            previous_text=current_editor_state,
            new_text=current_editor_state,
            changed=False,
            applied_strategy=strategy,
        ),
        latency=LatencyMetrics(
            stt_ms=round(stt_ms, 2),
            llm_ms=round(llm_ms, 2),
            diff_ms=0.0,
            total_ms=round(stt_ms + llm_ms, 2),
        ),
        providers=ProviderInfo(
            stt_provider=stt_provider_name,
            llm_provider=llm_provider_name,
            stt_is_mock=stt_is_mock,
            llm_is_mock=llm_is_mock,
        ),
        client_action=client_action,
        note=note,
    )


def _empty_transcript_response(
    current_editor_state: str,
    stt_provider: str,
    llm_provider: str,
    stt_ms: float,
    stt_is_mock: bool,
    note: Optional[str],
) -> PipelineResponse:
    """Build a no-op response when STT detects silence or empty speech."""
    return PipelineResponse(
        raw_transcript="",
        command=EditorEditCommand(
            action="APPEND",
            target="",
            replacement="",
            updated_full_text=None,
            confidence=0.0,
        ),
        diff=ApplyResult(
            previous_text=current_editor_state,
            new_text=current_editor_state,
            changed=False,
            applied_strategy="empty_transcript",
        ),
        latency=LatencyMetrics(stt_ms=round(stt_ms, 2), total_ms=round(stt_ms, 2)),
        providers=ProviderInfo(
            stt_provider=stt_provider,
            llm_provider=llm_provider,
            stt_is_mock=stt_is_mock,
            llm_is_mock=llm_provider == "mock",
        ),
        note=note or "Transkript bo'sh qaytdi.",
    )


class VoiceEditorPipeline:
    """Coordinates STT transcription, Uzbek intent resolution, and diff application."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._single_shot_gemini: Optional[GeminiSingleShotAudioEngine] = None

    def _get_single_shot_gemini(self) -> GeminiSingleShotAudioEngine:
        if self._single_shot_gemini is None:
            self._single_shot_gemini = GeminiSingleShotAudioEngine(
                api_key=self._settings.gemini_api_key,
                model=self._settings.gemini_model,
                timeout_ms=max(10000, int(self._settings.llm_timeout_seconds * 1000)),
            )
        return self._single_shot_gemini

    async def process_text(
        self,
        current_editor_state: str,
        raw_transcript: str,
        llm_provider: Optional[str] = None,
        stt_provider_name: str = "direct-text",
        stt_ms: float = 0.0,
        stt_is_mock: bool = False,
        stt_note: Optional[str] = None,
    ) -> PipelineResponse:
        """Run LLM Intent Detection and Diff Engine on an existing transcript."""
        total_start = time.perf_counter()

        # Instant deterministic voice Undo/Redo check (<0.1ms) before any LLM call.
        client_action = detect_client_action(raw_transcript)
        if client_action is not None:
            resolved_llm = llm_provider or self._settings.resolved_llm_provider()
            return _client_action_response(
                current_editor_state=current_editor_state,
                raw_transcript=raw_transcript,
                client_action=client_action,
                stt_provider_name=stt_provider_name,
                llm_provider_name=resolved_llm,
                stt_ms=stt_ms,
                llm_ms=round((time.perf_counter() - total_start) * 1000.0, 2),
                stt_is_mock=stt_is_mock,
                llm_is_mock=resolved_llm == "mock",
                note=stt_note,
            )

        engine = create_intent_engine(self._settings, override=llm_provider)

        llm_start = time.perf_counter()
        fallback_note: Optional[str] = None
        try:
            intent_res = await engine.resolve_intent(current_editor_state, raw_transcript)
        except Exception as exc:
            if llm_provider and llm_provider != "auto":
                raise
            fallback_engine = RuleFallbackIntentEngine()
            intent_res = await fallback_engine.resolve_intent(
                current_editor_state, raw_transcript
            )
            fallback_note = (
                f"{engine.name} LLM xatoligi ({type(exc).__name__}), "
                "lokal zaxira tahlilchi ishlatildi."
            )
        llm_ms = (time.perf_counter() - llm_start) * 1000.0

        diff_start = time.perf_counter()
        diff_res = apply_edit_command(current_editor_state, intent_res.command)
        diff_ms = (time.perf_counter() - diff_start) * 1000.0

        total_ms = stt_ms + (time.perf_counter() - total_start) * 1000.0
        intent_note = None if fallback_note else intent_res.note
        notes = [n for n in (stt_note, fallback_note, intent_note) if n]

        return PipelineResponse(
            raw_transcript=raw_transcript.strip(),
            command=intent_res.command,
            diff=diff_res,
            latency=LatencyMetrics(
                stt_ms=round(stt_ms, 2),
                llm_ms=round(llm_ms, 2),
                diff_ms=round(diff_ms, 2),
                total_ms=round(total_ms, 2),
            ),
            providers=ProviderInfo(
                stt_provider=stt_provider_name,
                llm_provider=intent_res.provider,
                stt_is_mock=stt_is_mock,
                llm_is_mock=intent_res.is_mock,
            ),
            note=" | ".join(notes) if notes else None,
        )

    async def process_audio(
        self,
        audio_bytes: bytes,
        current_editor_state: str,
        mime_type: str = "audio/pcm",
        sample_rate: int = 16000,
        language: Optional[str] = None,
        stt_provider: Optional[str] = None,
        llm_provider: Optional[str] = None,
    ) -> PipelineResponse:
        """Transcribe audio via single-shot Gemini or modular STT -> Intent -> Diff."""
        effective_stt = (
            (stt_provider or self._settings.resolved_stt_provider()).strip().lower()
        )
        if effective_stt == "auto":
            effective_stt = self._settings.resolved_stt_provider()

        effective_llm = (
            (llm_provider or self._settings.resolved_llm_provider()).strip().lower()
        )
        if effective_llm == "auto":
            effective_llm = self._settings.resolved_llm_provider()

        # Fast path: Single-Shot Multimodal Gemini (Audio -> Transcript + Intent in 1 call).
        if (
            effective_stt == "gemini"
            and effective_llm == "gemini"
            and self._settings.gemini_api_key
            and (language or self._settings.default_language).lower() == "uz"
        ):
            try:
                shot_start = time.perf_counter()
                shot_res = await self._get_single_shot_gemini().process_audio(
                    audio_bytes=audio_bytes,
                    current_editor_state=current_editor_state,
                    mime_type=mime_type,
                    sample_rate=sample_rate,
                )
                shot_ms = (time.perf_counter() - shot_start) * 1000.0

                if shot_res.is_silence or not shot_res.raw_transcript:
                    return _empty_transcript_response(
                        current_editor_state=current_editor_state,
                        stt_provider="gemini-multimodal",
                        llm_provider="gemini",
                        stt_ms=shot_ms,
                        stt_is_mock=False,
                        note=shot_res.note,
                    )

                action_hint = shot_res.client_action or detect_client_action(
                    shot_res.raw_transcript
                )
                if action_hint is not None:
                    return _client_action_response(
                        current_editor_state=current_editor_state,
                        raw_transcript=shot_res.raw_transcript,
                        client_action=action_hint,
                        stt_provider_name="gemini-multimodal",
                        llm_provider_name="gemini",
                        stt_ms=0.0,
                        llm_ms=shot_ms,
                        note=shot_res.note,
                    )

                diff_start = time.perf_counter()
                diff_res = apply_edit_command(current_editor_state, shot_res.command)
                diff_ms = (time.perf_counter() - diff_start) * 1000.0

                return PipelineResponse(
                    raw_transcript=shot_res.raw_transcript,
                    command=shot_res.command,
                    diff=diff_res,
                    latency=LatencyMetrics(
                        stt_ms=0.0,
                        llm_ms=round(shot_ms, 2),
                        diff_ms=round(diff_ms, 2),
                        total_ms=round(shot_ms + diff_ms, 2),
                    ),
                    providers=ProviderInfo(
                        stt_provider="gemini-multimodal",
                        llm_provider="gemini",
                        stt_is_mock=False,
                        llm_is_mock=False,
                    ),
                    note=shot_res.note,
                )
            except Exception as exc:
                if (stt_provider and stt_provider != "auto") or not is_local_whisper_available():
                    # Fall through to modular 2-step STT -> Intent fallback below.
                    pass
                else:
                    return await self._fallback_whisper_pipeline(
                        audio_bytes=audio_bytes,
                        current_editor_state=current_editor_state,
                        mime_type=mime_type,
                        sample_rate=sample_rate,
                        language=language or self._settings.default_language,
                        llm_provider=llm_provider,
                        reason=f"Gemini single-shot xatoligi ({type(exc).__name__})",
                    )

        stt = create_stt_provider(self._settings, override=stt_provider)
        target_lang = language or self._settings.default_language

        stt_start = time.perf_counter()
        stt_fallback_note: Optional[str] = None
        try:
            stt_res = await stt.transcribe(
                audio_bytes=audio_bytes,
                mime_type=mime_type,
                sample_rate=sample_rate,
                language=target_lang,
            )
        except Exception as exc:
            if (
                (stt_provider and stt_provider != "auto")
                or not is_local_whisper_available()
                or isinstance(exc, (STTConfigurationError, LLMConfigurationError))
            ):
                raise
            return await self._fallback_whisper_pipeline(
                audio_bytes=audio_bytes,
                current_editor_state=current_editor_state,
                mime_type=mime_type,
                sample_rate=sample_rate,
                language=target_lang,
                llm_provider=llm_provider,
                reason=f"{stt.name} STT xatoligi ({type(exc).__name__})",
            )
        stt_ms = (time.perf_counter() - stt_start) * 1000.0

        if not stt_res.text.strip():
            resolved_llm = llm_provider or self._settings.resolved_llm_provider()
            notes = [n for n in (stt_fallback_note, stt_res.note) if n]
            return _empty_transcript_response(
                current_editor_state=current_editor_state,
                stt_provider=stt_res.provider,
                llm_provider=resolved_llm,
                stt_ms=stt_ms,
                stt_is_mock=stt_res.is_mock,
                note=" | ".join(notes) if notes else None,
            )

        merged_note = " | ".join(n for n in (stt_fallback_note, stt_res.note) if n) or None
        return await self.process_text(
            current_editor_state=current_editor_state,
            raw_transcript=stt_res.text,
            llm_provider=llm_provider,
            stt_provider_name=stt_res.provider,
            stt_ms=stt_ms,
            stt_is_mock=stt_res.is_mock,
            stt_note=merged_note,
        )

    async def _fallback_whisper_pipeline(
        self,
        audio_bytes: bytes,
        current_editor_state: str,
        mime_type: str,
        sample_rate: int,
        language: str,
        llm_provider: Optional[str],
        reason: str,
    ) -> PipelineResponse:
        """Fallback to local Whisper STT and continue standard text intent pipeline."""
        stt_start = time.perf_counter()
        local_stt = LocalWhisperSTTProvider(
            model_size=self._settings.local_whisper_model,
            device=self._settings.local_whisper_device,
            compute_type=self._settings.local_whisper_compute_type,
        )
        stt_res = await local_stt.transcribe(
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            sample_rate=sample_rate,
            language=language,
        )
        stt_ms = (time.perf_counter() - stt_start) * 1000.0
        note = f"{reason}, lokal Whisper ishlatildi."

        if not stt_res.text.strip():
            resolved_llm = llm_provider or self._settings.resolved_llm_provider()
            return _empty_transcript_response(
                current_editor_state=current_editor_state,
                stt_provider=stt_res.provider,
                llm_provider=resolved_llm,
                stt_ms=stt_ms,
                stt_is_mock=False,
                note=note,
            )

        return await self.process_text(
            current_editor_state=current_editor_state,
            raw_transcript=stt_res.text,
            llm_provider=llm_provider,
            stt_provider_name=stt_res.provider,
            stt_ms=stt_ms,
            stt_is_mock=False,
            stt_note=note,
        )
