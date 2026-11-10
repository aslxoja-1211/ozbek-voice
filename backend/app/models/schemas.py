"""Strict JSON schemas for STT, LLM Intent Engine, Text Diff Engine, and WebSocket API."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

ActionType = Literal["APPEND", "REPLACE", "DELETE", "FORMAT"]
ClientActionType = Literal["UNDO", "REDO"]
TranslationLanguage = Literal["ru", "en"]


class EditorEditCommand(BaseModel):
    """Strict LLM output schema for contextual Uzbek voice editing commands."""

    action: ActionType = Field(
        description="Editor action: APPEND, REPLACE, DELETE, or FORMAT."
    )
    target: str = Field(
        default="",
        description="Text span or segment to modify/delete/format; empty for APPEND.",
    )
    replacement: str = Field(
        default="",
        description="New text to append, replace with, or formatted replacement.",
    )
    updated_full_text: Optional[str] = Field(
        default=None,
        description="Optional full updated text when diff is complex.",
    )
    confidence: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0.",
    )


class TextSpan(BaseModel):
    """Character range in the source editor text."""

    start: int = Field(ge=0)
    end: int = Field(ge=0)
    matched_text: str


class ApplyResult(BaseModel):
    """Outcome of applying an EditorEditCommand to current editor text."""

    previous_text: str
    new_text: str
    changed: bool
    applied_strategy: str
    matched_span: Optional[TextSpan] = None
    format_hint: Optional[str] = None


class LatencyMetrics(BaseModel):
    """Execution timing metrics in milliseconds."""

    stt_ms: float = 0.0
    llm_ms: float = 0.0
    diff_ms: float = 0.0
    total_ms: float = 0.0


class ProviderInfo(BaseModel):
    """Active provider metadata."""

    stt_provider: str
    llm_provider: str
    stt_is_mock: bool = False
    llm_is_mock: bool = False


class TextProcessRequest(BaseModel):
    """REST request for running Intent + Diff directly on transcript text."""

    current_editor_state: str = ""
    raw_transcript: str = Field(min_length=1)
    stt_provider: Optional[str] = None
    llm_provider: Optional[str] = None


class SingleShotAudioCommand(BaseModel):
    """Combined transcription + intent schema for single-shot multimodal Gemini calls."""

    raw_transcript: str = Field(
        default="",
        description="Exact Uzbek Latin transcript of the spoken audio.",
    )
    action: ActionType = Field(default="APPEND")
    target: str = Field(default="")
    replacement: str = Field(default="")
    updated_full_text: Optional[str] = Field(default=None)
    confidence: float = Field(default=0.95, ge=0.0, le=1.0)
    client_action: Optional[ClientActionType] = Field(default=None)


class PipelineResponse(BaseModel):
    """Full response returned by REST and WebSocket endpoints."""

    raw_transcript: str
    command: EditorEditCommand
    diff: ApplyResult
    latency: LatencyMetrics
    providers: ProviderInfo
    client_action: Optional[ClientActionType] = None
    note: Optional[str] = None


class HealthResponse(BaseModel):
    """Health and active configuration summary."""

    status: str
    app_name: str
    version: str
    active_stt: str
    active_llm: str
    configured_providers: dict[str, bool]


class TranslateRequest(BaseModel):
    """REST request for translating Uzbek editor content to Russian or English."""

    text: str = ""
    target_language: TranslationLanguage = "ru"
    provider: Optional[str] = None


class TranslateResponse(BaseModel):
    """Structured translation output for the editor's translation pane."""

    source_text: str
    target_language: TranslationLanguage
    translated_text: str
    provider: str
    latency_ms: float = 0.0
    note: Optional[str] = None
