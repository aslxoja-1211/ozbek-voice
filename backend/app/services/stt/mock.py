"""Demo/Mock STT adapter enabling offline testing and API-key-free previews."""

from app.audio.pcm_utils import compute_pcm16_rms, estimate_pcm16_duration_ms
from app.services.stt.base import STTProvider, STTResult

DEMO_UZBEK_PHRASES = (
    "Bugun O'zbekistonda sun'iy intellekt texnologiyalari tez rivojlanmoqda.",
    "Loyiha bo'yicha birinchi uchrashuv ertaga soat o'nda bo'lib o'tadi.",
    "ertaga so'zini bugun deb o'zgartir",
    "oxirgi gapni ro'yxatga aylantir",
)


class MockSTTProvider(STTProvider):
    """Deterministic demo STT provider when no live STT API key is configured."""

    name = "mock"
    is_mock = True

    def __init__(self) -> None:
        self._counter = 0

    async def transcribe(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/pcm",
        sample_rate: int = 16000,
        language: str = "uz",
    ) -> STTResult:
        """Validate audio buffer and return a deterministic Uzbek demo transcript."""
        if not audio_bytes:
            return STTResult(
                text="",
                provider=self.name,
                is_mock=True,
                note="Bo'sh audio bufer yuborildi.",
            )

        normalized_mime = (mime_type or "audio/pcm").split(";")[0].strip().lower()
        if normalized_mime in {"audio/pcm", "audio/l16"}:
            duration_ms = estimate_pcm16_duration_ms(len(audio_bytes), sample_rate=sample_rate)
            rms = compute_pcm16_rms(audio_bytes)
            if duration_ms < 150 or rms < 0.0005:
                return STTResult(
                    text="",
                    provider=self.name,
                    is_mock=True,
                    note="Demo STT: sukut yoki juda qisqa audio aniqlandi.",
                )

        phrase = DEMO_UZBEK_PHRASES[self._counter % len(DEMO_UZBEK_PHRASES)]
        self._counter += 1
        return STTResult(
            text=phrase,
            provider=self.name,
            is_mock=True,
            note=(
                "Demo STT rejimi faol (OPENAI_API_KEY yoki MOHIRPOOL_API_KEY "
                "kiritilmagan). Haqiqiy nutq tanish uchun .env ga kalit qo'shing."
            ),
        )
