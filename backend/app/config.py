"""Application settings and provider selection configuration."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables or .env files."""

    model_config = SettingsConfigDict(
        env_file=(str(ROOT_DIR / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Aqua Voice Uzbek"
    app_version: str = "0.1.0"
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:8000,http://127.0.0.1:8000"
    )

    stt_provider: Literal["auto", "mock", "gemini", "local_whisper", "openai", "mohirpool"] = "auto"
    llm_provider: Literal["auto", "mock", "gemini", "openai"] = "auto"

    local_whisper_model: str = Field(default="turbo")
    local_whisper_device: str = Field(default="auto")
    local_whisper_compute_type: str = Field(default="float16")

    gemini_api_key: str = Field(default="")
    gemini_model: str = Field(default="gemini-3.5-flash")

    openai_api_key: str = Field(default="")
    openai_stt_model: str = Field(default="whisper-1")
    openai_llm_model: str = Field(default="gpt-4o-mini")

    mohirpool_api_key: str = Field(default="")
    mohirpool_stt_url: str = Field(default="https://mohir.ai/api/v1/stt")

    default_language: str = "uz"
    llm_timeout_seconds: float = 8.0
    stt_timeout_seconds: float = 15.0
    max_audio_bytes: int = 15 * 1024 * 1024

    def cors_origin_list(self) -> list[str]:
        """Return non-empty CORS origin URLs."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def resolved_stt_provider(self) -> str:
        """Resolve 'auto' STT selection from configured API keys or local Whisper."""
        if self.stt_provider != "auto":
            return self.stt_provider
        if self.mohirpool_api_key:
            return "mohirpool"
        if self.gemini_api_key:
            return "gemini"
        if self.openai_api_key:
            return "openai"
        from app.services.stt.local_whisper import is_local_whisper_available

        if is_local_whisper_available():
            return "local_whisper"
        return "mock"

    def resolved_llm_provider(self) -> str:
        """Resolve 'auto' LLM selection from configured API keys."""
        if self.llm_provider != "auto":
            return self.llm_provider
        if self.gemini_api_key:
            return "gemini"
        if self.openai_api_key:
            return "openai"
        return "mock"


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
