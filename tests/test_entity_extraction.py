"""Entity-extraction contract tests (roadmap item 66).

The acceptance gate itself lives in evals/entity_extraction.py (deterministic
vs LLM F1 on evals/entity_fixtures.py); these tests pin the deterministic
baseline floor, the LLM extractor's parse/fallback contract with a fake LLM,
and the flag-off default so the live path is unchanged until the gate passes.
"""
import pytest

from evals.entity_extraction import evaluate
from evals.entity_fixtures import CASES
from noesek.config import settings
from noesek.core.memory_graph import extract_entities, llm_extract_entities


def test_deterministic_baseline_floor():
    """The deterministic extractor's measured fixture F1 must not regress
    below its item-66 baseline (54.6% at landing; floor 50%)."""
    report = evaluate(extract_entities)
    assert report["f1"] >= 0.50, f"deterministic F1 {report['f1']:.1%} below 50% floor"
    assert report["cases"] == len(CASES)


class FakeLLM:
    def __init__(self, content):
        self._content = content
        self.calls = 0

    async def complete(self, messages, schemas):
        self.calls += 1
        class Reply:
            content = self._content
        return Reply()


@pytest.mark.asyncio
async def test_llm_extractor_parses_json_array():
    llm = FakeLLM('["Sarah", " Espresso ", "bluecup cafe"]')
    ents = await llm_extract_entities("Sarah likes espresso from the Bluecup cafe.", llm=llm)
    assert ents == ["sarah", "espresso", "bluecup cafe"]
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_llm_extractor_strips_code_fences_and_caps():
    llm = FakeLLM('```json\n["a", "b", "c", "d", "e", "f", "g", "h", "i"]\n```')
    ents = await llm_extract_entities("anything", cap=8, llm=llm)
    assert ents == ["a", "b", "c", "d", "e", "f", "g", "h"]


@pytest.mark.asyncio
async def test_llm_extractor_falls_back_on_garbage():
    llm = FakeLLM("I cannot help with that.")
    ents = await llm_extract_entities("Ethan's sister is Sarah.", llm=llm)
    assert ents == extract_entities("Ethan's sister is Sarah.")


@pytest.mark.asyncio
async def test_llm_extractor_falls_back_when_llm_raises():
    class Boom:
        async def complete(self, messages, schemas):
            raise RuntimeError("provider down")
    ents = await llm_extract_entities("Ethan's sister is Sarah.", llm=Boom())
    assert ents == extract_entities("Ethan's sister is Sarah.")


def test_llm_extraction_flag_defaults_off():
    """Item 66's gate: the LLM path stays dark until it beats deterministic
    on the fixtures and the flag is flipped deliberately."""
    assert settings.llm_entity_extraction_enabled is False
