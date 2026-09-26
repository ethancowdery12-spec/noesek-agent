"""Diff-first code review pipeline.

Architecture adapted (own words, Apache-2.0) from alibaba/open-code-review:
group changed files, plan risks, review each group with a bounded
context-tool loop, then fact-check comments against the diff before
reporting. Deterministic pieces (diff parsing, grouping, line anchoring,
dedupe) live here; the model is used only for plan/review/filter passes.
See THIRD_PARTY_NOTICES.md.
"""
