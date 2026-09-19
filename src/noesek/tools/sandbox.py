from pydantic import BaseModel, Field
from ..config import settings
from .sandbox_backends import get_backend

class PythonInput(BaseModel):
    code: str = Field(min_length=1, max_length=20000)
    timeout_seconds: int = Field(default=10, ge=1, le=30)

async def run_python(inp: PythonInput):
    return await get_backend().run_python(
        inp.code, image=settings.sandbox_image, timeout_seconds=inp.timeout_seconds)

class CommandInput(BaseModel):
    command: str = Field(min_length=1, max_length=4000,
                         description="Shell command run in the sandbox with the workspace mounted read-only at /workspace")
    timeout_seconds: int = Field(default=60, ge=1, le=300)

async def run_command(inp: CommandInput):
    """Verify changes with real build/test evidence: workspace mounted READ-ONLY,
    network disabled, same isolation flags as run_python."""
    from .local_read import allowed_root
    return await get_backend().run_command(
        inp.command, image=settings.sandbox_image, timeout_seconds=inp.timeout_seconds,
        workspace=str(allowed_root()))
