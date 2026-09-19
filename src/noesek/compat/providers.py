"""Provider catalog and auth metadata, inspired by the upstream provider surface.

No provider SDK is imported. OpenAI-compatible endpoints use Noesek's HTTP adapter;
other protocols are described honestly as unavailable until their adapter is installed.
"""
from dataclasses import asdict, dataclass
from typing import Iterable

@dataclass(frozen=True)
class Provider:
    name: str
    protocol: str
    env_keys: tuple[str, ...]
    base_url: str | None = None
    oauth: bool = False
    available: bool = True

_BUILTINS = {
    p.name: p for p in (
        Provider("openai", "openai-chat", ("NOESEK_LLM_API_KEY",), "https://api.openai.com/v1"),
        Provider("openrouter", "openai-chat", ("NOESEK_LLM_API_KEY",), "https://openrouter.ai/api/v1"),
        Provider("ollama", "openai-chat", (), "http://localhost:11434/v1"),
        Provider("lmstudio", "openai-chat", (), "http://localhost:1234/v1"),
        Provider("vllm", "openai-chat", (), "http://localhost:8000/v1"),
        Provider("azure-openai", "openai-chat", ("NOESEK_LLM_API_KEY",), oauth=True),
        Provider("anthropic", "anthropic-messages", ("ANTHROPIC_API_KEY",), "https://api.anthropic.com/v1", oauth=True),
        Provider("google", "gemini", ("GOOGLE_API_KEY",), "https://generativelanguage.googleapis.com/v1beta", oauth=True),
        Provider("bedrock", "aws-converse", ("AWS_PROFILE",), available=False),
    )
}

def list_providers() -> list[dict]: return [asdict(_BUILTINS[k]) for k in sorted(_BUILTINS)]
def get_provider(name: str) -> Provider: return _BUILTINS[name]
def resolve_provider(base_url: str) -> Provider | None:
    value = base_url.rstrip("/")
    return next((p for p in _BUILTINS.values() if p.base_url and p.base_url.rstrip("/") == value), None)
