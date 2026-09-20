"""Voice notes as a chat-controller tool: offline TTS, delivered as a download."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .. import filestore, voice


class SpeakInput(BaseModel):
    text: str = Field(min_length=1, max_length=voice.MAX_CHARS,
                      description="What the voice note should say")
    name: str = Field(default="voice-note.wav", max_length=128)


def speak_handler(conversation_id: int):
    async def h(inp: SpeakInput):
        try:
            meta = await voice.synthesize(inp.text, inp.name)
        except (voice.VoiceError, filestore.FileStoreError) as exc:
            return {"error": str(exc)}
        return {"created": True, "download": f"/files/{meta['name']}", **meta}
    return h
