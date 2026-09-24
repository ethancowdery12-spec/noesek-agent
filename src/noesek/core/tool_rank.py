"""BM25 tool ranking (Gorilla-style retrieval upgrade, roadmap item 82).

The original ToolRegistry.search ranked by keyword substring tiers
(exact name > name-substring > description-substring), which misses most
natural-language queries ("poke holes in this design" never substring-matches
"adversarial_review"). This module is a dependency-free BM25 ranker over
tool name + description tokens, measured against the frozen acceptance
fixtures in finetune/cases.py by evals/tool_retrieval.py.

Stdlib only; ~50 tools, so scoring is a trivial in-memory pass per query.
"""
import math
import re

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens; snake_case and camelCase split into words so
    tool names ('adversarial_review') match their component words."""
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    return _TOKEN_RE.findall(text.lower().replace("_", " "))


class BM25:
    """Okapi BM25 over a small fixed corpus."""

    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = docs
        self.n_docs = len(docs)
        self.avgdl = sum(len(d) for d in docs) / max(1, self.n_docs)
        df: dict[str, int] = {}
        for d in docs:
            for t in set(d):
                df[t] = df.get(t, 0) + 1
        # Lucene-style idf: always positive, so in tiny corpora (and for
        # terms shared by many tools) tf/length normalization still breaks
        # ties toward the doc where the term is concentrated.
        self.idf = {t: math.log(1 + (self.n_docs - n + 0.5) / (n + 0.5))
                    for t, n in df.items()}

    def score(self, query_tokens: list[str], doc: list[str]) -> float:
        if not doc:
            return 0.0
        tf: dict[str, int] = {}
        for t in doc:
            tf[t] = tf.get(t, 0) + 1
        dl = len(doc)
        norm = self.k1 * (1 - self.b + self.b * dl / max(1e-9, self.avgdl))
        total = 0.0
        for t in query_tokens:
            f = tf.get(t)
            if f:
                total += self.idf.get(t, 0.0) * (f * (self.k1 + 1)) / (f + norm)
        return total

    def rank(self, query: str, limit: int) -> list[tuple[float, int]]:
        """Return [(score, doc_index)] best-first; zero-score docs included
        last (stable by index) so callers always get `limit` candidates."""
        q = tokenize(query)
        scored = [(self.score(q, d), i) for i, d in enumerate(self.docs)]
        scored.sort(key=lambda x: (-x[0], x[1]))
        return scored[:limit]
