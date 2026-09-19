import httpx
import pytest
from noesek.core import llm as llm_mod
from noesek import cli

class FakeClient:
    response = None
    error = None
    def __init__(self, **kwargs): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def post(self, *args, **kwargs):
        if self.error: raise self.error
        return self.response

def response(code, data=None):
    return httpx.Response(code, json=data or {"error":{"message":"secret vendor detail"}},
                          request=httpx.Request("POST", "https://x"))

@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(llm_mod.settings, "llm_base_url", "https://api.deepseek.com/v1")
    monkeypatch.setattr(llm_mod.settings, "llm_model", "deepseek-flash")
    monkeypatch.setattr(llm_mod.settings, "llm_api_key", "secret")
    monkeypatch.setattr(llm_mod.settings, "llm_provider", "openai-compatible")
    monkeypatch.setattr(llm_mod.settings, "llm_max_retries", 0)
    monkeypatch.setattr(llm_mod.httpx, "AsyncClient", FakeClient)

@pytest.mark.parametrize("status,expected", [(401,"API key"),(404,"model name"),(429,"rate-limited"),(503,"server error")])
async def test_http_errors_are_actionable(status, expected):
    FakeClient.error = None; FakeClient.response = response(status)
    with pytest.raises(llm_mod.LLMError) as caught:
        await llm_mod.OpenAICompatibleLLM().complete([{"role":"user","content":"hi"}], [])
    text = str(caught.value)
    assert "provider=deepseek" in text and "base_url=https://api.deepseek.com/v1" in text
    assert "model=deepseek-flash" in text and f"status={status}" in text and expected in text
    assert "secret vendor detail" not in text

@pytest.mark.parametrize("error,kind", [(httpx.ConnectError("down"),"connection error"),
                                          (httpx.ReadTimeout("slow"),"timeout")])
async def test_transport_errors_are_actionable(error, kind):
    FakeClient.response = None; FakeClient.error = error
    with pytest.raises(llm_mod.LLMError, match=kind):
        await llm_mod.OpenAICompatibleLLM().complete([], [])

def test_main_prints_clean_provider_error(monkeypatch, capsys):
    async def fail(_args):
        raise llm_mod.LLMError(provider="deepseek", base_url="https://api.deepseek.com/v1",
                               model="deepseek-flash", status=401, kind="HTTP error")
    monkeypatch.setattr(cli, "_chat", fail)
    assert cli.main(["chat", "--oneshot", "-q", "hello"]) == 1
    err = capsys.readouterr().err
    assert "LLM provider error" in err and "Traceback" not in err

async def test_worker_returns_safe_provider_failure():
    from noesek.workers.runner import run_worker
    class Broken:
        async def complete(self, messages, tools):
            raise llm_mod.LLMError(provider="deepseek", base_url="https://api.deepseek.com/v1",
                                   model="deepseek-flash", status=429, kind="HTTP error")
    result = await run_worker("researcher", "test", llm=Broken())
    assert result["incomplete"] and "provider=deepseek" in result["output"]
