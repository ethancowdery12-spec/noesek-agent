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

- [ ] **2. docling** - `docling-project/docling`. VERIFIED, MIT, 67k stars. "Get your documents ready for gen AI" - PDFs/DOCX/etc. to structured output, tables, code, formulas, layouts. Use for multimodal input processing. **Status: TODO.**
- [ ] **3. markitdown** - `microsoft/markitdown`. VERIFIED, MIT, 186k stars. Converts files/office docs to clean Markdown, cuts token usage. Complement or alternative to docling; evaluate both, likely markitdown for lightweight conversion + docling for complex layouts. **Status: TODO.**

## P3 - Agent core quality

- [ ] **4. Anti-laziness: Unlazy** - `leonxlnx/unlazy`. VERIFIED, MIT, 3.5k stars. Anti-laziness agent skill built around the "Depth Tree" method. Add built-in. **Status: TODO.**
- [ ] **5. Anti-laziness: Ponytail** - `DietrichGebert/ponytail`. VERIFIED, MIT, 143k stars. Claude Code skill: "makes your AI agent think like the laziest senior dev in the room" (he named it twice). **Status: TODO.**
- [ ] **6. Long-conversation reminder.** VERIFIED concept: Anthropic's published Claude system prompt includes a reminder injected when chats run long ("long conversation reminder"). Research the exact mechanism from Anthropic's docs/release notes, then write our OWN custom version and inject on long sessions. No copying Anthropic text. **Status: TODO.**
- [ ] **7. Adversarial multi-review audit.** VERIFIED pattern (from an X post he relayed): agent A audits, agent B independently reviews, a third pass reconciles disagreements - a large share of the original "problems" get rejected. Guards against "keep asking what to improve and it will keep finding things." Build as a bounded audit loop: findings must survive independent re-review before they become work. **Status: TODO.**
- [ ] **8. Karpathy coding rules** - `multica-ai/andrej-karpathy-skills`. VERIFIED repo exists (214k stars) but NO license file detected - STUDY-ONLY. Distill ~4 rules into our own wording for the system prompt. **Status: TODO (study-only, own words).**
- [ ] **9. System-prompt wording study** - `asgeirtj/system_prompts_leaks`. VERIFIED, CC0-1.0, 68k stars (also YeeKal/leaked-system-prompts, tomturing/CL4R1T4S). Study how frontier system prompts are worded for efficiency. Explicitly NOT copying any leaked proprietary text - style lessons only. **Status: STUDY-ONLY.**

## P4 - Research capability

- [ ] **10. OpenResearch** - `alphaXiv/OpenResearch`. VERIFIED, MIT, 5.5k stars. "Turn your coding agents into research agents." Extract core ideas into a research skill/toggle. **Status: TODO.**
- [ ] **11. ARIS (Auto-Research-In-Sleep)** - `wanshuiyin/Auto-claude-code-research-in-sleep`. VERIFIED, MIT, 16k stars. Lightweight Markdown-only skills for autonomous adversarial multi-agent research (arxiv paper exists). Build research mode ideas in. **Status: TODO.**
- [ ] **12. Context7** - `upstash/context7`. VERIFIED exists; LICENSE UNCHECKED (API rate-limited). Up-to-date library docs for prompts via MCP. Likely integrate as a service, not copied code. **Status: TODO.**

## P5 - Prompt tooling

- [ ] **13. Prompt optimizer ("Prompt Master")** - `nidhinjs/prompt-master` (MIT, 13k stars) and `austinmao/prompt-master-claude` (MIT, 0 stars, same description). VERIFIED. Sloppy user prompt -> optimized prompt feature. **Status: TODO.**
- [ ] **14. Prompt library** - `f/prompts.chat` (f.k.a. Awesome ChatGPT Prompts). VERIFIED, 171k stars; license NOASSERTION (original was CC0 - confirm before bundling any prompt text). Curate a small set of high-value prompts as built-in references, not the whole thing. **Status: TODO.**

## P6 - Output humanization

- [ ] **15. Humanizer** - `blader/humanizer`. VERIFIED, MIT, 51k stars. Agent skill removing signs of AI-generated writing. Apply to outbound text style. **Status: TODO.**
- [ ] **16. AI-text detection study (StoryScope)** - VERIFIED: University of Maryland + Google DeepMind research; detects AI fiction at ~93% from story structure (arxiv). Read it; make our long-form output structurally less templated. **Status: STUDY-ONLY.**
- [ ] **17. Claude watermark removers** - `haidrrrry/claude-watermark-remover`, `anshrajore/Claude-Clean`. VERIFIED exist; LICENSES UNCHECKED. Small repos about stripping invisible watermark characters from Claude output. Relevant only if/when we surface Claude-generated text; ideas only. **Status: TODO (low).**

## P7 - Harness & architecture inspiration

