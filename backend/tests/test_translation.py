"""Tests for REST and WebSocket Uzbek -> Russian / English translation."""

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models.schemas import TranslateResponse


def _make_client() -> TestClient:
    cfg = Settings(
        stt_provider="mock",
        llm_provider="mock",
        gemini_api_key="",
        openai_api_key="",
        mohirpool_api_key="",
    )
    return TestClient(create_app(cfg))


def test_translate_empty_text_returns_empty_response():
    client = _make_client()
    resp = client.post(
        "/api/v1/translate",
        json={"text": "   ", "target_language": "ru"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["translated_text"] == ""
    assert data["provider"] == "none"


def test_translate_without_api_key_returns_400():
    client = _make_client()
    resp = client.post(
        "/api/v1/translate",
        json={"text": "Salom dunyo", "target_language": "en"},
    )
    assert resp.status_code == 400


def test_translate_rest_and_websocket_with_mocked_translator(monkeypatch):
    cfg = Settings(
        stt_provider="mock",
        llm_provider="gemini",
        gemini_api_key="test-key",
        openai_api_key="",
        mohirpool_api_key="",
    )
    app = create_app(cfg)

    async def fake_translate(text: str, target_language: str = "ru", provider_override=None):
        mapping = {
            "ru": "Сегодня в Ташкенте отличная погода.",
            "en": "Today the weather in Tashkent is great.",
        }
        return TranslateResponse(
            source_text=text,
            target_language=target_language,  # type: ignore[arg-type]
            translated_text=mapping[target_language],
            provider="gemini",
            latency_ms=42.5,
        )

    monkeypatch.setattr(app.state.translator, "translate", fake_translate)
    client = TestClient(app)

    ru_resp = client.post(
        "/api/v1/translate",
        json={"text": "Bugun Toshkentda ob-havo juda yaxshi.", "target_language": "ru"},
    )
    assert ru_resp.status_code == 200
    assert ru_resp.json()["translated_text"] == "Сегодня в Ташкенте отличная погода."

    with client.websocket_connect("/ws/voice") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "connected"

        ws.send_json(
            {
                "type": "translate",
                "text": "Bugun Toshkentda ob-havo juda yaxshi.",
                "target_language": "en",
            }
        )
        status = ws.receive_json()
        assert status == {"type": "translation_status", "target_language": "en"}

        res = ws.receive_json()
        assert res["type"] == "translation_result"
        assert res["payload"]["translated_text"] == "Today the weather in Tashkent is great."

        ws.send_json(
            {
                "type": "translate",
                "text": "Salom",
                "target_language": "fr",
            }
        )
        err = ws.receive_json()
        assert err["type"] == "translation_error"
