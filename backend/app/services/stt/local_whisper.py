"""Local offline Speech-to-Text adapter powered by faster-whisper."""

from __future__ import annotations

import asyncio
import ctypes
import importlib.util
import io
import os
import sys
import wave
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

from app.audio.pcm_utils import (
    compute_pcm16_rms,
    estimate_pcm16_duration_ms,
)
from app.services.stt.base import (
    STTConfigurationError,
    STTProvider,
    STTResult,
    UZBEK_WHISPER_PROMPT,
)

_DLL_HANDLES: list[object] = []


def _register_nvidia_dll_dirs() -> None:
    """Register pip-installed NVIDIA cuBLAS/cuDNN DLL folders on Windows."""
    if sys.platform != "win32" or _DLL_HANDLES:
        return
    for site_dir in sys.path:
        nvidia_root = Path(site_dir) / "nvidia"
        if not nvidia_root.is_dir():
            continue
        for bin_dir in nvidia_root.glob("*/bin"):
            if bin_dir.is_dir():
                os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"
                _DLL_HANDLES.append(os.add_dll_directory(str(bin_dir)))


def is_local_whisper_available() -> bool:
    """Return True when faster-whisper is installed in the current environment."""
    return importlib.util.find_spec("faster_whisper") is not None


def _cuda_runtime_available() -> bool:
    """Return True only if CUDA cuBLAS 12 DLL can actually be loaded."""
    _register_nvidia_dll_dirs()
    try:
        ctypes.WinDLL("cublas64_12.dll" if sys.platform == "win32" else "libcublas.so.12")
        return True
    except OSError:
        return False


@lru_cache(maxsize=2)
def _load_whisper_model(model_size: str, device: str, compute_type: str):
    """Lazily load and cache WhisperModel, using CUDA only when runtime DLLs exist."""
    from faster_whisper import WhisperModel

    effective_device = device
    effective_compute = compute_type
    if effective_device == "auto":
        if _cuda_runtime_available():
            effective_device = "cuda"
        else:
            effective_device = "cpu"
            effective_compute = "int8"

    try:
        if effective_device == "cpu":
            return WhisperModel(
                model_size,
                device="cpu",
                compute_type=effective_compute,
                cpu_threads=min(8, os.cpu_count() or 4),
            )
        return WhisperModel(model_size, device=effective_device, compute_type=effective_compute)
    except Exception:
        if effective_device != "cpu":
            return WhisperModel(
                model_size,
                device="cpu",
                compute_type="int8",
                cpu_threads=min(8, os.cpu_count() or 4),
            )
        raise


def warmup_local_whisper(
    model_size: str = "turbo",
    device: str = "auto",
    compute_type: str = "float16",
) -> None:
    """Preload Whisper model into memory if faster-whisper is installed."""
    if is_local_whisper_available():
        _load_whisper_model(model_size, device, compute_type)


