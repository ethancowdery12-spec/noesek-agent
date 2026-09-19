from noesek.testing import ScriptedLLM, text_reply, tool_reply
from noesek.workers import runner
from noesek.workers.runner import run_worker, worker_registry

def test_worker_scopes_are_read_only():
    r = worker_registry("researcher")
    assert set(r.names()) == {"search_web", "fetch_url"}
    r2 = worker_registry("coder")
    assert "run_python" in r2.names() and "search_web" not in r2.names()

def test_unknown_worker_errors():
    import asyncio
    out = asyncio.run(run_worker("ghost", "do x", llm=ScriptedLLM([])))
    assert "error" in out

async def test_worker_direct_answer():
    out = await run_worker("researcher", "summarize", llm=ScriptedLLM([text_reply("done")]))
    assert out["output"] == "done" and out["steps"] == 1

async def test_worker_tool_loop_collects_citations(monkeypatch):
    from pydantic import BaseModel
    from noesek.core.tools import ToolSpec
    from noesek.core.types import Risk
    class Q(BaseModel): q: str = "x"
    async def search(inp): return {"results": [{"url": "https://example.org/r"}]}
    def specs():
        return {"search_web": ToolSpec("search_web", "d", Q, Risk.READ, search),
                "fetch_url": ToolSpec("fetch_url", "d", Q, Risk.READ, search),
                "run_python": ToolSpec("run_python", "d", Q, Risk.READ, search)}
    monkeypatch.setattr(runner, "_all_tool_specs", specs)
    llm = ScriptedLLM([tool_reply("search_web", {"q": "vaccines"}), text_reply("synthesis")])
    out = await run_worker("researcher", "research", llm=llm)
    assert out["output"] == "synthesis"
    assert out["citations"] == ["https://example.org/r"]
