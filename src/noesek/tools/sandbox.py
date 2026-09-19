from pydantic import BaseModel, Field
from ..config import settings
from .sandbox_backends import get_backend

class PythonInput(BaseModel):
    code: str = Field(min_length=1, max_length=20000)
    timeout_seconds: int = Field(default=10, ge=1, le=30)

async def run_python(inp: PythonInput):
    return await get_backend().run_python(
        inp.code, image=settings.sandbox_image, timeout_seconds=inp.timeout_seconds)
