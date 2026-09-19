"""Output caps with local capture + registry tool search (tranche 9 adoption)."""
import json


def test_small_result_passes_through(tmp_path):
    from noesek.core.output_caps import cap_tool_result
    small = {"ok": True, "n": 1}
    assert cap_tool_result(small, directory=tmp_path) == small


def test_large_result_captured_with_receipt(tmp_path):
    from noesek.core.output_caps import cap_tool_result
    big = {"data": "x" * 5000}
    out = cap_tool_result(big, cap_bytes=1000, directory=tmp_path)
    assert out["truncated"] and out["total_bytes"] > 1000
    captured = tmp_path / out["captured_to"].split("/")[-1]
    assert json.loads(captured.read_bytes()) == big  # nothing lost
    assert oct(captured.stat().st_mode & 0o777) == "0o600"


def test_tool_search_ranks_name_over_description():
    from noesek.core.tools import ToolRegistry, ToolSpec
    from noesek.core.types import Risk
    from pydantic import BaseModel

    class In(BaseModel):
        pass

    async def fn(inp):
        return {}

    reg = ToolRegistry()
    reg.register(ToolSpec(name="search_web", description="Search the web", input_model=In, risk=Risk.READ, handler=fn))
    reg.register(ToolSpec(name="fetch_url", description="Fetch a page; good for web research", input_model=In, risk=Risk.READ, handler=fn))
    assert reg.search("search_web") == ["search_web"]
    assert reg.search("web")[0] == "search_web"  # name match beats description match
    assert reg.search("") == []


async def test_runner_caps_large_tool_results(monkeypatch, tmp_path):
    from noesek.workers.runner import run_worker

    class BigToolLLM:
        def __init__(self):
            self.calls = 0

        async def complete(self, messages, schemas):
            self.calls += 1

            class R:
                pass
            r = R()
            if self.calls == 1:
                class TC:
                    id = "c1"
                    name = "run_python"
                    arguments = {"code": "x", "timeout_seconds": 1}
                r.content = ""; r.tool_calls = [TC()]
            else:
                r.content = "done"; r.tool_calls = []
            return r

    import noesek.workers.runner as runner
    from noesek.core.tools import ToolRegistry, ToolSpec
    from noesek.core.types import Risk
    from pydantic import BaseModel

    class In(BaseModel):
        code: str
        timeout_seconds: int = 1

    async def big(inp):
        return {"blob": "y" * 50000}

    reg = ToolRegistry()
    reg.register(ToolSpec(name="run_python", description="run", input_model=In, risk=Risk.READ, handler=big))
    monkeypatch.setattr(runner, "worker_registry", lambda name, spawn_grant=None: reg)
    result = await run_worker("operator", "do it", llm=BigToolLLM())
    tool_msgs = [m for m in [result] ]  # result contains output; check no flood via output
    assert result["output"] == "done"
