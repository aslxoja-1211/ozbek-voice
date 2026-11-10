"""Integration tests for FastAPI REST and WebSocket endpoints."""

import math
import struct

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _make_test_client() -> TestClient:
    settings = Settings(
        stt_provider="mock",
        llm_provider="mock",
        gemini_api_key="",
        openai_api_key="",
        mohirpool_api_key="",
    )
    app = create_app(settings)
    return TestClient(app)


def _tone_pcm16(duration_s: float = 0.3, rate: int = 16000) -> bytes:
    n = int(duration_s * rate)
    samples = [int(10000 * math.sin(2.0 * math.pi * 440.0 * i / rate)) for i in range(n)]
    return struct.pack(f"<{n}h", *samples)


def test_health_and_demo_page():
    client = _make_test_client()
    health = client.get("/health")
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "ok"
    assert body["active_stt"] == "mock"
    assert body["active_llm"] == "mock"

    demo = client.get("/")
    assert demo.status_code == 200
    assert "Aqua Voice Uzbek" in demo.text


def test_rest_process_text_pipeline():
    client = _make_test_client()

    step1 = client.post(
        "/api/v1/process-text",
        json={
            "current_editor_state": "",
            "raw_transcript": "Men kecha Toshkentda uchrashuv o'tkazdim.",
        },
    )
    assert step1.status_code == 200
    state = step1.json()["diff"]["new_text"]
    assert state == "Men kecha Toshkentda uchrashuv o'tkazdim."

    step2 = client.post(
        "/api/v1/process-text",
        json={
            "current_editor_state": state,
            "raw_transcript": "kecha so'zini bugun deb o'zgartir",
        },
    )
    assert step2.status_code == 200
    data2 = step2.json()
    assert data2["command"]["action"] == "REPLACE"
    assert data2["diff"]["new_text"] == "Men bugun Toshkentda uchrashuv o'tkazdim."

    bad_provider = client.post(
        "/api/v1/process-text",
        json={
            "current_editor_state": state,
            "raw_transcript": "salom",
            "llm_provider": "gemini",
        },
    )
    assert bad_provider.status_code == 400


def test_rest_process_audio():
    client = _make_test_client()
    pcm = _tone_pcm16()
    resp = client.post(
        "/api/v1/process-audio",
        files={"file": ("speech.pcm", pcm, "audio/pcm")},
        data={"current_editor_state": "", "mime_type": "audio/pcm", "sample_rate": "16000"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["providers"]["stt_provider"] == "mock"
    assert payload["diff"]["changed"] is True
    assert len(payload["raw_transcript"]) > 0


def test_websocket_audio_and_text_commands():
    client = _make_test_client()
    pcm = _tone_pcm16()
    half = len(pcm) // 2

    with client.websocket_connect("/ws/voice") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "connected"

        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}

        ws.send_json(
            {
                "type": "start_utterance",
                "editor_state": "",
                "mime_type": "audio/pcm",
                "sample_rate": 16000,
            }
        )
        assert ws.receive_json() == {"type": "utterance_started"}

        ws.send_bytes(pcm[:half])
        ws.send_bytes(pcm[half:])
        ws.send_json({"type": "end_utterance"})

        status_msg = ws.receive_json()
        assert status_msg["type"] == "status"

        result_msg = ws.receive_json()
        assert result_msg["type"] == "result"
        assert result_msg["payload"]["diff"]["changed"] is True

        ws.send_json(
            {
                "type": "text_command",
                "raw_transcript": "hammasini o'chir",
            }
        )
        status2 = ws.receive_json()
        assert status2["type"] == "status"
        result2 = ws.receive_json()
        assert result2["payload"]["command"]["action"] == "DELETE"
        assert result2["payload"]["diff"]["new_text"] == ""
