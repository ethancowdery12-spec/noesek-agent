import sys
from datetime import datetime, timezone
from pathlib import Path
import pytest
from noesek.compat.providers import get_provider, list_providers, resolve_provider
from noesek.compat.plugins import discover_plugins
from noesek.compat.skills import discover_skills
from noesek.compat.mcp import ExternalServer, inspect_server
from noesek.compat.terminal import TerminalPolicyError, run_command, validate_command
from noesek.compat.schedules import IntervalSchedule

HERE=Path(__file__).parent

def test_provider_catalog_is_stable_and_honest():
    rows=list_providers(); assert rows == sorted(rows,key=lambda x:x["name"])
    assert get_provider("anthropic").available is True
    assert resolve_provider("https://api.openai.com/v1/").name == "openai"

def test_plugins_are_manifest_only_and_deny_by_default():
    rows=discover_plugins([HERE/"fixtures/plugins"])
    assert rows[0]["name"] == "demo" and rows[0]["enabled"] is False
    assert rows[0]["capabilities"] == ["tools"]

def test_skills_are_discovered_as_inert_markdown():
    rows=discover_skills([HERE/"fixtures/skills"])
    assert rows[0]["name"] == "demo" and rows[0]["description"] == "Demo skill"

def test_external_server_requires_explicit_allowlist():
    with pytest.raises(ValueError): ExternalServer("x","http","https://x.test",enabled=True).validate()
    row=inspect_server(ExternalServer("x","http","https://u:p@x.test/mcp",True,("read",)))
    assert row["target"] == "https://***@x.test/mcp"

def test_terminal_policy_denies_network_escalation(tmp_path):
    with pytest.raises(TerminalPolicyError): validate_command(["ssh","host"],tmp_path)

async def test_terminal_runner_is_bounded(tmp_path):
    result=await run_command([sys.executable,"-c","print('ok')"],tmp_path)
    assert result["exit_code"] == 0 and result["stdout"] == "ok\n"

async def test_terminal_timeout(tmp_path):
    result=await run_command([sys.executable,"-c","import time; time.sleep(1)"],tmp_path,timeout=.01)
    assert result["timed_out"] is True

def test_interval_schedule_bounds_and_next():
    s=IntervalSchedule(60); now=datetime(2026,1,1,tzinfo=timezone.utc)
    assert (s.next_after(now)-now).total_seconds() == 60
    with pytest.raises(ValueError): IntervalSchedule(1)
