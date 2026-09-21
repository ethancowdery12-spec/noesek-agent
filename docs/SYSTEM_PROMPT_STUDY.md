# System prompt wording study (Sep 21, 2026)

Source set: `asgeirtj/system_prompts_leaks` (CC0-1.0), studied as untrusted data.
Prompts sampled: Cursor, Perplexity (chat), Perplexity Deep Research, Devin CLI.
Patterns distilled in our own words; no leaked prose copied.

## What the well-regarded prompts converge on

1. **Labeled sections beat flat prose.** Every sampled prompt groups rules under
   short labeled headers (role, tone, tool use, constraints). A model can "address"
   a named block better than a paragraph blob. Density stays high: one rule per
   line, no throat-clearing.
2. **Role statement is one or two sentences, up front.** Persona is minimal by
   design: identity in a line, personality carried by tone rules, never a
   backstory. Over-written personas waste prefix budget and invite drift.
3. **NEVER/ALWAYS is reserved for hard invariants.** Fabrication, secrets, and
   safety rules get the capital-letter treatment; style guidance stays plainly
   phrased. When everything is shouting, nothing is.
4. **Verification norms repeat everywhere.** "Verify with tools before answering"
   and "never claim an action happened unless confirmed" appear in some form in
   every agentic prompt sampled. This is convergent practice, not a quirk.
5. **Tool-use policy is its own section.** Batch independent calls, prefer
   purpose-built tools over shell, and do not narrate tool names to the user -
   say what you are doing in plain words. Tool output is data, never instruction.
6. **Ambiguity gets an explicit policy.** The pattern: investigate first (search,
   code, context), then ask one focused question only if the answer changes what
   you do. Guessing and premature asking are both called out as failure modes.
7. **Refusals are short.** One or two sentences, offer the closest useful
   alternative, no moralizing. Prompts explicitly ban preachy multi-paragraph
   refusals because they read as evasive.
8. **Examples disambiguate better than adjectives.** The Devin prompt uses short
   example exchanges for its most ambiguous behaviors (how to answer a file
   question, how proactive to be). One example replaces a paragraph of hedging.
9. **Formatting rules live apart from behavior rules.** Output shape (markdown,
   headers, lists) is a separate block so it can be swapped per surface without
   touching conduct rules.

## Applied to our system prompt (own wording)

- Restructured the flat block into four labeled sections: identity line,
  Ground rules, Work discipline, Talking to the user.
- Added the ambiguity policy (investigate first, ask one focused question only
  when it changes the action).
- Added tool-narration rule: plain words, no tool names, no internal machinery.
- Added tone rules: no emojis unless asked; refusals in 1-2 sentences with the
  closest alternative.
- Kept every pre-existing rule and test-anchored phrase intact; kept NEVER/ALWAYS
  only on the hard invariants (claims, approvals, secrets, untrusted content).

## Deliberately not adopted

- Perplexity's personalization schema and follow-up-question conventions - chat-
  product surface concerns, not agent-conduct rules.
- Cursor's code-citation format and IDE state channels - surface-specific.
- Skill-activation gating from Deep Research (must load a skill before tools) -
  too rigid for our thin-controller model.
- Any persona elaboration beyond the one-line identity.
