"""Tool-retrieval gate (Gorilla pattern, roadmap item 82).

Pins the measured retrieval accuracy of the live ToolRegistry.search (BM25)
on the frozen natural-language fixtures in finetune/cases.py. Floors leave
headroom for corpus growth as new tools land; a ranker regression or a
description rewrite that breaks retrievability fails here.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from finetune.cases import TEST_CASES
from noesek.core.controller import Controller
from noesek.core.tool_rank import BM25, tokenize


class QuietLLM:
    async def complete(self, messages, schemas):
        class Reply:
            content = "done"
            tool_calls = []
        return Reply()


def _positive_cases():
    return [c for c in TEST_CASES if not c["critical"] and c["calls"]]


def test_search_finds_expected_tool_top5(db):
    registry = Controller(llm=QuietLLM()).registry(1)
    cases = _positive_cases()
    hits = sum(1 for c in cases if c["calls"][0] in registry.search(c["query"], 5))
    rate = hits / len(cases)
    assert rate >= 0.95, f"top-5 retrieval {rate:.1%} on {len(cases)} frozen cases (floor 95%)"


def test_search_finds_expected_tool_top1(db):
    registry = Controller(llm=QuietLLM()).registry(1)
    cases = _positive_cases()
    hits = sum(1 for c in cases if c["calls"][0] in registry.search(c["query"], 1))
    rate = hits / len(cases)
    assert rate >= 0.65, f"top-1 retrieval {rate:.1%} on {len(cases)} frozen cases (floor 65%)"


def test_search_empty_query_returns_nothing(db):
    registry = Controller(llm=QuietLLM()).registry(1)
    assert registry.search("", 5) == []
    assert registry.search("   ", 5) == []


def test_tokenize_splits_snake_and_camel():
    assert tokenize("adversarial_review") == ["adversarial", "review"]
    assert tokenize("gmailRead") == ["gmail", "read"]


def test_bm25_ranks_relevant_doc_first():
    bm25 = BM25([tokenize("read gmail inbox emails"),
                 tokenize("list calendar events meetings")])
    ranked = bm25.rank("what meetings do I have", 2)
    assert ranked[0][1] == 1
    assert ranked[0][0] > 0
