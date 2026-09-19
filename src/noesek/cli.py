"""Noesek chat/worker implementations; the command surface lives in cli_surface."""
from __future__ import annotations
import argparse, asyncio, json, os, sys
from pathlib import Path
from . import __version__
from .config import settings


def _emit(value, as_json=False):
    if as_json: print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    elif isinstance(value, dict):
        for k, v in value.items(): print(f"{k}: {json.dumps(v, ensure_ascii=False) if isinstance(v,(dict,list)) else v}")
    elif isinstance(value, list):
        for row in value: print(json.dumps(row, ensure_ascii=False))
    else: print(value)


async def _conversation(user):
    from .db import Session, get_or_create_conversation, init_db, migrate
    await init_db(); await migrate()
    async with Session() as s:
        conv = await get_or_create_conversation(s, "cli", user); await s.commit(); return conv.id


async def _one_shot(args):
    from .core.controller import Controller
    cid = await _conversation(args.user)
    if args.format == "stream-json": _emit({"type":"turn.started", "conversation_id":cid}, True)
    result = await Controller().handle(cid, args.query)
    payload = {"text":result.text, "citations":result.citations, "pending_approval_id":result.pending_approval_id,
               "conversation_id":cid}
    if args.format == "stream-json":
        _emit({"type":"turn.completed", **payload}, True)
    elif args.format == "json": _emit(payload, True)
    else: print(result.text)


async def _chat(args):
    from .core.controller import Controller
    from .core.llm import LLMError
    if args.query and args.oneshot: return await _one_shot(args)
    if not args.query:
        from .ui import run_interactive
        return await run_interactive(args.user)
    cid = await _conversation(args.user); c = Controller()
    if args.query:
        try: result = await c.handle(cid, args.query); print("agent>", result.text)
        except LLMError as e: print(f"noesek: {e}", file=sys.stderr)
    print(f"noesek {__version__} local chat. Type 'approve ID', 'reject ID', 'pending', or 'quit'.")
    while True:
        try: text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt): print(); break
        if text.lower() in ("quit", "exit"): break
        if text.lower() == "pending": print("agent>", (await c.pending_approvals(cid)).text); continue
        import re
        m = re.fullmatch(r"\s*(approve|reject)\s+(\d+)\s*", text, re.I)
        if m: print("agent>", (await c.decide_approval(cid, int(m.group(2)), m.group(1).lower()=="approve")).text); continue
        try: print("agent>", (await c.handle(cid, text)).text)
        except LLMError as e: print(f"noesek: {e}", file=sys.stderr)


async def _worker():
    from .channels import outbound
    from .db import init_db, migrate
    from .jobs import task_worker
    await init_db(); await migrate(); stop = asyncio.Event()
    try: await task_worker(stop, deliver=outbound.deliver)
    except KeyboardInterrupt: stop.set()


def main(argv=None):
    from .cli_surface import main as surface_main
    return surface_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
