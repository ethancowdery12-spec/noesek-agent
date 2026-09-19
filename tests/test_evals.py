"""Promptfoo process-boundary integration: config shape, locality guard, runner."""
import json

import pytest

from noesek.tools.evals import (EvalRunnerError, build_promptfoo_config,
                                run_eval, write_config)


def test_config_targets_local_http_provider(tmp_path):
    cfg = build_promptfoo_config(
        endpoint="http://127.0.0.1:8000/api/eval",
        prompts=["Answer: {{question}}"],
        cases=[{"vars": {"question": "2+2"}, "assert": [{"type": "contains", "value": "4"}]}])
    path = write_config(cfg, tmp_path)
    import yaml
    loaded = yaml.safe_load(path.read_text())
    assert loaded["providers"][0]["config"]["url"] == "http://127.0.0.1:8000/api/eval"
    assert loaded["tests"][0]["vars"]["question"] == "2+2"


def test_external_endpoint_refused():
    with pytest.raises(EvalRunnerError):
        build_promptfoo_config(endpoint="https://api.openai.com/v1/chat", prompts=[], cases=[])


async def test_runner_runs_promptfoo_subprocess(tmp_path, monkeypatch):
    # Fake promptfoo executable: writes results.json honoring -o.
    fake = tmp_path / "promptfoo"
    fake.write_text(
        "#!/bin/sh\n"
        "while [ $# -gt 0 ]; do\n"
        "  if [ \"$1\" = \"-o\" ]; then shift; echo '{\"results\":{\"results\":[]}}' > \"$1\"; fi\n"
        "  shift\n"
        "done\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")
    import shutil
    monkeypatch.setattr(shutil, "which", lambda n: str(fake) if n == "promptfoo" else None)
    cfg = build_promptfoo_config(endpoint="http://127.0.0.1:9/x", prompts=["p"], cases=[])
    out = await run_eval(cfg, timeout_seconds=30)
    assert out == {"results": {"results": []}}


async def test_runner_missing_promptfoo_reports_cleanly(monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which", lambda n: None)
    cfg = build_promptfoo_config(endpoint="http://127.0.0.1:9/x", prompts=["p"], cases=[])
    out = await run_eval(cfg)
    assert "promptfoo is not installed" in out["error"]


def test_deepeval_cases_shape_and_validation():
    from noesek.tools.evals import build_deepeval_cases
    cases = build_deepeval_cases([
        {"input": "2+2?", "expected_output": "4"},
        {"input": "capital of France?", "context": ["France is a country in Europe."]},
    ])
    assert cases[0] == {"input": "2+2?", "expected_output": "4"}
    assert cases[1]["context"] == ["France is a country in Europe."]
    with pytest.raises(EvalRunnerError):
        build_deepeval_cases([{"input": ""}])
