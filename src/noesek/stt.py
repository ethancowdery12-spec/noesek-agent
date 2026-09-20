"""Speech-to-text ingest: offline transcription of inbound voice notes.

Offline first, symmetric with voice.py: ffmpeg converts the inbound audio
(WhatsApp voice notes are OGG/Opus) to 16 kHz mono PCM, vosk recognizes it
with a local small model - no API key, no per-call cost, works on the free
VM. Both are optional runtime pieces (pip extra `stt` + ffmpeg + model);
when either is missing, transcribe() raises STTError and the channel keeps
its old "describe it in text" reply.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile

MODEL_ENV = "NOESEK_VOSK_MODEL"
MAX_BYTES = 10_000_000


class STTError(RuntimeError):
    pass


def available() -> bool:
    if not shutil.which("ffmpeg"):
        return False
    try:
        import vosk  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get(MODEL_ENV))


async def _to_pcm(data: bytes, src_suffix: str) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=src_suffix, delete=False) as f:
        f.write(data)
        src = f.name
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-v", "error", "-i", src,
            "-ar", "16000", "-ac", "1", "-f", "s16le", "-",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        pcm, err = await proc.communicate()
        if proc.returncode != 0 or not pcm:
            raise STTError(f"ffmpeg could not decode the audio: {(err or b'').decode()[:200]}")
        return pcm
    finally:
        try:
            os.unlink(src)
        except OSError:
            pass


def _recognize(pcm: bytes) -> str:
    try:
        import vosk
    except ImportError:
        raise STTError("vosk is not installed (pip install noesek-agent[stt])")
    model_path = os.environ.get(MODEL_ENV)
    if not model_path:
        raise STTError(f"{MODEL_ENV} is not set (no local model)")
    vosk.SetLogLevel(-1)
    model = vosk.Model(model_path)
    rec = vosk.KaldiRecognizer(model, 16000)
    rec.AcceptWaveform(pcm)
    words = json.loads(rec.FinalResult()).get("text", "").strip()
    if not words:
        raise STTError("no speech recognized")
    return words


async def transcribe(data: bytes, content_type: str = "audio/ogg") -> str:
    """Audio bytes -> text. Raises STTError with an actionable message."""
    if not data:
        raise STTError("empty audio")
    if len(data) > MAX_BYTES:
        raise STTError("audio too long")
    if not shutil.which("ffmpeg"):
        raise STTError("ffmpeg is not installed")
    suffix = ".ogg" if "ogg" in content_type else ".wav" if "wav" in content_type else ".bin"
    pcm = await _to_pcm(data, suffix)
    return await asyncio.to_thread(_recognize, pcm)
