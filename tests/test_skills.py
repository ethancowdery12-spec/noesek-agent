"""Tests for skill_library (skills batch 3: Voyager + agent-workflow-memory
patterns, own-words)."""
from sqlalchemy import select

from noesek.core.context import assemble
from noesek.db import Conversation, Memory, Session
from noesek.tools.skills import SkillInput, skill_library


async def _conv():
    async with Session() as s:
        c = Conversation(channel="cli", external_user_id="u1"); s.add(c); await s.commit(); return c.id


def _save_input(name="csv totals", **kw):
    return SkillInput(action="save", name=name,
                      when_to_use=kw.get("when", "user asks to total or sum columns in a CSV file"),
                      steps=kw.get("steps", "1. duckdb_query with SELECT sum(amount) 2. report the total"),
                      verification=kw.get("verification", "ran it on sales.csv, total matched the spreadsheet"))


async def test_save_requires_verification(db):
    cid = await _conv()
    r = await skill_library(_save_input(verification=""), cid)
    assert r["ok"] is False and "verification" in r["error"]
    r = await skill_library(_save_input(steps=""), cid)
    assert r["ok"] is False


async def test_save_stores_skill_memory(db):
    cid = await _conv()
    r = await skill_library(_save_input(), cid)
    assert r["ok"] and r["skill_id"]
    async with Session() as s:
        m = await s.get(Memory, r["skill_id"])
        assert m.kind == "skill" and m.source == "self-authored" and m.active
        assert "csv totals" in m.content and "Verified by" in m.content


async def test_search_and_get(db):
    cid = await _conv()
    await skill_library(_save_input(), cid)
    r2 = await skill_library(SkillInput(
        action="save", name="paper roundup",
        when_to_use="user asks for recent papers on a topic",
        steps="1. literature_search across sources 2. dedupe 3. summarize top 5",
        verification="returned 5 deduped papers with links"), cid)
    res = await skill_library(SkillInput(action="search", query="sum a csv column"), cid)
    assert res["ok"] and res["results"][0]["name"] == "csv totals"
    got = await skill_library(SkillInput(action="get", skill_id=r2["skill_id"]), cid)
    assert got["ok"] and "literature_search" in got["content"]


async def test_retire_removes_from_search(db):
    cid = await _conv()
    r = await skill_library(_save_input(), cid)
    out = await skill_library(SkillInput(action="retire", skill_id=r["skill_id"]), cid)
    assert out["ok"]
    res = await skill_library(SkillInput(action="search", query="csv total"), cid)
    assert all(x["skill_id"] != r["skill_id"] for x in res["results"])
    gone = await skill_library(SkillInput(action="get", skill_id=r["skill_id"]), cid)
    assert gone["ok"] is False


async def test_skill_surfaces_in_assembled_context(db):
    cid = await _conv()
    await skill_library(_save_input(), cid)
    async with Session() as s:
        out = await assemble(s, cid, query="can you total the csv columns for me")
    system = out[0]["content"]
    assert "csv totals" in system


async def test_unknown_action(db):
    cid = await _conv()
    r = await skill_library(SkillInput(action="explode"), cid)
    assert r["ok"] is False and "unknown action" in r["error"]
