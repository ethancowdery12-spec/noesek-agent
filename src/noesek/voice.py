"""Voice notes: offline TTS into the files outbox.

Offline first (competitive-matrix gap 5): synthesizes with a local binary -
espeak-ng preferred, espeak or flite as fallbacks - so voice notes work with
no network and no API key. Output is a WAV in the file outbox, delivered to
the chat as a /files/{name} download path. Cloud TTS voices are a later
upgrade behind the same interface.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import tempfile

from . import filestore

MAX_CHARS = 4000

# binary -> argv builder writing a WAV to a given path
def _espeak_cmd(binary: str, text: str, out: str) -> list[str]:
    return [binary, "-w", out, "--", text]

def _flite_cmd(binary: str, text: str, out: str) -> list[str]:
    return [binary, "-t", text, "-o", out]

_BACKENDS = (
    ("espeak-ng", _espeak_cmd),
    ("espeak", _espeak_cmd),
    ("flite", _flite_cmd),
)


class VoiceError(RuntimeError):
    pass


def available_backend() -> str | None:
    for binary, _ in _BACKENDS:
        if shutil.which(binary):
            return binary
    return None


async def synthesize(text: str, name: str = "voice-note.wav") -> dict:
    """Synthesize text to a WAV in the outbox. Returns file metadata."""
    text = (text or "").strip()
    if not text:
        raise VoiceError("empty text")
    if len(text) > MAX_CHARS:
        raise VoiceError(f"text exceeds {MAX_CHARS} chars")
    if not name.endswith(".wav"):
        name += ".wav"
    binary = available_backend()
    if binary is None:
        raise VoiceError("no offline TTS binary (install espeak-ng)")
    resolved = shutil.which(binary) or binary
    builder = dict(_BACKENDS)[binary]
    fd, tmp = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        proc = await asyncio.create_subprocess_exec(
            *builder(resolved, text, tmp),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE)
        _, err = await proc.communicate()
        if proc.returncode != 0:
            raise VoiceError(f"{binary} failed: {(err or b'').decode()[:200]}")
        with open(tmp, "rb") as f:
            data = f.read()
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    if not data:
        raise VoiceError(f"{binary} produced no audio")
    return filestore.write_file(name, data)
