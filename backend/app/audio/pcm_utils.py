"""PCM16 audio inspection and WAV encapsulation utilities."""

import io
import math
import struct
import wave


def pcm16_to_wav(
    pcm_bytes: bytes,
    sample_rate: int = 16000,
    channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    """Wrap raw signed 16-bit little-endian PCM bytes in a standard RIFF/WAV header."""
    if not pcm_bytes:
        raise ValueError("Audio buffer is empty.")
    aligned_len = len(pcm_bytes) - (len(pcm_bytes) % (channels * sample_width))
    if aligned_len <= 0:
        raise ValueError("PCM buffer is too short to form a valid audio frame.")

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes[:aligned_len])
    return buf.getvalue()


def compute_pcm16_rms(pcm_bytes: bytes) -> float:
    """Compute normalized RMS amplitude [0.0, 1.0] for raw PCM16 audio."""
    sample_count = len(pcm_bytes) // 2
    if sample_count == 0:
        return 0.0
    samples = struct.unpack(f"<{sample_count}h", pcm_bytes[: sample_count * 2])
    sum_sq = sum(s * s for s in samples)
    return math.sqrt(sum_sq / sample_count) / 32768.0


def ensure_audio_filename_and_bytes(
    audio_bytes: bytes,
    mime_type: str = "audio/pcm",
    sample_rate: int = 16000,
) -> tuple[str, bytes, str]:
    """Return (filename, upload_bytes, content_type) suitable for STT HTTP APIs."""
    normalized_mime = (mime_type or "audio/pcm").split(";")[0].strip().lower()

    if normalized_mime in {"audio/pcm", "audio/l16", "application/octet-stream"}:
        wav_bytes = pcm16_to_wav(audio_bytes, sample_rate=sample_rate)
        return ("audio.wav", wav_bytes, "audio/wav")

    ext_map = {
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/webm": "webm",
        "audio/ogg": "ogg",
        "audio/opus": "opus",
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/mp4": "m4a",
        "audio/m4a": "m4a",
    }
    ext = ext_map.get(normalized_mime, "wav")
    if ext == "wav" and not audio_bytes.startswith(b"RIFF"):
        audio_bytes = pcm16_to_wav(audio_bytes, sample_rate=sample_rate)
    return (f"audio.{ext}", audio_bytes, normalized_mime)


def estimate_pcm16_duration_ms(
    byte_length: int,
    sample_rate: int = 16000,
    channels: int = 1,
    sample_width: int = 2,
) -> float:
    """Estimate duration in milliseconds of raw PCM audio bytes."""
    bytes_per_second = sample_rate * channels * sample_width
    if bytes_per_second <= 0:
        return 0.0
    return (byte_length / bytes_per_second) * 1000.0
