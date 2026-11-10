"""Tests for STT/LLM provider factories and Mohirpool transcript extraction."""

import pytest

from app.config import Settings
from app.services.llm.base import LLMConfigurationError
from app.services.llm.factory import create_intent_engine
from app.services.stt.base import STTConfigurationError
from app.services.stt.factory import create_stt_provider
from app.services.stt.local_whisper import is_local_whisper_available
from app.services.stt.mohirpool import _extract_transcript


def test_auto_provider_resolution_priority(monkeypatch):
    monkeypatch.setattr(
        "app.services.stt.local_whisper.is_local_whisper_available",
        lambda: False,
    )
    default_cfg = Settings(
        stt_provider="auto",
        llm_provider="auto",
        gemini_api_key="",
        openai_api_key="",
        mohirpool_api_key="",
    )
    assert default_cfg.resolved_stt_provider() == "mock"
    assert default_cfg.resolved_llm_provider() == "mock"

    monkeypatch.setattr(
        "app.services.stt.local_whisper.is_local_whisper_available",
        lambda: True,
    )
    assert default_cfg.resolved_stt_provider() == "local_whisper"

    configured_cfg = Settings(
        stt_provider="auto",
        llm_provider="auto",
        gemini_api_key="test-gemini",
        openai_api_key="test-openai",
        mohirpool_api_key="test-mohir",
    )
    assert configured_cfg.resolved_stt_provider() == "mohirpool"
    assert configured_cfg.resolved_llm_provider() == "gemini"
    assert create_stt_provider(configured_cfg).name == "mohirpool"
    assert create_intent_engine(configured_cfg).name == "gemini"

    gemini_only_cfg = Settings(
        stt_provider="auto",
        llm_provider="auto",
        gemini_api_key="test-gemini",
        openai_api_key="",
        mohirpool_api_key="",
    )
    assert gemini_only_cfg.resolved_stt_provider() == "gemini"
    assert gemini_only_cfg.resolved_llm_provider() == "gemini"
    assert create_stt_provider(gemini_only_cfg).name == "gemini"


def test_missing_api_keys_raise_configuration_errors():
    empty_cfg = Settings(
        gemini_api_key="",
        openai_api_key="",
        mohirpool_api_key="",
    )
    with pytest.raises(STTConfigurationError):
        create_stt_provider(empty_cfg, override="gemini")
    with pytest.raises(STTConfigurationError):
        create_stt_provider(empty_cfg, override="mohirpool")
    with pytest.raises(STTConfigurationError):
        create_stt_provider(empty_cfg, override="openai")
    with pytest.raises(LLMConfigurationError):
        create_intent_engine(empty_cfg, override="gemini")
    with pytest.raises(LLMConfigurationError):
        create_intent_engine(empty_cfg, override="openai")


def test_mohirpool_extract_transcript_variants():
    assert _extract_transcript({"text": "Salom O'zbekiston"}) == "Salom O'zbekiston"
    assert _extract_transcript({"result": {"transcript": "Bugun havo ochiq"}}) == "Bugun havo ochiq"
    assert _extract_transcript({"data": {"text": "Yangi xatboshi"}}) == "Yangi xatboshi"
    assert _extract_transcript("  Oddiy matn  ") == "Oddiy matn"
    assert _extract_transcript({}) == ""


def test_local_whisper_factory_instantiation():
    if not is_local_whisper_available():
        pytest.skip("faster-whisper o'rnatilmagan")
    cfg = Settings(stt_provider="local_whisper", local_whisper_model="base")
    provider = create_stt_provider(cfg)
    assert provider.name == "local_whisper"
    assert provider.is_mock is False