def _pcm16_to_float32_16k(
    pcm_bytes: bytes,
    sample_rate: int = 16000,
    channels: int = 1,
) -> np.ndarray:
    """Convert raw PCM16 bytes directly into 16kHz mono float32 ndarray."""
    import numpy as np

    aligned = len(pcm_bytes) - (len(pcm_bytes) % (2 * channels))
    if aligned <= 0:
        return np.zeros(0, dtype=np.float32)
    samples = np.frombuffer(pcm_bytes[:aligned], dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    if sample_rate != 16000 and len(samples) > 0:
        target_len = max(1, int(round(len(samples) * 16000 / sample_rate)))
        x_old = np.linspace(0.0, 1.0, num=len(samples), endpoint=False)
        x_new = np.linspace(0.0, 1.0, num=target_len, endpoint=False)
        samples = np.interp(x_new, x_old, samples).astype(np.float32)
    return samples


def _decode_to_whisper_input(
    audio_bytes: bytes,
    mime_type: str,
    sample_rate: int,
) -> np.ndarray | io.BytesIO:
    """Decode PCM16/WAV directly to 16kHz float32 numpy array (avoiding PyAV issues)."""
    normalized_mime = (mime_type or "audio/pcm").split(";")[0].strip().lower()
    if normalized_mime in {"audio/pcm", "audio/l16", "application/octet-stream"}:
        return _pcm16_to_float32_16k(audio_bytes, sample_rate=sample_rate, channels=1)

    if normalized_mime in {"audio/wav", "audio/x-wav"} or audio_bytes.startswith(b"RIFF"):
        with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
            ch = wf.getnchannels()
            sw = wf.getsampwidth()
            sr = wf.getframerate()
            frames = wf.readframes(wf.getnframes())
        if sw == 2:
            return _pcm16_to_float32_16k(frames, sample_rate=sr, channels=ch)

    return io.BytesIO(audio_bytes)


class LocalWhisperSTTProvider(STTProvider):
    """Runs Whisper locally via CTranslate2 (faster-whisper) with zero API keys."""

    name = "local_whisper"
    is_mock = False

    def __init__(
        self,
        model_size: str = "turbo",
        device: str = "auto",
        compute_type: str = "float16",
    ) -> None:
        if not is_local_whisper_available():
            raise STTConfigurationError(
                "faster-whisper o'rnatilmagan. `pip install faster-whisper` bajaring."
            )
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type

    def _run_transcribe(
        self,
        model,
        audio_input: np.ndarray | io.BytesIO,
        language: str,
        use_vad: bool,
    ) -> str:
        kwargs: dict[str, object] = {
            "language": language or "uz",
            "initial_prompt": UZBEK_WHISPER_PROMPT,
            "beam_size": 2,
            "condition_on_previous_text": False,
            "vad_filter": use_vad,
        }
        if use_vad:
            kwargs["vad_parameters"] = {
                "min_speech_duration_ms": 100,
                "min_silence_duration_ms": 200,
            }
        if isinstance(audio_input, io.BytesIO):
            audio_input.seek(0)
        segments, _ = model.transcribe(audio_input, **kwargs)
        return " ".join(seg.text.strip() for seg in segments if seg.text.strip()).strip()

    def _transcribe_sync(
        self,
        audio_bytes: bytes,
        mime_type: str,
        sample_rate: int,
        language: str,
    ) -> tuple[str, str | None]:
        normalized_mime = (mime_type or "audio/pcm").split(";")[0].strip().lower()
        is_pcm = normalized_mime in {"audio/pcm", "audio/l16"}
        rms = compute_pcm16_rms(audio_bytes) if is_pcm else 1.0
        if is_pcm:
            duration_ms = estimate_pcm16_duration_ms(len(audio_bytes), sample_rate=sample_rate)
            if duration_ms < 120 or rms < 0.0005:
                return "", "Mikrofondan sukut yoki juda qisqa audio keldi."

        audio_input = _decode_to_whisper_input(audio_bytes, mime_type, sample_rate)
        if not isinstance(audio_input, io.BytesIO):
            import numpy as np

            if len(audio_input) == 0:
                return "", "Bo'sh audio."
            rms = float(np.sqrt(np.mean(audio_input ** 2)))
            if rms < 0.0005:
                return "", "Mikrofondan sukut yoki juda qisqa audio keldi."

        model = _load_whisper_model(self._model_size, self._device, self._compute_type)
        text = self._run_transcribe(model, audio_input, language, use_vad=True)

        # Retry without VAD when non-silent short utterance ("bir") was clipped.
        if not text and rms >= 0.003:
            text = self._run_transcribe(model, audio_input, language, use_vad=False)

        return text, None

    async def transcribe(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/pcm",
        sample_rate: int = 16000,
        language: str = "uz",
    ) -> STTResult:
        """Run faster-whisper inference in a worker thread without blocking FastAPI."""
        if not audio_bytes:
            return STTResult(text="", provider=self.name, is_mock=False)
        text, note = await asyncio.to_thread(
            self._transcribe_sync, audio_bytes, mime_type, sample_rate, language
        )
        return STTResult(text=text, provider=self.name, is_mock=False, note=note)
