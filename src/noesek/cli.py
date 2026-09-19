import argparse, asyncio, json, logging, os, sys
from pathlib import Path
from . import __version__
from .config import settings


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="noesek", description="Noesek Agent - primary CLI. Bare `noesek` opens the interactive terminal UI (Hermes-compatible); `hermes` remains as a compatibility alias with the same surface.")
    p.add_argument("--version", action="version", version=f"noesek {__version__}")
    p.add_argument("--json", action="store_true", help="Emit machine-readable JSON where supported")
    sub = p.add_subparsers(dest="command")
    sub.add_parser("serve", help="Run the webhook server")
    chat = sub.add_parser("chat", help="Interactive or one-shot local chat")
    chat.add_argument("-q", "--query"); chat.add_argument("--oneshot", action="store_true")
    chat.add_argument("--format", choices=("text", "json", "stream-json"), default="text")
    chat.add_argument("--user", default="local-user", help="Stable local conversation key")
    sub.add_parser("worker", help="Run only the background task worker")
    sub.add_parser("acp-serve", help="Serve the Noesek ACP agent over stdio")
    sub.add_parser("migrate", help="Apply in-place schema upgrades")
    sub.add_parser("status", help="Show runtime state without secrets")
    sub.add_parser("doctor", help="Diagnose local configuration and dependencies")
    cfg = sub.add_parser("config", help="Inspect effective configuration with secrets redacted")
    cfg.add_argument("name", nargs="?")
    ses = sub.add_parser("sessions", help="List, export, or delete conversation sessions")
    ss = ses.add_subparsers(dest="sessions_command")
    ls = ss.add_parser("list"); ls.add_argument("--limit", type=int, default=20)
    ex = ss.add_parser("export"); ex.add_argument("session_id", type=int); ex.add_argument("--output", type=Path, required=True)
    de = ss.add_parser("delete"); de.add_argument("session_id", type=int); de.add_argument("--yes", action="store_true")
    sub.add_parser("prompt-size", help="Show prompt and tool-schema byte sizes")
    sub.add_parser("providers", help="List provider protocols and availability")
    sk = sub.add_parser("skills", help="Discover inert SKILL.md packages")
    sk.add_argument("--root", action="append", type=Path, default=[])
    pl = sub.add_parser("plugins", help="Inspect plugin manifests without importing code")
    pl.add_argument("--root", action="append", type=Path, default=[])
    mem = sub.add_parser("memories", help="Local memory operations (offline)")
    mems = mem.add_subparsers(dest="memories_command")
    mse = mems.add_parser("search"); mse.add_argument("query"); mse.add_argument("--limit", type=int, default=20)
    inc = sub.add_parser("incidents", help="Cron incident review (offline)")
    incs = inc.add_subparsers(dest="incidents_command")
    incs.add_parser("list")
    ipm = incs.add_parser("postmortem"); ipm.add_argument("incident_id"); ipm.add_argument("--output", type=Path, default=None)
    pr = sub.add_parser("pairing", help="Manage channel pairing approvals (Hermes PairingStore)")
    prs = pr.add_subparsers(dest="pairing_command")
    pra = prs.add_parser("approve"); pra.add_argument("platform"); pra.add_argument("code")
    prr = prs.add_parser("revoke"); prr.add_argument("platform"); prr.add_argument("user_id")
    prl = prs.add_parser("list"); prl.add_argument("--platform", default=None)
    prp = prs.add_parser("pending"); prp.add_argument("--platform", default=None)
    ba = sub.add_parser("backup", help="Create a local zip backup without external transmission")
    ba.add_argument("output", type=Path)
    co = sub.add_parser("completion", help="Print a shell completion script")
    co.add_argument("shell", choices=("bash", "zsh", "fish"))
    return p


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
        from .hermes_ui import run_interactive
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


def _completion(shell):
    commands="serve chat worker migrate status doctor config sessions prompt-size providers skills plugins backup completion"
    if shell == "fish": return f"complete -c noesek -f -a '{commands}'"
    if shell == "zsh": return f"#compdef noesek\n_arguments '1:command:({commands})'"
    return f"_noesek() {{ COMPREPLY=($(compgen -W '{commands}' -- \"${{COMP_WORDS[1]}}\")); }}\ncomplete -F _noesek noesek"


