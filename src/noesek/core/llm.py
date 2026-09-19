import asyncio, json
import httpx
from .types import LLMReply, ToolCall
from ..config import settings

def provider_name(base_url: str, configured: str | None = None) -> str:
    """Return a useful provider label without exposing credentials."""
    if configured and configured.strip().lower() not in {"openai-compatible", "openai"}:
        return configured.strip().lower()
    host = httpx.URL(base_url).host or "unknown"
    known = {"api.openai.com": "openai", "api.deepseek.com": "deepseek",
             "openrouter.ai": "openrouter", "generativelanguage.googleapis.com": "gemini",
             "api.anthropic.com": "anthropic"}
    return known.get(host, f"openai-compatible ({host})")

def normalize_usage(data: dict) -> dict:
    """Normalize a provider usage object to {"input_tokens", "output_tokens"}."""
    usage = (data or {}).get("usage") or {}
    return {"input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens")}


class LLMError(RuntimeError):
    def __init__(self, *, provider: str, base_url: str, model: str, status: int | None = None,
                 kind: str = "request failed"):
        self.provider, self.base_url, self.model = provider, base_url.rstrip("/"), model
        self.status, self.kind = status, kind
        status_text = str(status) if status is not None else "unavailable"
        if status in {401, 403}:
            action = "Check that the API key belongs to this provider and that the base URL is correct."
        elif status == 404:
            action = "Check the base URL and model name against the provider's current model list."
        elif status == 429:
            action = "The provider rate-limited the request. Wait, check quota/billing, then retry."
        elif status is not None and status >= 500:
            action = "The provider reported a server error. Retry shortly or use another configured provider."
        elif kind == "timeout":
            action = "The provider timed out. Check the endpoint and network, then retry."
        elif kind == "connection error":
            action = "Could not connect. Check the base URL, internet connection, proxy, and firewall."
        else:
            action = "Check the provider endpoint, model, and response format."
        super().__init__(f"LLM provider error: provider={provider}; base_url={self.base_url}; "
                         f"model={model}; status={status_text}; error={kind}. {action}")

def _llm_error(base_url: str, model: str, status: int | None = None, kind: str = "request failed",
               provider: str | None = None) -> LLMError:
    return LLMError(provider=provider or provider_name(base_url, settings.llm_provider),
                    base_url=base_url, model=model, status=status, kind=kind)

class OpenAICompatibleLLM:
    """OpenAI-compatible chat-completions adapter with bounded retries and clean errors."""
    async def complete(self, messages: list[dict], tools: list[dict]) -> LLMReply:
        if not settings.llm_api_key or not settings.llm_model:
            return LLMReply(content="No LLM is configured. Set NOESEK_LLM_API_KEY and NOESEK_LLM_MODEL, then try again.")
        base_url, model = settings.llm_base_url.rstrip("/"), settings.llm_model
        body = {"model": model, "messages": messages, "tools": tools or None,
                "tool_choice": "auto" if tools else None}
        body = {k: v for k, v in body.items() if v is not None}
        headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
        url, delay, last = base_url + "/chat/completions", 1.0, None
        for attempt in range(settings.llm_max_retries + 1):
            try:
                from .llm_pool import get_pool
                async with get_pool():
                    async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
                        r = await client.post(url, json=body, headers=headers)
                if r.status_code >= 400:
                    last = _llm_error(base_url, model, r.status_code, "HTTP error")
                    if r.status_code not in {429} and r.status_code < 500:
                        raise last
                else:
                    try:
                        data = r.json()
                        choice = data["choices"][0]
                        msg = choice["message"]
                        calls = [ToolCall(id=c["id"], name=c["function"]["name"],
                                          arguments=json.loads(c["function"].get("arguments") or "{}"))
                                 for c in (msg.get("tool_calls") or [])]
                        return LLMReply(content=msg.get("content"), tool_calls=calls,
                                        usage=normalize_usage(data), finish_reason=choice.get("finish_reason"))
                    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
                        raise _llm_error(base_url, model, r.status_code, "invalid response") from None
            except LLMError:
                raise
            except httpx.TimeoutException:
                last = _llm_error(base_url, model, kind="timeout")
            except httpx.TransportError:
                last = _llm_error(base_url, model, kind="connection error")
            if attempt < settings.llm_max_retries:
                await asyncio.sleep(delay); delay = min(delay * 2, 8.0)
        raise last or _llm_error(base_url, model)


def configured_llm():
    """Build the selected native wire adapter without probing or sending credentials."""
    name = settings.llm_provider.strip().lower()
    if name in {"openai", "openai-compatible"}: return OpenAICompatibleLLM()
    from .providers import AnthropicAdapter, GeminiAdapter
    if name == "anthropic": return AnthropicAdapter(settings.llm_api_key, settings.llm_model, settings.llm_base_url, settings.llm_timeout_seconds)
    if name in {"google", "gemini"}: return GeminiAdapter(settings.llm_api_key, settings.llm_model, settings.llm_base_url, settings.llm_timeout_seconds)
    raise ValueError(f"unsupported LLM provider: {name}")


class FallbackLLM:
    """Ordered OpenAI-compatible fallback, only for transport, rate, and server failures."""
    def __init__(self, fallbacks: list[dict]):
        if not fallbacks: raise ValueError("fallbacks must be a non-empty list")
        self._configs = fallbacks

    @staticmethod
    def from_settings() -> "FallbackLLM | None":
        raw = settings.llm_fallbacks.strip()
        if not raw: return None
        chain = [{"base_url": settings.llm_base_url, "model": settings.llm_model,
                  "api_key": settings.llm_api_key}]
        chain.extend(json.loads(raw))
        return FallbackLLM(chain)

    async def complete(self, messages: list[dict], tools: list[dict]) -> LLMReply:
        last: LLMError | None = None
        for cfg in self._configs:
            base_url, model = cfg["base_url"].rstrip("/"), cfg["model"]
            body = {"model": model, "messages": messages, "tools": tools or None,
                    "tool_choice": "auto" if tools else None}
            body = {k: v for k, v in body.items() if v is not None}
            for attempt in range(settings.llm_max_retries + 1):
                try:
                    async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
                        r = await client.post(base_url + "/chat/completions", json=body,
                                              headers={"Authorization": f"Bearer {cfg['api_key']}"})
                    if r.status_code >= 400:
                        raise _llm_error(base_url, model, r.status_code, "HTTP error")
                    data = r.json()
                    choice = data["choices"][0]
                    msg = choice["message"]
                    calls = [ToolCall(id=c.get("id", ""), name=c["function"]["name"],
                                      arguments=json.loads(c["function"].get("arguments") or "{}"))
                             for c in (msg.get("tool_calls") or [])]
                    return LLMReply(content=msg.get("content") or "", tool_calls=calls,
                                    usage=normalize_usage(data), finish_reason=choice.get("finish_reason"))
                except httpx.TimeoutException:
                    last = _llm_error(base_url, model, kind="timeout")
                except httpx.TransportError:
                    last = _llm_error(base_url, model, kind="connection error")
                except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
                    last = _llm_error(base_url, model, kind="invalid response")
                except LLMError as e:
                    last = e
                    if e.status not in {429} and not (e.status is not None and e.status >= 500):
                        raise
                if attempt < settings.llm_max_retries:
                    await asyncio.sleep(min(2 ** attempt, 8))
            # move to the next configured provider
        raise last or _llm_error(settings.llm_base_url, settings.llm_model)