- [ ] **18. OpenWorker** - `andrewyng/openworker`. VERIFIED, MIT, 18k stars (Andrew Ng). Study for agentic harness design. **Status: STUDY-ONLY -> extract ideas.**
- [ ] **19. cloudflare/computer** - VERIFIED, MIT, 9.2k stars. Persistent virtual FS in a Durable Object backed by SQLite; one command set, three interchangeable backends (container / Bash / JS isolate); FS works with no execution backend; claims better-than-disk metadata perf. README stamps it PREVIEW, unstable APIs, not for production - so: study the design, port the useful ideas into our own stable layer, do not ship their preview API. **Status: TODO (ideas port).**
- [ ] **20. NVIDIA cross-model KV cache transfer** - VERIFIED research (arxiv: "Cross-Model KV Cache Transfer in LLM Families: A Closed-Form Linear Mapping", + VentureBeat coverage). Figure out applicability to model switching in our runtime. Honest note: this is inference-engine-level tech (vLLM/SGLang territory); applicability to a provider-API agent like ours may be limited - document the conclusion either way. **Status: STUDY-ONLY.**
- [ ] **21. DeepSeek-Reasonix** - `esengine/DeepSeek-Reasonix`. VERIFIED, MIT, 36k stars. DeepSeek-native coding agent engineered around token-cost control. Study exactly how they keep token cost down; adopt techniques. **Status: TODO (study + adopt).**
- [ ] **22. agent-skills** - `addyosmani/agent-skills`. VERIFIED, MIT, 98k stars (Addy Osmani, Google). Production-grade engineering skills for coding agents. Cherry-pick built-ins. **Status: TODO.**
- [ ] **23. Graphify** - `Graphify-Labs/graphify`. VERIFIED, Apache-2.0, 120k stars. Turns codebases + docs + SQL schemas + PDFs into knowledge graphs for AI coding assistants. **Status: TODO (evaluate fit).**
- [ ] **24. WebMCP** - PARTIAL: `webmachinelearning/webmcp` exists (W3C/Chrome web ML community proposal, no license file detected), but it is NOT an OpenAI project as he guessed. Study the protocol idea (websites exposing tools to agents). **Status: STUDY-ONLY.**
- [ ] **25. Coldtea AGENTS.md study** - VERIFIED as a Coldtea blog analysis: "What the 100 biggest GitHub repos put in their AGENTS.md files." Read and apply to our own agent docs. **Status: STUDY-ONLY.**
- [ ] **26. awesome-harness-engineering** - `ai-boost/awesome-harness-engineering`. VERIFIED, license NOASSERTION (awesome-list), 4.4k stars. Reference list for harness tools/patterns/evals. **Status: STUDY-ONLY.**

## P8 - Skills & integrations

- [ ] **27. OfficeCLI** - `iOfficeAI/OfficeCLI`. VERIFIED, Apache-2.0, 31k stars. Office suite purpose-built for AI agents. Evaluate as an Office-docs capability. **Status: TODO.**
- [ ] **28. linkedin-skills** - `Linked-API/linkedin-skills` (MIT, 66 stars; also `quantumbyte31/linkedin-skills`). VERIFIED. LinkedIn automation skills (sales, social selling, data). Small; cherry-pick ideas. **Status: TODO (low).**
- [ ] **29. Anthropic-Cybersecurity-Skills** - `mukul975/Anthropic-Cybersecurity-Skills`. VERIFIED, Apache-2.0, 33k stars. 817 structured cybersecurity skills mapped to 6 frameworks. Cherry-pick relevant defensive skills. **Status: TODO.**
- [ ] **30. Agent-Reach** - `Panniantong/Agent-Reach`. VERIFIED, MIT, 84k stars. "Give your AI agent eyes to see the entire internet" - read/search Twitter/X etc. Could extend what connectors pull at sign-in. **Status: TODO (evaluate).**
- [ ] **31. screenshot-to-code** - `abi/screenshot-to-code`. VERIFIED, MIT, 79k stars. Screenshot -> clean code. Study pipeline. **Status: STUDY-ONLY.**
- [ ] **32. skill-ui** - `gsknnft/skill-ui`. VERIFIED exists; LICENSE UNCHECKED. Frontend skill. **Status: TODO (low).**

## P9 - Security testing

- [ ] **33. Strix pentest** - `usestrix/strix`. VERIFIED exists (open-source AI pentest agent; strix.ai); LICENSE UNCHECKED. Run it AGAINST our agent as an adversary; fix what it finds. **Status: TODO (after P1 lands).**

## P10 - UI/frontend (lowest value - see note)

NOTE: Noesek is messaging-native (WhatsApp/Slack/Telegram/local chat) - there is no web frontend today, so UI animation/component libraries have no surface to land on. These stay parked until a frontend exists.

- [ ] **34. anime.js** - `juliangarnier/anime`. VERIFIED exists; license unchecked (historically MIT). PARKED.
- [ ] **35. motion.dev / Framer Motion** - `motiondivision/motion`. VERIFIED exists; license unchecked. PARKED.
- [ ] **36. "coconut UI"** - PARTIAL/UNVERIFIED: `MVCoconut/coconut.ui` exists but is a 96-star Haxe framework - probably not what he meant. PARKED pending clarification.
- [ ] **37. "backlit UI"** - UNVERIFIED: nearest matches (`bklit/bklit-ui`, `bennypowers/backlit`) don't clearly match "backlit UI components." PARKED pending clarification.
- [ ] **38. Playwright CLI** - we already ship Playwright (the /computer/browse tool). Evaluate whether the CLI form adds anything over our executor. **Status: TODO (cheap evaluation).**

## Unmatched / needs clarification

- [ ] **39. "Agent Memory" repo** - UNVERIFIED. Too vague to identify (many repos by that name). If he means a specific one, need the link or author.
- [ ] **40. Unnamed "browser stuff" repo** - UNVERIFIED. He said "maybe use that GitHub repo" without a name; we already run Playwright in production.

## Open mandate

- [ ] **41.** "If you research and find anything else that might be useful, please feel free to implement that." - Ongoing; anything added under this mandate gets logged here with source + license first.

---

Working agreement: implement in the P1-P9 order above; park P10; update this file as items land (checkbox + date + PR). Each copied component gets attribution + a docs/licenses entry per the reuse rule.
