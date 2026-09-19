from dataclasses import asdict, dataclass
@dataclass(frozen=True)
class Usage:
    input_tokens: int=0
    output_tokens: int=0
    cached_tokens: int=0
    @property
    def total_tokens(self): return self.input_tokens+self.output_tokens
    def to_dict(self): return {**asdict(self),"total_tokens":self.total_tokens}
def normalize_usage(provider: str,data: dict) -> Usage:
    p=provider.lower()
    if p in {"openai","openai-compatible"}: return Usage(int(data.get("prompt_tokens",0)),int(data.get("completion_tokens",0)),int((data.get("prompt_tokens_details") or {}).get("cached_tokens",0)))
    if p=="anthropic": return Usage(int(data.get("input_tokens",0)),int(data.get("output_tokens",0)),int(data.get("cache_read_input_tokens",0)))
    if p in {"gemini","google"}: return Usage(int(data.get("promptTokenCount",0)),int(data.get("candidatesTokenCount",0)),int(data.get("cachedContentTokenCount",0)))
    if p=="bedrock": return Usage(int(data.get("inputTokens",0)),int(data.get("outputTokens",0)))
    raise ValueError(f"unknown provider: {provider}")
