"""Unit tests for PCM16 -> WAV utilities and RMS measurement."""

import io
import math
import struct
import wave

import pytest

from app.audio.pcm_utils import (
    compute_pcm16_rms,
    ensure_audio_filename_and_bytes,
    estimate_pcm16_duration_ms,
    pcm16_to_wav,
)


def make_sine_pcm16(freq_hz: float = 440.0, duration_s: float = 0.25, rate: int = 16000) -> bytes:
    total = int(duration_s * rate)
    samples = [
        int(12000 * math.sin(2.0 * math.pi * freq_hz * i / rate))
        for i in range(total)
    ]
    return struct.pack(f"<{total}h", *samples)


def test_pcm16_to_wav_valid_header():
    pcm = make_sine_pcm16()
    wav_bytes = pcm16_to_wav(pcm, sample_rate=16000)
    assert wav_bytes.startswith(b"RIFF")

    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 16000
        assert wf.getnframes() == 4000


def test_compute_rms_and_duration():
    silence = b"\x00\x00" * 1600
    tone = make_sine_pcm16(duration_s=0.5)
    assert compute_pcm16_rms(silence) == 0.0
    assert compute_pcm16_rms(tone) > 0.1
    assert estimate_pcm16_duration_ms(len(tone), sample_rate=16000) == pytest.approx(500.0)


def test_ensure_audio_filename_and_empty_error():
    pcm = make_sine_pcm16(duration_s=0.1)
    fname, payload, ctype = ensure_audio_filename_and_bytes(pcm, "audio/pcm", 16000)
    assert fname == "audio.wav"
    assert ctype == "audio/wav"
    assert payload.startswith(b"RIFF")

    with pytest.raises(ValueError):
        pcm16_to_wav(b"")
