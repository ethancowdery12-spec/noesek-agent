"""Chat-tool registrations for the metadata/creative tool family.

Kept out of controller.py so the controller stays a wiring table; each
tool's spec lives next to its siblings. Registers: scrub, rewrite_natural,
generate_variants.
"""
from __future__ import annotations

from sqlalchemy import select

from ..core.tools import ToolSpec
from ..core.types import Risk
from ..db import Conversation, Session
from .browser_cookies import BrowserCookiesInput, browser_cookies
from .code_graph import CodeGraphInput, code_graph
from .design_system import DesignInput, design_system
from .linkedin import LinkedInInput, linkedin
from .office_doc import OfficeDocInput, office_doc
from .playbook import PlaybookInput, playbook
from .naturalize import RewriteNaturalInput, rewrite_natural
from .scrub import ScrubInput, scrub_handler
from .variants import GenerateVariantsInput, generate_variants_handler
from .story_critique import StoryCritiqueInput, story_critique_handler
from .exact_solve import ExactSolveInput, exact_solve
from .seo_audit import SeoAuditInput, seo_audit
from .geo_audit import GeoAuditInput, geo_audit
from .literature import LiteratureInput, literature_search
from .duckdb_query import DuckdbInput, duckdb_query
from .interpreter import InterpreterInput, code_interpreter_handler
from .test_verifier import VerifierInput, test_verifier
from .codeact import CodeActInput, codeact_handler


