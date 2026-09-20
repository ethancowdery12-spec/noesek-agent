"""File creation as a chat-controller tool: the agent authors, the user downloads."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .. import filestore


class CreateFileInput(BaseModel):
    name: str = Field(min_length=1, max_length=128,
                      description="File name with extension, e.g. report.md")
    content: str = Field(min_length=1, max_length=filestore.MAX_FILE_BYTES,
                         description="Full text content of the file")


def create_file_handler(conversation_id: int):
    async def h(inp: CreateFileInput):
        try:
            meta = filestore.write_file(inp.name, inp.content)
        except filestore.FileStoreError as exc:
            return {"error": str(exc)}
        return {"created": True, "download": f"/files/{meta['name']}", **meta}
    return h