def main(argv=None):
    args = build_parser().parse_args(argv); logging.basicConfig(level=settings.log_level)
    from . import cli_ops
    try:
        if args.command == "serve":
            from .main import run; run()
        elif args.command == "chat":
            if args.oneshot and not args.query: raise ValueError("--oneshot requires --query")
            asyncio.run(_chat(args))
        elif args.command == "worker": asyncio.run(_worker())
        elif args.command == "acp-serve":
            from .compat.acp_server import main as _acp_main; _acp_main()
        elif args.command == "migrate":
            from .db import init_db, migrate
            asyncio.run(init_db()); asyncio.run(migrate()); print("schema up to date")
        elif args.command == "status": _emit(asyncio.run(cli_ops.status_report()), args.json)
        elif args.command == "doctor":
            report=cli_ops.doctor_report(); _emit(report, args.json)
            if not report["ok"]: return 1
        elif args.command == "config":
            if args.name:
                try:
                    _emit(cli_ops.config_get(args.name), args.json)
                except KeyError:
                    print(f"unknown config key: {args.name}", file=sys.stderr)
                    return 2
            else:
                _emit(cli_ops.config_snapshot(), args.json)
        elif args.command == "sessions":
            if args.sessions_command in (None, "list"): _emit(asyncio.run(cli_ops.sessions_list(getattr(args,"limit",20))), args.json)
            elif args.sessions_command == "export": _emit({"messages":asyncio.run(cli_ops.session_export(args.session_id,args.output)),"output":str(args.output)}, args.json)
            elif args.sessions_command == "delete":
                if not args.yes: raise ValueError("session deletion requires --yes")
                asyncio.run(cli_ops.session_delete(args.session_id)); _emit({"deleted":args.session_id}, args.json)
        elif args.command == "prompt-size": _emit(cli_ops.prompt_size_report(), args.json)
        elif args.command == "providers":
            from .compat.providers import list_providers
            _emit(list_providers(), args.json)
        elif args.command == "skills":
            from .compat.skills import discover_skills
            _emit(discover_skills(args.root), args.json)
        elif args.command == "plugins":
            from .compat.plugins import discover_plugins
            _emit(discover_plugins(args.root), args.json)
        elif args.command == "pairing":
            from .channels.authorization import NoesekAuthorizationGate
            gate = NoesekAuthorizationGate()
            if args.pairing_command == "approve":
                _emit(gate.approve_code(args.platform, args.code) or {"approved": False}, args.json)
            elif args.pairing_command == "revoke":
                _emit({"revoked": gate.revoke(args.platform, args.user_id)}, args.json)
            elif args.pairing_command == "list": _emit(gate.list_approved(args.platform), args.json)
            elif args.pairing_command == "pending": _emit(gate.pairing_store.list_pending(args.platform), args.json)
        elif args.command == "memories":
            from .core.memory_search import search_memories
            if args.memories_command == "search":
                _emit(asyncio.run(search_memories(args.query, args.limit)), args.json)
        elif args.command == "incidents":
            from .vendor.hermes.cron import incidents as _inc
            if args.incidents_command == "list": _emit(_inc.list_incidents(), args.json)
            elif args.incidents_command == "postmortem":
                try:
                    text = cli_ops.postmortem(args.incident_id)
                except KeyError:
                    print(f"unknown incident: {args.incident_id}", file=sys.stderr)
                    return 2
                if args.output:
                    args.output.write_text(text); _emit({"output": str(args.output)}, args.json)
                else:
                    print(text, end="")
        elif args.command == "backup": _emit({"output":str(args.output),"files":cli_ops.backup(args.output)}, args.json)
        elif args.command == "completion": print(_completion(args.shell))
        elif args.command is None:
            from .hermes_ui import run_interactive
            asyncio.run(run_interactive("cli-user"))
        else: build_parser().print_help()
        return 0
    except (KeyError, LookupError, ValueError) as e:
        print(f"noesek: {type(e).__name__}: {e}", file=sys.stderr); return 2
    except Exception as e:
        from .core.llm import LLMError
        if isinstance(e, LLMError):
            print(f"noesek: {e}", file=sys.stderr); return 1
        raise

if __name__ == "__main__": raise SystemExit(main())
