"""Tests for parallel-variant generation (roadmap item 53)."""
import pytest

from noesek.core.types import LLMReply
from noesek.tools.variants import GenerateVariantsInput, generate_variants_handler, LENSES


class FakeLLM:
    def __init__(self, judge_reply="PICK 2 - sharpest of the set", fail_judge=False, fail_variants=0):
        self.calls = []
        self.judge_reply = judge_reply
        self.fail_judge = fail_judge
        self.fail_variants = fail_variants

    async def complete(self, messages, tools):
        self.calls.append(messages[0]["content"])
        if "Pick the single best candidate" in messages[0]["content"]:
            if self.fail_judge:
                raise RuntimeError("judge down")
            return LLMReply(content=self.judge_reply)
        if self.fail_variants > 0:
            self.fail_variants -= 1
            raise RuntimeError("variant failed")
        return LLMReply(content=f"candidate-{len(self.calls)}")


def resolver_for(llm):
    async def r():
        return llm
    return r


@pytest.mark.asyncio
async def test_generates_n_variants_in_parallel_with_lenses():
    llm = FakeLLM()
    h = generate_variants_handler(resolver_for(llm))
    out = await h(GenerateVariantsInput(task="tagline for a dog app", n=3))
    assert len(out["variants"]) == 3
    assert [v["lens"] for v in out["variants"]] == LENSES[:3]
    assert out["pick"] == 2
    assert "sharpest" in out["reason"]
    # 3 variant calls + 1 judge call
    assert len(llm.calls) == 4


@pytest.mark.asyncio
async def test_judge_failure_falls_back_to_first_variant():
    llm = FakeLLM(fail_judge=True)
    h = generate_variants_handler(resolver_for(llm))
    out = await h(GenerateVariantsInput(task="subject line", n=2))
    assert out["pick"] == 1
    assert "judge unavailable" in out["reason"]


@pytest.mark.asyncio
async def test_partial_variant_failure_still_returns_survivors():
    llm = FakeLLM(fail_variants=1)
    h = generate_variants_handler(resolver_for(llm))
    out = await h(GenerateVariantsInput(task="name ideas", n=3))
    assert len(out["variants"]) == 2


@pytest.mark.asyncio
async def test_all_variants_failed_errors():
    llm = FakeLLM(fail_variants=5)
    h = generate_variants_handler(resolver_for(llm))
    out = await h(GenerateVariantsInput(task="bio", n=2))
    assert "error" in out


@pytest.mark.asyncio
async def test_bad_judge_pick_ignored():
    llm = FakeLLM(judge_reply="PICK 9 - does not exist")
    h = generate_variants_handler(resolver_for(llm))
    out = await h(GenerateVariantsInput(task="tweet draft", n=2))
    assert out["pick"] == 1


def test_n_bounds_enforced():
    with pytest.raises(Exception):
        GenerateVariantsInput(task="x", n=6)
    with pytest.raises(Exception):
        GenerateVariantsInput(task="x", n=1)
