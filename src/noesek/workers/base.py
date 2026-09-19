from dataclasses import dataclass, field

@dataclass(frozen=True)
class Worker:
    name: str
    instruction: str
    tools: tuple[str, ...] = field(default=())

# Workers only receive read-only tools. Anything consequential must come back
# through the conversation controller, where the approval gate lives.
WORKERS = {
 "researcher": Worker("researcher",
   "Find reliable sources, preserve URLs, distinguish facts from inference, and return a cited synthesis.",
   ("search_web", "fetch_url")),
 "coder": Worker("coder",
   "Plan, implement, test, and explain code. Prefer small reversible changes. "
   "Map the repo first (repo_map), edit with apply_edit SEARCH/REPLACE hunks "
   "(write_file for new files), verify changes by running code, and finish with "
   "the submit checklist (summary, files_changed, verification evidence, limitations).",
   ("run_python", "fetch_url", "read_file", "repo_map", "apply_edit", "write_file", "submit")),
 "operator": Worker("operator",
   "Carry out stateful work carefully. Check current state and report exactly what changed; never claim unverified effects.",
   ("fetch_url", "run_python")),
 "evaluator": Worker("evaluator",
   "Test outputs against explicit criteria, identify unsupported claims, and report failures precisely.",
   ("run_python", "fetch_url")),
}
