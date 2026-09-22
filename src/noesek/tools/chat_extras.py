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
from .code_graph import CodeGraphInput, code_graph
from .design_system import DesignInput, design_system
from .linkedin import LinkedInInput, linkedin
from .office_doc import OfficeDocInput, office_doc
from .playbook import PlaybookInput, playbook
from .naturalize import RewriteNaturalInput, rewrite_natural
from .scrub import ScrubInput, scrub_handler
from .variants import GenerateVariantsInput, generate_variants_handler


def register_chat_extras(r, conversation_id: int, controller, timeout: float) -> None:
    r.register(ToolSpec("scrub","Clean the user's own text or files of hidden metadata: strips invisible watermark characters from text, and removes EXIF/document-properties metadata from their own images, Office docs, and PDFs (PDF needs optional pypdf). Creates a -clean copy; originals untouched.",ScrubInput,Risk.WRITE,scrub_handler(conversation_id),timeout_seconds=timeout))
    r.register(ToolSpec("rewrite_natural","Rewrite the user's own AI-sounding text so it reads naturally: cuts throat-clearing and hedge stacks, removes formulaic transitions, then applies the humanizer passes; reports rhythm issues. No claim about detectors.",RewriteNaturalInput,Risk.READ,rewrite_natural,timeout_seconds=timeout))

    r.register(ToolSpec("playbook","Load a working brief for a high-value workflow: mock interview, both-sides debate, writing tutor, step-by-step teacher, structured critic. Use list to see them, load to adopt one for this conversation.",PlaybookInput,Risk.READ,playbook,timeout_seconds=timeout))
    r.register(ToolSpec("design_system","Design-system skills: list/get schema'd themes (color, type, spacing, radius tokens) and render a self-contained styled HTML deliverable (title, subtitle, sections) into the file store.",DesignInput,Risk.WRITE,design_system,timeout_seconds=timeout))
    r.register(ToolSpec("linkedin","LinkedIn via the official API: profile (who am I) or share (post text as the member, PUBLIC or CONNECTIONS). Activates only when NOESEK_LINKEDIN_ACCESS_TOKEN is set; otherwise explains setup.",LinkedInInput,Risk.WRITE,linkedin,timeout_seconds=timeout))
    r.register(ToolSpec("office_doc","Read, create, and edit Word/Excel/PowerPoint files in the agent file store through the OfficeCLI binary (view/get outline or JSON; create/add/set/remove/close). Degrades cleanly when the officecli binary is not installed.",OfficeDocInput,Risk.WRITE,office_doc,timeout_seconds=timeout))
    r.register(ToolSpec("code_graph","Answer structural questions about the Noesek codebase itself: what calls a function, what a function calls, what imports a module, a module's imports, a module outline, or repo stats. Deterministic AST analysis of the installed package.",CodeGraphInput,Risk.READ,code_graph,timeout_seconds=timeout))
    async def _resolve_llm():
        async with Session() as s:
            ov = await s.scalar(select(Conversation.model_override).where(Conversation.id == conversation_id))
        return controller._llm_for_model(ov)
    r.register(ToolSpec("generate_variants","Generate N distinct candidate versions of a creative output in parallel (names, taglines, subject lines, drafts), then pick the best with a judge pass and show the rest. Use for creative asks where one shot is a lottery.",GenerateVariantsInput,Risk.READ,generate_variants_handler(_resolve_llm),timeout_seconds=timeout))
