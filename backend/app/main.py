"""FastAPI server exposing REST and WebSocket endpoints for Aqua Voice Uzbek."""

import asyncio
import base64
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.config import Settings, get_settings
from app.models.schemas import (
    HealthResponse,
    PipelineResponse,
    TextProcessRequest,
    TranslateRequest,
    TranslateResponse,
)
from app.pipeline import VoiceEditorPipeline
from app.services.llm.base import LLMConfigurationError
from app.services.stt.base import STTConfigurationError
from app.services.stt.local_whisper import (
    is_local_whisper_available,
    warmup_local_whisper,
)
from app.services.translation import (
    TranslationConfigurationError,
    TranslationService,
)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    cfg = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if cfg.resolved_stt_provider() == "local_whisper":
            asyncio.create_task(
                asyncio.to_thread(
                    warmup_local_whisper,
                    cfg.local_whisper_model,
                    cfg.local_whisper_device,
                    cfg.local_whisper_compute_type,
                )
            )
        yield

    app = FastAPI(
        title=cfg.app_name,
        version=cfg.app_version,
        description="O'zbek tili uchun AI ovozli matn muharriri (FastAPI + WebSockets)",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origin_list(),
        allow_origin_regex=r"https://.*\.vercel\.app",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.settings = cfg
    app.state.pipeline = VoiceEditorPipeline(cfg)
    app.state.translator = TranslationService(cfg)

    def get_pipeline() -> VoiceEditorPipeline:
        return app.state.pipeline

    def get_translator() -> TranslationService:
        return app.state.translator

    def get_cfg() -> Settings:
        return app.state.settings

    @app.get("/health", response_model=HealthResponse)
    async def health(active_cfg: Settings = Depends(get_cfg)) -> HealthResponse:
        """Return service status and configured provider capabilities."""
        return HealthResponse(
            status="ok",
            app_name=active_cfg.app_name,
            version=active_cfg.app_version,
            active_stt=active_cfg.resolved_stt_provider(),
            active_llm=active_cfg.resolved_llm_provider(),
            configured_providers={
                "gemini": bool(active_cfg.gemini_api_key),
                "openai": bool(active_cfg.openai_api_key),
                "mohirpool": bool(active_cfg.mohirpool_api_key),
                "local_whisper": is_local_whisper_available(),
                "mock": True,
            },
        )

    @app.get("/", include_in_schema=False)
    @app.get("/demo", include_in_schema=False)
    async def serve_demo_page() -> Any:
        """Serve the standalone Python test & live voice demo page."""
        demo_file = STATIC_DIR / "demo.html"
        if demo_file.exists():
            return FileResponse(demo_file)
        return JSONResponse(
            {
                "message": "Aqua Voice Uzbek API ishlamoqda.",
                "docs": "/docs",
                "health": "/health",
                "ws": "/ws/voice",
            }
        )

    @app.post("/api/v1/process-text", response_model=PipelineResponse)
    async def process_text(
        body: TextProcessRequest,
        pipeline: VoiceEditorPipeline = Depends(get_pipeline),
    ) -> PipelineResponse:
        """Run Intent Detection and Text Diff Engine on raw transcript text."""
        try:
            return await pipeline.process_text(
                current_editor_state=body.current_editor_state,
                raw_transcript=body.raw_transcript,
                llm_provider=body.llm_provider,
            )
        except (LLMConfigurationError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"LLM xatoligi: {exc}") from exc

    @app.post("/api/v1/process-audio", response_model=PipelineResponse)
    async def process_audio(
        file: UploadFile = File(...),
        current_editor_state: str = Form(default=""),
        mime_type: Optional[str] = Form(default=None),
        sample_rate: int = Form(default=16000),
        stt_provider: Optional[str] = Form(default=None),
        llm_provider: Optional[str] = Form(default=None),
        pipeline: VoiceEditorPipeline = Depends(get_pipeline),
        active_cfg: Settings = Depends(get_cfg),
    ) -> PipelineResponse:
        """Transcribe uploaded audio and apply contextual Uzbek voice edit."""
        audio_bytes = await file.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Audio fayl bo'sh.")
        if len(audio_bytes) > active_cfg.max_audio_bytes:
            raise HTTPException(status_code=413, detail="Audio fayl hajmi juda katta.")

        effective_mime = mime_type or file.content_type or "audio/wav"
        try:
            return await pipeline.process_audio(
                audio_bytes=audio_bytes,
                current_editor_state=current_editor_state,
                mime_type=effective_mime,
                sample_rate=sample_rate,
                stt_provider=stt_provider,
                llm_provider=llm_provider,
            )
        except (STTConfigurationError, LLMConfigurationError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Pipeline xatoligi: {exc}") from exc

    @app.post("/api/v1/translate", response_model=TranslateResponse)
    async def translate_text(
        body: TranslateRequest,
        translator: TranslationService = Depends(get_translator),
    ) -> TranslateResponse:
        """Translate Uzbek editor content into Russian ('ru') or English ('en')."""
        try:
            return await translator.translate(
                text=body.text,
                target_language=body.target_language,
                provider_override=body.provider,
            )
        except (TranslationConfigurationError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Tarjima xatoligi: {exc}") from exc

    @app.websocket("/ws/voice")
    async def voice_websocket(websocket: WebSocket) -> None:
        """Real-time WebSocket endpoint for streaming PCM/Opus audio and editor commands."""
        await websocket.accept()
        pipeline: VoiceEditorPipeline = app.state.pipeline
        active_cfg: Settings = app.state.settings

        audio_buffer = bytearray()
        editor_state = ""
        mime_type = "audio/pcm"
        sample_rate = 16000
        stt_provider: Optional[str] = None
        llm_provider: Optional[str] = None

        await websocket.send_json(
            {
                "type": "connected",
                "active_stt": active_cfg.resolved_stt_provider(),
                "active_llm": active_cfg.resolved_llm_provider(),
            }
        )

        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break

                raw_bytes = message.get("bytes")
                if raw_bytes is not None:
                    if len(audio_buffer) + len(raw_bytes) > active_cfg.max_audio_bytes:
                        audio_buffer.clear()
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": "Audio bufer maksimal hajmdan oshib ketdi.",
                            }
                        )
                        continue
                    audio_buffer.extend(raw_bytes)
                    continue

                raw_text = message.get("text")
                if raw_text is None:
                    continue

                try:
                    import json

                    data = json.loads(raw_text)
                except Exception:
                    await websocket.send_json(
                        {"type": "error", "message": "Noto'g'ri JSON xabar."}
                    )
                    continue

                msg_type = data.get("type")
                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})

                elif msg_type == "sync_state":
                    editor_state = str(data.get("editor_state", ""))

                elif msg_type == "start_utterance":
                    audio_buffer.clear()
                    if "editor_state" in data:
                        editor_state = str(data.get("editor_state", ""))
                    mime_type = str(data.get("mime_type", "audio/pcm"))
                    sample_rate = int(data.get("sample_rate", 16000))
                    stt_provider = data.get("stt_provider") or None
                    llm_provider = data.get("llm_provider") or None
                    await websocket.send_json({"type": "utterance_started"})

                elif msg_type == "audio_chunk":
                    chunk_b64 = data.get("data", "")
                    if chunk_b64:
                        decoded = base64.b64decode(chunk_b64)
                        if len(audio_buffer) + len(decoded) <= active_cfg.max_audio_bytes:
                            audio_buffer.extend(decoded)

                elif msg_type == "end_utterance":
                    if "editor_state" in data:
                        editor_state = str(data.get("editor_state", ""))
                    if data.get("stt_provider") is not None:
                        stt_provider = data.get("stt_provider") or None
                    if data.get("llm_provider") is not None:
                        llm_provider = data.get("llm_provider") or None

                    payload_bytes = bytes(audio_buffer)
                    audio_buffer.clear()

                    if not payload_bytes:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": "Hech qanday audio ma'lumot yuborilmadi.",
                            }
                        )
                        continue

                    await websocket.send_json({"type": "status", "stage": "processing"})
                    try:
                        result = await pipeline.process_audio(
                            audio_bytes=payload_bytes,
                            current_editor_state=editor_state,
                            mime_type=mime_type,
                            sample_rate=sample_rate,
                            stt_provider=stt_provider,
                            llm_provider=llm_provider,
                        )
                        editor_state = result.diff.new_text
                        await websocket.send_json(
                            {"type": "result", "payload": result.model_dump()}
                        )
                    except WebSocketDisconnect:
                        raise
                    except Exception as exc:
                        await websocket.send_json(
                            {"type": "error", "message": str(exc)}
                        )

                elif msg_type == "text_command":
                    if "editor_state" in data:
                        editor_state = str(data.get("editor_state", ""))
                    raw_transcript = str(data.get("raw_transcript", "")).strip()
                    req_llm = data.get("llm_provider") or llm_provider
                    if not raw_transcript:
                        await websocket.send_json(
                            {"type": "error", "message": "raw_transcript bo'sh."}
                        )
                        continue

                    await websocket.send_json({"type": "status", "stage": "analyzing"})
                    try:
                        result = await pipeline.process_text(
                            current_editor_state=editor_state,
                            raw_transcript=raw_transcript,
                            llm_provider=req_llm,
                        )
                        editor_state = result.diff.new_text
                        await websocket.send_json(
                            {"type": "result", "payload": result.model_dump()}
                        )
                    except WebSocketDisconnect:
                        raise
                    except Exception as exc:
                        await websocket.send_json(
                            {"type": "error", "message": str(exc)}
                        )

                elif msg_type == "translate":
                    text_to_translate = str(data.get("text", ""))
                    target_lang = str(data.get("target_language", "ru")).lower()
                    if target_lang not in {"ru", "en"}:
                        await websocket.send_json(
                            {
                                "type": "translation_error",
                                "message": "Faqat 'ru' yoki 'en' tillari qo'llab-quvvatlanadi.",
                            }
                        )
                        continue
                    req_provider = data.get("provider") or None
                    await websocket.send_json(
                        {"type": "translation_status", "target_language": target_lang}
                    )
                    try:
                        translator_svc: TranslationService = app.state.translator
                        trans_res = await translator_svc.translate(
                            text=text_to_translate,
                            target_language=target_lang,  # type: ignore[arg-type]
                            provider_override=req_provider,
                        )
                        await websocket.send_json(
                            {
                                "type": "translation_result",
                                "payload": trans_res.model_dump(),
                            }
                        )
                    except WebSocketDisconnect:
                        raise
                    except Exception as exc:
                        await websocket.send_json(
                            {"type": "translation_error", "message": str(exc)}
                        )
                else:
                    await websocket.send_json(
                        {"type": "error", "message": f"Noma'lum xabar turi: {msg_type}"}
                    )

        except WebSocketDisconnect:
            return

    return app


app = create_app()