def register_chat_extras(r, conversation_id: int, controller, timeout: float) -> None:
    r.register(ToolSpec("scrub","Clean the user's own text or files of hidden metadata: strips invisible watermark characters from text, and removes EXIF/document-properties metadata from their own images, Office docs, and PDFs (PDF needs optional pypdf). Creates a -clean copy; originals untouched.",ScrubInput,Risk.WRITE,scrub_handler(conversation_id),timeout_seconds=timeout))
    r.register(ToolSpec("rewrite_natural","Rewrite the user's own AI-sounding text so it reads naturally: cuts throat-clearing and hedge stacks, removes formulaic transitions, then applies the humanizer passes; reports rhythm issues. No claim about detectors.",RewriteNaturalInput,Risk.READ,rewrite_natural,timeout_seconds=timeout))

    r.register(ToolSpec("playbook","Load a working brief for a high-value workflow: mock interview, both-sides debate, writing tutor, step-by-step teacher, structured critic. Use list to see them, load to adopt one for this conversation.",PlaybookInput,Risk.READ,playbook,timeout_seconds=timeout))
    r.register(ToolSpec("design_system","Design-system skills: list/get schema'd themes (color, type, spacing, radius tokens) and render a self-contained styled HTML deliverable (title, subtitle, sections) into the file store.",DesignInput,Risk.WRITE,design_system,timeout_seconds=timeout))
    r.register(ToolSpec("linkedin","LinkedIn via the official API: profile (who am I) or share (post text as the member, PUBLIC or CONNECTIONS). Activates only when NOESEK_LINKEDIN_ACCESS_TOKEN is set; otherwise explains setup.",LinkedInInput,Risk.WRITE,linkedin,timeout_seconds=timeout))
    r.register(ToolSpec("office_doc","Read, create, and edit Word/Excel/PowerPoint files in the agent file store through the OfficeCLI binary (view/get outline or JSON; create/add/set/remove/close). Degrades cleanly when the officecli binary is not installed.",OfficeDocInput,Risk.WRITE,office_doc,timeout_seconds=timeout))
    r.register(ToolSpec("browser_cookies","Persistent browser sessions: status (stored/enabled sites, counts only), enable/disable a site (the per-site approval before any logged-in session is used on a browse run), revoke, clear, audit. Imports never happen here - cookie exports are posted directly to the /computer/browser-state/import endpoint; cookie values are never shown or accepted in chat.",BrowserCookiesInput,Risk.WRITE,browser_cookies,timeout_seconds=timeout))
    r.register(ToolSpec("code_graph","Answer structural questions about the Noesek codebase itself: what calls a function, what a function calls, what imports a module, a module's imports, a module outline, or repo stats. Deterministic AST analysis of the installed package.",CodeGraphInput,Risk.READ,code_graph,timeout_seconds=timeout))
    async def _resolve_llm():
        async with Session() as s:
            ov = await s.scalar(select(Conversation.model_override).where(Conversation.id == conversation_id))
        return controller._llm_for_model(ov)
    r.register(ToolSpec("generate_variants","Generate N distinct candidate versions of a creative output in parallel (names, taglines, subject lines, drafts), then pick the best with a judge pass and show the rest. Use for creative asks where one shot is a lottery.",GenerateVariantsInput,Risk.READ,generate_variants_handler(_resolve_llm),timeout_seconds=timeout))
    r.register(ToolSpec("seo_audit","Audit one HTML page for rankability (claude-seo checks, MIT, own-words): title/meta bounds, single h1, heading outline, lang/charset/viewport, canonical, noindex, mixed content, og/twitter cards, JSON-LD validity + deprecated types, content depth, image alt coverage. Returns 0-100 score with per-check pass/warn/fail, evidence, and fixes. Run on any website/landing deliverable before shipping.",SeoAuditInput,Risk.READ,seo_audit,timeout_seconds=timeout))
    r.register(ToolSpec("geo_audit","Audit one HTML page for citability inside AI answers (geo-optimizer-skill method families, MIT, own-words; GEO research line arXiv 2311.09735): outbound source citations, statistics, quotations, answer-ready lead, question-form headings, extractable lists/tables, JSON-LD entity clarity with sameAs, Wikidata entity presence (create/maintain the business's wikidata.org item and link it via sameAs - knowledge-graph presence makes AI assistants surface it), freshness dates, AI-crawler access in robots.txt, llms.txt. Pass the page HTML plus robots_txt/llms_txt when available. Returns 0-100 score with per-check pass/warn/fail, evidence, and fixes. Companion to seo_audit - run both on website/landing deliverables.",GeoAuditInput,Risk.READ,geo_audit,timeout_seconds=timeout))
    r.register(ToolSpec("literature_search","Search academic papers across open scholarly APIs (arXiv, Crossref, Semantic Scholar, OpenAlex - free, keyless). Returns deduped results with title, authors, year, abstract snippet, and link. Use for research questions, literature reviews, citations, and finding papers by topic or author.",LiteratureInput,Risk.READ,literature_search,timeout_seconds=timeout))
    r.register(ToolSpec("duckdb_query",'Run one read-only SQL statement over files in the agent file store (CSV/TSV/JSON/NDJSON/Parquet become views named by file stem, e.g. sales.csv -> sales) with DuckDB. Read-only gate: SELECT/WITH/EXPLAIN/DESCRIBE/SHOW/SUMMARIZE only; writes, ATTACH, and direct reader functions are refused. Use for sums, joins, filters, and exploration over data files.',DuckdbInput,Risk.READ,duckdb_query,timeout_seconds=timeout))
    r.register(ToolSpec("test_verifier","Run pytest with coverage over this conversation's code workspace (the code_interpreter working directory, or a subpath) and return structured results: pass/fail/error counts, failed test names, the failure output tail, and per-file line coverage with a total. The verify step of the write -> test -> fix loop: after writing or changing code in code_interpreter, run this, read the failures, fix, and re-run until green. Extra pytest flags like '-k filter -x' are accepted. Sandboxed: scrubbed environment, resource limits, timeout.",VerifierInput,Risk.WRITE,lambda inp: test_verifier(inp, conversation_id),timeout_seconds=timeout))
    def _codeact_allowed():
        return {n for n in r.names() if r.get(n).risk == Risk.READ and n != "code_act"}
    r.register(ToolSpec("code_act","Compose read-only tools in one sandboxed Python program instead of narrating calls one at a time: call_tool(name, **args) invokes another chat tool for real and returns its actual result; loop, filter, join, and aggregate in code; emit(value) sets the final answer; print() for working notes. Only read-only tools are callable (search/recall/duckdb_query/literature_search/code_graph/seo_audit/geo_audit etc.) - no side effects. Use for multi-step research and synthesis where every value must come from a real execution: the call trace is returned, so results are verifiable, not narrated.",CodeActInput,Risk.WRITE,codeact_handler(conversation_id,r.invoke,_codeact_allowed),timeout_seconds=timeout))
    r.register(ToolSpec("code_interpreter",'Persistent Python code interpreter for this conversation: run code with state kept across calls (variables, imports, files in its private working directory), reset the session, or save a file the session wrote into the file store for download. Sandboxed: scrubbed environment, resource limits, per-call timeout. Use for data analysis, calculations, file processing, and multi-step computational work.',InterpreterInput,Risk.WRITE,code_interpreter_handler(conversation_id),timeout_seconds=timeout))
    r.register(ToolSpec("exact_solve","Solve exact-procedure tasks with code instead of in-head simulation (reasoning models collapse on long exact traces - Apple's Illusion of Thinking, arXiv:2506.06941). Use for puzzles, long arithmetic, state tracking, multi-step derivations: pass a small Python solver that computes and self-verifies, prints STATUS + ANSWER; a solver proving infeasibility reports UNSOLVABLE. Returns only the verified result plus a short digest.",ExactSolveInput,Risk.WRITE,exact_solve,timeout_seconds=timeout))
    r.register(ToolSpec("story_critique","Critique a fiction draft against the documented AI-narrative defaults (StoryScope, COLM 2026): stated themes, tidy endings, linear time, single-track plots, clean heroes, bodily emotion, vague references, flat escalation, debate dialogue, sealed narration. Returns per-check ai/human/mixed verdicts with evidence and fixes.",StoryCritiqueInput,Risk.READ,story_critique_handler(_resolve_llm),timeout_seconds=timeout))
