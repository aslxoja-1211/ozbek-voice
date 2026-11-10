"""Tests for voice Undo/Redo detection and Single-Shot Gemini Audio-to-Intent pipeline."""

import math
import struct

from fastapi.testclient import TestClient

from app.config import Settings
from app.editor.uzbek_text import detect_client_action
from app.main import create_app
from app.models.schemas import EditorEditCommand
from app.services.llm.gemini_audio_intent import SingleShotResult


def _tone_pcm16(duration_s: float = 0.25, rate: int = 16000) -> bytes:
    n = int(duration_s * rate)
    samples = [int(10000 * math.sin(2.0 * math.pi * 440.0 * i / rate)) for i in range(n)]
    return struct.pack(f"<{n}h", *samples)


def test_detect_client_action_uzbek_commands():
    assert detect_client_action("bekor qil") == "UNDO"
    assert detect_client_action("Oxirgi amalni bekor qil.") == "UNDO"
    assert detect_client_action("orqaga qaytar") == "UNDO"
    assert detect_client_action("oldinga qaytar") == "REDO"
    assert detect_client_action("qayta tikla!") == "REDO"

    # Normal sentences containing "bekor qil..." must NOT trigger UNDO.
    assert detect_client_action("Men uchrashuvni bekor qildim.") is None
    assert detect_client_action("Bugun ob-havo yaxshi.") is None


def test_websocket_voice_undo_and_redo():
    cfg = Settings(
        stt_provider="mock",
        llm_provider="mock",
        gemini_api_key="",
        openai_api_key="",
        mohirpool_api_key="",
    )
    client = TestClient(create_app(cfg))
    with client.websocket_connect("/ws/voice") as ws:
        ws.receive_json()  # connected

        ws.send_json({"type": "text_command", "raw_transcript": "bekor qil"})
        ws.receive_json()  # status
        res = ws.receive_json()
        assert res["type"] == "result"
        assert res["payload"]["client_action"] == "UNDO"
        assert res["payload"]["diff"]["applied_strategy"] == "client_undo"

        ws.send_json({"type": "text_command", "raw_transcript": "oldinga qaytar"})
        ws.receive_json()  # status
        res2 = ws.receive_json()
        assert res2["payload"]["client_action"] == "REDO"
        assert res2["payload"]["diff"]["applied_strategy"] == "client_redo"


def test_single_shot_gemini_audio_pipeline(monkeypatch):
    cfg = Settings(
        stt_provider="gemini",
        llm_provider="gemini",
        gemini_api_key="test-gemini-key",
        openai_api_key="",
        mohirpool_api_key="",
    )
    app = create_app(cfg)

    class FakeSingleShot:
        async def process_audio(
            self,
            audio_bytes: bytes,
            current_editor_state: str,
            mime_type: str = "audio/pcm",
            sample_rate: int = 16000,
        ) -> SingleShotResult:
            if "kecha" in current_editor_state:
                return SingleShotResult(
                    raw_transcript="kecha so'zini bugun deb o'zgartir",
                    command=EditorEditCommand(
                        action="REPLACE",
                        target="kecha",
                        replacement="bugun",
                        confidence=0.98,
                    ),
                )
            return SingleShotResult(
                raw_transcript="Men kecha keldim.",
                command=EditorEditCommand(
                    action="APPEND",
                    target="",
                    replacement="Men kecha keldim.",
                    confidence=0.97,
                ),
            )

    monkeypatch.setattr(app.state.pipeline, "_get_single_shot_gemini", lambda: FakeSingleShot())
    client = TestClient(app)

    pcm = _tone_pcm16()
    r1 = client.post(
        "/api/v1/process-audio",
        files={"file": ("voice.pcm", pcm, "audio/pcm")},
        data={"current_editor_state": "", "mime_type": "audio/pcm", "sample_rate": "16000"},
    )
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["providers"]["stt_provider"] == "gemini-multimodal"
    assert d1["providers"]["llm_provider"] == "gemini"
    assert d1["diff"]["new_text"] == "Men kecha keldim."

    r2 = client.post(
        "/api/v1/process-audio",
        files={"file": ("voice.pcm", pcm, "audio/pcm")},
        data={
            "current_editor_state": d1["diff"]["new_text"],
            "mime_type": "audio/pcm",
            "sample_rate": "16000",
        },
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["command"]["action"] == "REPLACE"
    assert d2["diff"]["new_text"] == "Men bugun keldim."
