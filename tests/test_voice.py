"""Hermetic voice tests: backend detection, stubbed synthesis, endpoint, tool."""

import pytest
from fastapi.testclient import TestClient

from noesek import filestore, voice
from noesek.computer import server


@pytest.fixture()
def fdir(tmp_path, monkeypatch):
    monkeypatch.setenv("NOESEK_FILES_DIR", str(tmp_path / "files"))
    yield tmp_path / "files"


def test_backend_detection(monkeypatch):
    monkeypatch.setattr(voice.shutil, "which", lambda b: "/usr/bin/espeak-ng" if b == "espeak-ng" else None)
    assert voice.available_backend() == "espeak-ng"
    monkeypatch.setattr(voice.shutil, "which", lambda b: None)
    assert voice.available_backend() is None


@pytest.mark.asyncio
async def test_missing_backend_errors(fdir, monkeypatch):
    monkeypatch.setattr(voice.shutil, "which", lambda b: None)
    with pytest.raises(voice.VoiceError, match="no offline TTS"):
        await voice.synthesize("hello")


@pytest.mark.asyncio
async def test_empty_and_long_text_rejected(fdir):
    with pytest.raises(voice.VoiceError):
        await voice.synthesize("   ")
    with pytest.raises(voice.VoiceError):
        await voice.synthesize("x" * (voice.MAX_CHARS + 1))


@pytest.mark.asyncio
async def test_synthesize_with_stubbed_binary(fdir, monkeypatch, tmp_path):
    fake = tmp_path / "espeak-ng"
    fake.write_text('#!/bin/sh\nwhile [ $# -gt 0 ]; do\n  if [ "$1" = "-w" ]; then shift; printf "RIFFfakewav" > "$1"; fi\n  shift || break\ndone\n')
    fake.chmod(0o755)
    monkeypatch.setattr(voice.shutil, "which", lambda b: str(fake) if b == "espeak-ng" else None)
    meta = await voice.synthesize("good morning ethan", "morning.wav")
    assert meta["name"] == "morning.wav"
    assert filestore.read_file("morning.wav") == b"RIFFfakewav"


@pytest.mark.asyncio
async def test_name_gets_wav_suffix(fdir, monkeypatch, tmp_path):
    fake = tmp_path / "flite"
    fake.write_text('#!/bin/sh\nprintf "RIFFx" > "$4"\n')
    fake.chmod(0o755)
    monkeypatch.setattr(voice.shutil, "which", lambda b: str(fake) if b == "flite" else None)
    meta = await voice.synthesize("hi", "note")
    assert meta["name"] == "note.wav"


def test_endpoint_and_tool(fdir, monkeypatch, tmp_path):
    fake = tmp_path / "espeak-ng"
    fake.write_text('#!/bin/sh\nwhile [ $# -gt 0 ]; do\n  if [ "$1" = "-w" ]; then shift; printf "RIFFep" > "$1"; fi\n  shift || break\ndone\n')
    fake.chmod(0o755)
    monkeypatch.setattr(voice.shutil, "which", lambda b: str(fake) if b == "espeak-ng" else None)

    client = TestClient(server.app)
    out = client.post("/voice/say", json={"text": "your build finished"})
    assert out.status_code == 200
    assert out.json()["download"] == "/files/voice-note.wav"
    assert client.get("/files/voice-note.wav").content == b"RIFFep"
    assert client.post("/voice/say", json={"text": ""}).status_code == 400

    import asyncio
    from noesek.core.controller import Controller
    from noesek.core.types import Risk
    from noesek.tools.voice_tools import SpeakInput
    registry = Controller(llm=object()).registry(1)
    spec = registry.get("speak")
    assert spec is not None and spec.risk is Risk.WRITE
    res = asyncio.run(spec.handler(SpeakInput(text="hello", name="t.wav")))
    assert res["created"] is True
