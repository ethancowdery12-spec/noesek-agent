# Command-execution sandbox isolation - design

Ethan, Sep 23 (verbatim): "GitHub Copilot now: when Copilot runs commands on
your behalf, it operates inside a sandbox that restricts which files it can
touch, which network resources it can reach, and whether it can access your
credentials at all - we should too."

This doc maps Copilot's three pillars onto what Noesek already enforces,
names the real gaps, and designs the policy layer that closes them. It is
the design gate before any build work in this lane; it also governs where
the sandboxed code interpreter (skills batch 1) plugs in.

## The three pillars vs. current state

| Pillar | docker-cli / docker-py backends | e2b backend | local-subprocess fallback |
|---|---|---|---|
| Filesystem scope | root FS `--read-only`; `/tmp` tmpfs (noexec, nosuid, 32-64m); workspace bind-mounted **read-only** at /workspace | remote microVM, isolated by the provider | isolated temp cwd only; host FS otherwise reachable for reads |
| Network egress | `--network=none` / `network_disabled=True` (full block) | provider microVM network | **NOT disabled** (documented in code) |
| Credential isolation | no host env passed into the container; no secrets in flags | operator's own E2B_API_KEY stays in operator env, never embedded, never requested | env stripped to PATH + PYTHONDONTWRITEBYTECODE |
| Resource caps | mem 256-512m, 1 CPU, pids 64 | provider limits | rlimits (CPU/AS/FSIZE/NPROC) + timeout |

Verdict: the container path is already close to Copilot's posture - in some
ways stricter (network fully off, everything read-only). The gaps are real
but specific.

## Gaps

1. **Privilege flags missing.** The `docker run` line has no `--cap-drop=ALL`,
   no `--security-opt=no-new-privileges`, and no `--user` - the payload runs
   as container root with default caps. Root in a user-namespace-less
   container plus a kernel bug is the classic escape path.
2. **No writable scope at all.** Today "which files it can touch" = none.
   That is safe but blocks the code-interpreter lane, which needs to produce
   output files. There is no declared writable scratch scoped to one run.
3. **Network is all-or-none.** Copilot restricts *which* resources; we can
   only do zero. Tools that legitimately need egress (package installs for
   an interpreter kernel, API-bound solvers) have no graded option inside
   the sandbox. (Tools like literature_search run outside the sandbox by
   design; that path is unaffected.)
4. **The local-subprocess fallback has no egress control.** It is the
   last-resort backend on hosts without Docker (Render included). Its doc
   warns, but nothing enforces, and no test pins the expectation.
5. **Policy is a hardcoded constant.** `ISOLATION` is one dict for every
   run. There is no per-run policy object a caller (controller, worker,
   future interpreter tool) can declare and a backend must honor, and no
   test that would fail if a backend silently weakened isolation.

## Design: a declared per-run SandboxPolicy

```python
@dataclass(frozen=True)
class SandboxPolicy:
    read_paths: tuple[str, ...]      # bind-mounted read-only (workspace etc.)
    write_path: str | None           # one fresh per-run scratch dir, tmpfs or emptyDir-like
    egress: tuple[str, ...]          # domain allowlist; empty = network none
    credentials: None = None         # structural: there is no field that can carry a secret
    mem_limit: str = "256m"
    timeout_seconds: int = 30
```

Rules the policy object makes structural:

- **Credentials: never.** No env passthrough field exists. Backends build the
  container env from a fixed allowlist (`PATH`, `PYTHONDONTWRITEBYTECODE`).
  A secret-shaped value in the command or code is the caller's problem to
  scrub, never the sandbox's to carry.
- **Writes: one scratch, or nothing.** `write_path` is a fresh per-run
  directory (tmpfs where the backend supports it), removed with the
  container. Deliverables leave the sandbox by stdout or by an explicit
  controller-side copy of declared output files - never by a writable bind
  into user space.
- **Egress: none by default, allowlist only.** An empty `egress` tuple keeps
  `--network=none`. A non-empty list is honored only on Docker via an egress
  proxy sidecar (M2); on e2b it maps to the provider's network controls; on
  local-subprocess it is REFUSED (backend errors, never silently allows) -
  that fallback stays no-network-guarantee.
- **Defaults = today's posture.** A bare `SandboxPolicy()` reproduces the
  current flags, so nothing existing loosens.

## Milestones

- **M1 (LANDED): policy object + hardening flags.** Introduce
  `SandboxPolicy`, thread it through `run_python`/`run_command`, add
  `--cap-drop=ALL --security-opt=no-new-privileges --user <uid>` to the
  Docker commands, add per-run tmpfs scratch as the only writable path, and
  add invariant tests: env contains no host secrets, mounts are read-only
  except scratch, non-empty egress on local-subprocess raises.
- **M2: egress allowlist.** Docker-only: per-run sidecar proxy (tiny
  forwarder pinned to the allowlist) on an internal network; sandbox
  container joins with no direct egress. Design detail deferred to its own
  PR; local-subprocess keeps refusing egress.
- **M3: code interpreter plugs in.** The batch-1 sandboxed code interpreter
  (jupyter_client kernel) runs as a sandbox payload under this policy:
  kernel env scrubbed, scratch writable, egress per the run's declared
  policy (package installs need M2).
- **M4 (FUTURE - requirement captured Sep 25, Ethan: "eventually, not right
  now"): guardian/reviewer decision model.** Every tool call the prime
  agent wants to make becomes a *request* (tool + args + the agent's stated
  reasoning) to a small dedicated decision model; only approved calls
  execute. Design requirements from the owner:
  - The reviewer sees minimal compressed context (a short summary - enough
    to judge intent, not the whole transcript) so a tricked prime agent
    cannot trivially trick the reviewer.
  - The reviewer *architecturally cannot* emit malformed or smuggled tool
    calls: its output is constrained (grammar/structured decode), and it
    returns an approve/deny decision - never a tool call of its own. A
    compromised prime agent therefore cannot produce a malformed execution
    even if the reviewer is also fooled.
  - Candidate open-weight decision models: Ethan will paste repo links;
    evaluate each (real code, license, authors' stated intent, size/speed
    fit, fine-tune feasibility under his ~$20 budget). His spoken name list
    is unverified - repo links are the only source of truth. Fine-tuning
    spend goes through the money gate like any other.
  - Relationship to M1-M3: the guardian gates *which* calls run; the
    sandbox policy bounds *what a call can touch* once approved. They are
    independent layers and either can ship first.

## Explicit non-goals

- No credential brokering into sandboxes, ever - including "scoped" or
  "temporary" secrets. If a payload needs an API, the sandbox returns and
  the controller does the call outside.
- No writable binds into the host workspace.
- No egress on the local-subprocess fallback.
