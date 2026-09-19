# Policy engine + approval leases (v2, stage B)

## Ordered rules

`core.policy.evaluate_policy(tool, risk, arguments)` walks an ordered rule
list; first match wins, returning allow / ask / deny. Rule 0 is always the
hardline content gate (vendored upstream detection tables, MIT): hardline and
sudo-stdin matches deny unconditionally and no configured rule, approval, or
mode can override them. Configured rules (`NOESEK_POLICY_RULES`, a JSON list
of `{effect, tools?, risks?, contains?, reason?}`) come next; the built-in
defaults (ask for write/external/money/destructive, allow otherwise) close
the list, so v1.11.3 behavior is unchanged with no configuration.

## Approval leases

An approval is a single-use lease bound to:

- the conversation (query-scoped, as before),
- the tool name and its **canonical arguments** (sort-keyed JSON, recorded
  at creation and re-verified at execution - a mismatch blocks as tampering),
- the originating **turn spine id** (`turn_id`, stage A),
- one execution (`pending -> executed|rejected|expired|blocked`),
- the existing TTL (`NOESEK_APPROVAL_TTL_HOURS`).

The hardline content gate is also re-run at execution time, so an approval
created for safe-looking arguments can never launder blocked content.

Existing databases upgrade in place: `noesek migrate` adds `turn_id` and
`canonical_args` to `approvals`.

## Provenance

Ordered first-match rules are a standard firewall pattern, re-implemented
here; lease binding to canonical arguments and run identity re-implements
patterns studied in the MIT-licensed harness deep-dives (upstream vendored
approval stack, SWE-agent). No code copied.
