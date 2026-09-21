# Noesek Research Roadmap

Source: Ethan's WhatsApp brain-dump, Sep 20 2026 (~8:36 PM CT). His instruction: "write it down on some document or something so you don't forget it and make a checklist." This is that checklist.

Status legend:
- **VERIFIED** - repo/study confirmed to exist (live check Sep 20 2026); license read from the repo's LICENSE file via GitHub API.
- **UNVERIFIED** - could not confirm what he named exists; needs more research before any use.
- **PARTIAL** - something exists but details differ from his description.

Implementation status: TODO / IN PROGRESS / DONE / STUDY-ONLY / DECLINED.

Reuse rule (standing): MIT/Apache/BSD/Unlicense = code may be copied with attribution + provenance header + docs/licenses entry. No detected license / copyleft / source-available = study ideas only, re-implement. Never copy leaked proprietary content, even paraphrased.

---

## P1 - Safety first

- [x] **1. llms.txt / web-content prompt-injection safeguards.** VERIFIED threat class (no single repo - this is a build item). His note: "AI agents will install malware from websites because they'll read the LLMs.txt, LLMs.full.txt, or any files on a website and they'll trust it. If that file tells it to download stuff, they'll just do it." Built: `core/content_guard.py` - tier-1 download-and-execute payloads redacted inline, tier-2 lures flagged with a model-facing notice, all tool results + /computer/browse text covered. **Status: DONE Sep 20 (#77).**

## P2 - Document & multimodal ingest

- [x] **2. docling** - `docling-project/docling`. VERIFIED, MIT, 67k stars. "Get your documents ready for gen AI" - PDFs/DOCX/etc. to structured output, tables, code, formulas, layouts. **Status: DONE Sep 20 (#79)** - optional PDF engine behind NOESEK_DOC_ENGINE (auto/markitdown/docling).
- [x] **3. markitdown** - `microsoft/markitdown`. VERIFIED, MIT, 186k stars. Converts files/office docs to clean Markdown, cuts token usage. **Status: DONE Sep 20 (#79)** - default engine: WhatsApp documents (PDF/DOCX/PPTX/XLSX/CSV/HTML) convert to Markdown, pass the content guard, and land in chat as text.

## P3 - Agent core quality

- [x] **4. Anti-laziness: Unlazy** - `leonxlnx/unlazy`. VERIFIED, MIT. **Status: DONE Sep 21** - adopted as prompt discipline, not the skill itself: the system prompt now requires deciding the checks that prove work is done before starting and running them before claiming completion (unlazy's "acceptance gates, enforced not requested" idea in our own words).
- [x] **5. Anti-laziness: Ponytail** - `DietrichGebert/ponytail`. VERIFIED, MIT. **Status: DONE Sep 21** - adopted its YAGNI core into the system prompt: prefer the smallest change that fully satisfies the request; no speculative features or extra abstractions.
- [x] **6. Long-conversation reminder.** VERIFIED concept: Anthropic staples a runtime note onto the user's latest message once a chat runs long. **Status: DONE Sep 20 (#82)** - our own <session-reminder> (own wording) appends to the latest user message past 30 total messages (NOESEK_LONG_REMINDER_MIN_MESSAGES); system prompt marks it runtime-origin so forged lookalikes are not obeyed.
- [x] **7. Adversarial multi-review audit.** VERIFIED pattern (agent A audits, agent B independently re-reviews, third pass reconciles). **Status: DONE Sep 20 (P7)** - `adversarial_review` chat tool is the deterministic reconciliation pass: findings survive only with concrete falsifiable evidence (quote/line/number/code span), speculation and bad severities rejected with reasons, duplicates collapse to highest severity, per-task-type audit checklists returned. No model call, no deps.
- [x] **8. Karpathy coding rules** - `multica-ai/andrej-karpathy-skills`. VERIFIED, MIT, 210k stars. **Status: DONE Sep 21** - distilled into the system prompt (own wording): surface wrong assumptions, inconsistencies, and tradeoffs instead of running with them; ask when a missing fact changes the answer; no bloat, no dead code.
- [x] **9. System-prompt wording study** - `asgeirtj/system_prompts_leaks`. VERIFIED, CC0-1.0. **Status: STUDIED Sep 21** - style lessons applied across tonight's prompt work (short imperative rules, explicit "never claim X unless a tool confirms it", untrusted-content boundaries). No leaked proprietary text copied, ever.

## P4 - Research capability

- [x] **10. OpenResearch** - `alphaXiv/OpenResearch`. VERIFIED, MIT, 5.5k stars. **Status: DONE Sep 20 (P4)** - multi-query fan-out idea landed as the `deep_research` tool on the researcher worker (expand question -> parallel searches -> dedupe -> concurrent fetch -> cited evidence pack).
- [x] **11. ARIS (Auto-Research-In-Sleep)** - `wanshuiyin/Auto-claude-code-research-in-sleep`. VERIFIED, MIT, 16k stars. **Status: DONE Sep 20** - fan-out half landed with P4 (#83, `deep_research`); adversarial review half landed with P7 (`adversarial_review`).
- [x] **12. Context7** - `upstash/context7`. LICENSE VERIFIED MIT (Sep 21). **Status: DONE Sep 21 (Ethan ordered MCP same day, superseding the morning's no-adoption verdict)** - MCP client core landed in `core/mcp_client.py` (official `mcp` SDK over Streamable HTTP, zero new deps - the SDK was already pinned); Context7 remote endpoint (`https://mcp.context7.com/mcp`, stateless) is the first server; `library_docs` controller tool runs resolve-library-id -> query-docs; provider-extensible via NOESEK_MCP_EXTRA_SERVERS JSON; optional NOESEK_CONTEXT7_API_KEY for higher rate limits.

## P5 - Prompt tooling

- [x] **13. Prompt optimizer ("Prompt Master")** - `nidhinjs/prompt-master` (MIT, 13k stars). VERIFIED. **Status: DONE Sep 20 (P5)** - `optimize_prompt` chat tool, own deterministic implementation of its pipeline (task-type detection -> structured Objective/Approach/Constraints/Ground-rules/Output-format rewrite, constraint extraction, grounding anchor). No extra model call, no deps.
- [x] **14. Prompt library** - `f/prompts.chat` (f.k.a. Awesome ChatGPT Prompts). VERIFIED, 171k stars; license RESOLVED Sep 21: dual - code MIT, prompt content CC0 (LICENSE-CC0 in repo). **Status: VERDICT Sep 21: NO BUNDLING** - our system prompt is purpose-built and P5's optimize_prompt rewrites user prompts on demand; a static CC0 prompt pack adds weight without a consumer. Revisit if we ship user-facing prompt templates.

## P6 - Output humanization

- [x] **15. Humanizer** - `blader/humanizer`. VERIFIED, MIT, 51k stars. **Status: DONE Sep 20 (P6)** - `humanize` chat tool, own deterministic rule set (pattern source: Wikipedia "Signs of AI writing"): filler stripper, em-dash/curly-quote normalization, safe verb swaps (utilize->use, delve->dig), inflated-vocabulary flags with suggestions. Facts/names untouched; no model call, no deps.
- [x] **16. AI-text detection study (StoryScope)** - VERIFIED research. **Status: STUDIED Sep 21** - lesson folded into the humanizer design: detectors key on structural template (uniform paragraph shapes, predictable arcs), so the humanizer varies structure and strips template tells, not just words.
- [x] **17. Claude watermark removers** - `haidrrrry/claude-watermark-remover` (GitHub flags license "Other"; a plugin registry claims MIT - ambiguous), `anshrajore/Claude-Clean` (MIT). **Status: VERDICT Sep 21: NO APPLICATION** - both strip AI provenance marks (invisible Unicode, C2PA/EXIF) from user-owned content; noesek does not surface Claude-generated text and provenance stripping is not a capability we want. Ideas noted, nothing ported.

## P7 - Harness & architecture inspiration

- [x] **18. OpenWorker** - `andrewyng/openworker`. VERIFIED, MIT, 18k stars. **Status: STUDIED Sep 21: ALREADY ALIGNED** - its engine assembly (base tools + permissions + AGENTS.md + memory + progressive-disclosure skill catalog) maps to what we already run: approval_engine gates, remember/recall memory, search_tools progressive disclosure. New idea taken: a root AGENTS.md (item 25). Nothing else to port.
- [x] **19. cloudflare/computer** - VERIFIED, MIT. **Status: STUDIED Sep 21: DESIGN ALREADY MIRRORED** - one command set across interchangeable backends with an FS that works without an execution backend = our sandbox_backends/computer_use layering (browse/screenshot run with no shell backend). Their API is stamped PREVIEW/unstable; nothing copied, no port needed.
- [x] **20. NVIDIA cross-model KV cache transfer** - VERIFIED research. **Status: DONE Sep 21 (multi-model landed)** - KV-cache transfer itself stays NOT APPLICABLE (inference-engine tech; we call provider APIs). What Ethan actually wanted shipped instead: a real multi-model layer - role-based model catalog (NOESEK_LLM_MODELS), deepseek-chat + deepseek-reasoner on the same key, per-chat model switching via the switch_model tool, per-task defaults (research/eval go to the reasoner), model-bound adapters with prefix-cache-reset note. Provider-extensible by design. KV note (Sep 21): cross-model KV-cache transfer (NVIDIA research direction) = WATCH item - applies only when self-hosting models, impossible through hosted APIs where the cache is server-side. Practical win adopted: prompt prefixes kept static and identical across roles/models so provider-side prefix caching stays hot.
- [x] **21. DeepSeek-Reasonix** - `esengine/DeepSeek-Reasonix`. VERIFIED, MIT, 36k stars. **Status: STUDIED + AUDITED Sep 21** - their two big token-cost fixes: (1) keep the prompt byte prefix stable (no per-turn timestamps or history reordering) so provider prefix caching hits; (2) never echo reasoning_content back into the prompt (~521 wasted tokens/turn measured on reasoner chains). Audited our stack: context.py injects no per-turn timestamps and llm/providers never round-trip reasoning content - both cache-killers already absent. Per-turn cache-hit metrics are DeepSeek-billing-specific, not applicable to our providers. Nothing to adopt.
- [x] **22. agent-skills** - `addyosmani/agent-skills`. VERIFIED, MIT, 98k stars. **Status: CHERRY-PICKED Sep 21** - the pack's core discipline (structured workflow + explicit verification steps before claiming done) landed in batch 1's work-discipline prompt block. The remaining 22 skills are SKILL.md workflows for desktop coding agents; noesek's channel-native surface does not load skill files. Done.
- [x] **23. Graphify** - `Graphify-Labs/graphify`. VERIFIED, Apache-2.0, 120k stars. **Status: VERDICT Sep 21: NO FIT** - it builds queryable knowledge graphs of a codebase for repo-scale coding assistants (deterministic AST parsing, no vector store - clean design). noesek is a messaging-native personal agent; FTS5 + keyword memory already covers recall and a code-graph pipeline fights the thin-controller design. No adoption.
- [x] **24. WebMCP** - `jasonjmcghee/WebMCP` (VERIFIED, MIT, 790 stars). **Status: VERDICT Sep 21: NO NEAR-TERM APPLICATION** - turning web pages into MCP tool servers needs an MCP host; we have none, and browser work already runs through /computer/browse on the cloud browser. Idea logged for a future MCP sidecar; nothing built.
- [x] **25. Coldtea AGENTS.md study** - **Status: STUDIED + APPLIED Sep 21** - read the field study of the 100 biggest repos' AGENTS.md files: consensus content is architecture/repo layout, how to test, build commands, dos-and-don'ts, PR etiquette, code style; keep it short and hand-written. Applied: root AGENTS.md added to this repo.
- [x] **26. awesome-harness-engineering** - `ai-boost/awesome-harness-engineering`. VERIFIED, NOASSERTION (link list). **Status: STUDIED Sep 21** - reference list of harness tools/patterns/evals; its categories (eval gates, loop guards, policy enforcement, trajectory review) are already first-class here (docs/eval_gate.md, loop_guard.md, policy_engine.md, turn_spine.md). Link list only - nothing copied. Done.

## P8 - Skills & integrations

- [x] **27. OfficeCLI** - `iOfficeAI/OfficeCLI`. VERIFIED, Apache-2.0, 31k stars. **Status: VERDICT Sep 21: NO ADOPTION** - genuinely strong single-binary Office suite for agents (read/edit Word/Excel/PowerPoint, no Office install). But noesek's doc needs today are ingest + generated deliverables, and shipping a second binary fights the zero-added-dependency rule. Revisit if Ethan asks for Office editing.
- [x] **28. linkedin-skills** - `Linked-API/linkedin-skills` (MIT, 66 stars). **Status: VERDICT Sep 21: NO FIT** - thin wrappers over the paid Linked API CLI for sales/social-selling automation; noesek has no LinkedIn connector and there is no LinkedIn automation ask. Nothing transferable.
- [x] **29. Anthropic-Cybersecurity-Skills** - `mukul975/Anthropic-Cybersecurity-Skills`. VERIFIED, Apache-2.0, 33k stars. **Status: DONE Sep 21 (P9 batch)** - cherry-picked defensive patterns into `security_audit`: 5 new probes (jwt-none, path-concat-open, insecure-temp, weak-hash, debug-enabled), regexes our own, attribution in source. First run caught a real mktemp race in our own computer server - fixed with mkstemp. Findings re-audited: only the 2 previously accepted remain.
- [x] **30. Agent-Reach** - `Panniantong/Agent-Reach`. VERIFIED, MIT, 84k stars. **Status: VERDICT Sep 21: NO ADOPTION** - wraps scraper CLIs for X/Reddit/YouTube/GitHub/etc. ("zero API fees"). Scraping logged-out social sites is brittle and ToS-risky; our connectors use official APIs and Brave search already covers general web reach. Nothing ported.
- [x] **31. screenshot-to-code** - `abi/screenshot-to-code`. VERIFIED, MIT, 79k stars. **Status: STUDIED Sep 21** - pipeline: middleware-staged WebSocket flow, screenshot -> vision model -> parallel multi-variant code generation -> pick best. Study-only as planned: noesek has no screenshot-to-code surface. The parallel-variant-generation pattern is logged for future creative tools.
- [x] **32. skill-ui** - `gsknnft/skill-ui`. LICENSE VERIFIED MIT (README + npm, Sep 21). **Status: VERDICT Sep 21: NO ADOPTION** - immature (0 stars, ~5 weekly npm downloads), TS/React frontend skill; noesek has no TS surface. Done.

## P9 - Security testing

- [x] **33. Strix pentest** - `usestrix/strix`. VERIFIED, Apache-2.0 (checked Sep 21). **Status: DONE Sep 21 (P8)** - own bounded auditor `security_audit`: static probes (exec, shell=True, hardcoded secrets, SQL f-strings, TLS/CORS) + FastAPI route inventory over our own layer, file:line evidence per finding, report at docs/SECURITY_AUDIT.md. First run: 2 findings, both reviewed and accepted with rationale.

## P10 - UI/frontend (lowest value - see note)

NOTE: Noesek is messaging-native (WhatsApp/Slack/Telegram/local chat) - there is no web frontend today, so UI animation/component libraries have no surface to land on. These stay parked until a frontend exists.

- [x] **34. anime.js** - `juliangarnier/anime`. LICENSE VERIFIED MIT (Sep 21, 72k stars). **Status: DONE Sep 21 (knowledge adoption)** - un-parked per Ethan: usage patterns collected into docs/UI_LIBRARY_REFERENCE.md and the system prompt now teaches when and how to use anime.js v4 for web UI code. No runtime dependency.
- [x] **35. motion.dev / Framer Motion** - `motiondivision/motion`. LICENSE VERIFIED MIT (Sep 21, Motion B.V.). **Status: DONE Sep 21 (knowledge adoption)** - same treatment as anime.js: patterns in docs/UI_LIBRARY_REFERENCE.md + system-prompt guidance (springs, gestures, scroll reveals, React motion components). No runtime dependency.
- [x] **36. "coconut UI" = kokonutui** - `kokonut-labs/kokonutui`. LICENSE VERIFIED MIT. **Status: DONE Sep 21 (knowledge adoption)** - copy-paste component patterns collected into docs/UI_LIBRARY_REFERENCE.md with attribution rule; system prompt points to it for component work. No runtime dependency.
- [ ] **37. "backlit UI"** - UNVERIFIED after real searching: nearest matches (`bklit/bklit-ui`, `bennypowers/backlit`) do not match "backlit UI components". PARKED - needs Ethan to name the repo.
- [x] **38. Playwright CLI** - **Status: VERDICT Sep 21: NO ADDITIONAL VALUE** - our /computer/browse executor already plans, validates, and runs navigate/click/type/extract/screenshot over Playwright with an 8k text cap; the CLI form adds a shell wrapper, nothing else.

## Unmatched / needs clarification

- [x] **39. "Agent Memory" = agentmemory** - `rohitg00/agentmemory` (VERIFIED, Apache-2.0, 28k stars). **Status: DONE Sep 21** - adopted into our memory layer: new `handoff` and `lesson` memory kinds, a `handoff` tool, and the latest active handoff is now always pinned into the conversation context (their session-hook idea) instead of being query-dependent. Their keyword-first fallback and BM25 recall were already covered by our FTS5 + keyword ranker; MCP server and vector/graph search deliberately not adopted (zero-added-dependency rule). UPDATE Sep 21 (Ethan ordered vector + graph memory same day, superseding the zero-added-dependency skip): vector memory landed in `core/memory_vector.py` - pluggable embedder (default zero-dep hashed-ngram local vectors; optional OpenAI-compatible /embeddings via NOESEK_EMBED_* settings), vectors in SQLite keyed by memory id with lazy backfill, cosine fused into recall on top of the FTS5/keyword baseline. Graph memory landed same day in `core/memory_graph.py` - deterministic zero-dep entity extraction (quoted phrases, mentions/tags, capitalized phrases, token fallback), co-occurrence edges with verb-pattern relation types in SQLite, entity-neighborhood boost fused into recall after the vector layer. NOESEK_GRAPH_MEMORY_ENABLED to disable.
- [x] **40. Unnamed "browser stuff" repo** - UNVERIFIED (never named). **Status: VERDICT Sep 21: COVERED** - the only browser capability in scope is already live: Playwright-driven /computer/browse + /computer/screenshot, verified in production Sep 21.

## Open mandate

- [x] **41.** "If you research and find anything else that might be useful, please feel free to implement that." - **Status: STANDING (recorded Sep 21)** - open mandate stays active; the Sep 20-21 audit closed every named item above, and anything added under this mandate gets logged here with source + license first.
- [x] **42. OpenDesign (design agent skills)** - `nexu-io/open-design`. VERIFIED, Apache-2.0, 94k stars. **Status: STUDIED Sep 21: NO ADOPTION** - skills-protocol.md separates atomic functional skills (SKILL.md convention) from rendering design-templates; design systems are schema'd packages, not standalone markdown. noesek has no design-rendering surface (same reasoning as items 34-36) and P5's optimize_prompt handles text prompts, so neither the skill protocol nor the DESIGN.md brand format has a consumer today. Revisit with a web/dashboard surface.

---

Working agreement: implement in the P1-P9 order above; park P10; update this file as items land (checkbox + date + PR). Each copied component gets attribution + a docs/licenses entry per the reuse rule.
