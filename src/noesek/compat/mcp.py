"""MCP/ACP connection configuration with secret redaction and deny-by-default policy."""
from dataclasses import asdict, dataclass, field
from urllib.parse import urlparse

@dataclass(frozen=True)
class ExternalServer:
    name: str
    transport: str
    target: str
    enabled: bool = False
    allowed_tools: tuple[str, ...] = field(default_factory=tuple)

    def validate(self):
        if self.transport not in {"stdio","http","sse"}: raise ValueError("unsupported transport")
        if self.enabled and not self.allowed_tools: raise ValueError("enabled servers need an explicit tool allowlist")
        if self.transport in {"http","sse"} and urlparse(self.target).scheme not in {"http","https"}: raise ValueError("invalid server URL")
        if self.transport == "stdio" and not self.target.strip(): raise ValueError("empty command")
        return self

def inspect_server(server: ExternalServer) -> dict:
    server.validate(); result = asdict(server)
    if "@" in server.target and server.transport != "stdio":
        parsed=urlparse(server.target); host=parsed.hostname or ""; port=f":{parsed.port}" if parsed.port else ""
        result["target"] = f"{parsed.scheme}://***@{host}{port}{parsed.path}"
    return result
