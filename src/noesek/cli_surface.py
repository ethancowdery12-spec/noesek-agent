"""Noesek Agent command surface over the thin-controller runtime.

The command grammar is generated from the pinned upstream manifest (see
THIRD_PARTY_NOTICES.md for attribution). Execution stays in Noesek: this
module never imports the upstream agent loop.
"""
from __future__ import annotations
import argparse, asyncio, json, os, sys
from pathlib import Path
from . import __version__
MANIFEST=Path(__file__).resolve().parent/"data/cli-manifest.json"
UNSUPPORTED=3

def _manifest(): return json.loads(MANIFEST.read_text())
def _dest(flags):
    opts=[x for x in flags if x.startswith('-')]
    return (max(opts,key=len).lstrip('-').replace('-','_') if opts else flags[0].replace('-','_'))
def _add(p,row):
    flags=row['flags']; kw={}
    for key in ('help','metavar','required','const','default','choices','nargs'):
        if key in row and row[key] is not None: kw[key]=row[key]
    action=row.get('action')
    if isinstance(action,str) and action in {'store_true','store_false','append','count','store_const'}:kw['action']=action
    if any(x.startswith('-') for x in flags): kw.setdefault('dest',row.get('dest') or _dest(flags))
    else:
        # Static extraction cannot always recover a computed nargs; permissive parsing is
        # intentional for contract-only adapters, while concrete adapters validate inputs.
        kw.setdefault('nargs',row.get('nargs','?'))
    if kw.get('nargs') in (0,None):kw.pop('nargs',None)
    try:p.add_argument(*flags,**kw)
    except (argparse.ArgumentError,TypeError,ValueError):
        # Upstream sometimes repeats an inherited option. First declaration wins, like
        # the effective namespace in the upstream CLI.
        pass

def build_parser():
    m=_manifest(); root=argparse.ArgumentParser(prog='noesek',description='Noesek Agent CLI - interactive terminal UI and full command surface.',formatter_class=argparse.RawDescriptionHelpFormatter)
    root.add_argument('--compat-report',action='store_true',help='Print command-surface manifest summary and exit')
    by={tuple(x['path']):x for x in m['commands']}
    for o in by.get((),{}).get('options',[]):_add(root,o)
    subs={():root.add_subparsers(dest='command',metavar='<command>')}; parsers={():root}
    for path,row in sorted(by.items(),key=lambda kv:(len(kv[0]),kv[0])):
        if not path:continue
        parent=path[:-1]
        if parent not in subs:
            pp=parsers[parent];subs[parent]=pp.add_subparsers(dest='command_'+('_'.join(parent) or 'root'))
        kwargs={'help':row.get('help') or argparse.SUPPRESS,'description':row.get('help') or None}
        aliases=[a for a in row.get('aliases',[]) if isinstance(a,str)]
        if aliases:kwargs['aliases']=aliases
        try:p=subs[parent].add_parser(path[-1],**kwargs)
        except argparse.ArgumentError:continue
        parsers[path]=p
        for o in row.get('options',[]):_add(p,o)
        p.set_defaults(_cmd_path=path)
        if any(x[:-1]==path for x in by):subs[path]=p.add_subparsers(dest='command_'+'_'.join(path))
    root.add_argument('--output-format',choices=['text','json','stream-json'],default='text',
                      help='Machine output format for one-shot (-z) and chat queries')
    if ('chat',) in parsers:
        parsers[('chat',)].add_argument('--oneshot',action='store_true',help='Run one query and exit (requires --query)')
    if ('sessions','delete') in parsers:
        parsers[('sessions','delete')].add_argument('--yes',action='store_true',help='Confirm deletion')
    if ('pairing',) in subs:
        pp=subs[('pairing',)].add_parser('pending',help='List pending pairing requests')
        pp.add_argument('--platform',default=None)
        pp.set_defaults(_cmd_path=('pairing','pending'))
    ex=subs[()]
    def _extra(name,**kw):
        ep=ex.add_parser(name,**kw);ep.set_defaults(_noesek_extra=name);return ep
    _extra('worker',help='Run only the background task worker')
    _extra('acp-serve',help='Serve the Noesek ACP agent over stdio')
    _extra('providers',help='List provider protocols and availability')
    mem=_extra('memories',help='Local memory operations (offline)')
    ms=mem.add_subparsers(dest='memories_command')
    mse=ms.add_parser('search');mse.add_argument('query');mse.add_argument('--limit',type=int,default=20)
    inc=_extra('incidents',help='Cron incident review (offline)')
    incs=inc.add_subparsers(dest='incidents_command')
    incs.add_parser('list')
    ipm=incs.add_parser('postmortem');ipm.add_argument('incident_id');ipm.add_argument('--output',type=Path,default=None)
    return root

def _extras(args):
    cmd=getattr(args,'_noesek_extra',None)
    if cmd is None:return None
    as_json=bool(getattr(args,'json',False))
    from . import cli_ops
    if cmd=='worker':
        from .cli import _worker;asyncio.run(_worker());return 0
    if cmd=='acp-serve':
        from .compat.acp_server import main as f;f();return 0
    if cmd=='providers':
        from .compat.providers import list_providers;_emit(list_providers(),as_json);return 0
    if cmd=='memories':
        if getattr(args,'memories_command',None)=='search':
            from .core.memory_search import search_memories
            _emit(asyncio.run(search_memories(args.query,args.limit)),as_json);return 0
    if cmd=='incidents':
        sub=getattr(args,'incidents_command',None)
        from cron import incidents as _inc
        if sub=='list' or sub is None:_emit(_inc.list_incidents(),as_json);return 0
        if sub=='postmortem':
            row=_inc.get_incident(args.incident_id)
            if row is None:return 2
            text=json.dumps(row,indent=2,sort_keys=True)
            if args.output:args.output.write_text(text);_emit({'output':str(args.output)},as_json)
            else:print(text)
            return 0
    return 2

def _emit(v,as_json=False):
    if as_json:print(json.dumps(v,sort_keys=True,ensure_ascii=False))
    elif isinstance(v,(dict,list)):print(json.dumps(v,indent=2,sort_keys=True,ensure_ascii=False))
    else:print(v)
def _compat_report(m):
    return {'upstream':m['upstream'],'command_paths':len(m['commands'])-1,'options':sum(len(x['options']) for x in m['commands']),'slash_commands':len(m['slash_commands']),'execution':'Noesek adapters; the upstream agent core is not imported'}
def _unsupported(path):
    print(f"noesek: {' '.join(path)} is parsed exactly but has no safe execution adapter yet",file=sys.stderr)
    print("This command did not run. See docs/CLI_SURFACE.md.",file=sys.stderr);return UNSUPPORTED

def _roots(kind):
    home=Path(os.environ.get('NOESEK_HOME','~/.noesek')).expanduser()
    return [home/kind,Path.cwd()/kind]

def _cron(args,path,as_json):
    from cron import jobs, executions, incidents, notepad
    action=path[1] if len(path)>1 else 'list'
    ref=getattr(args,'job_id',None)
    if action=='list':_emit(jobs.list_jobs(include_disabled=True),as_json);return 0
    if action=='create':
        row=jobs.create_job(getattr(args,'prompt',None),getattr(args,'schedule',None),name=getattr(args,'name',None),repeat=getattr(args,'repeat',None),deliver=getattr(args,'deliver',None),skill=getattr(args,'skill',None),model=getattr(args,'model',None),provider=getattr(args,'provider',None),script=getattr(args,'script',None),workdir=getattr(args,'workdir',None),monitor_script=getattr(args,'monitor_script',None),monitor_url=getattr(args,'monitor_url',None),reasoning_effort=getattr(args,'reasoning_effort',None),failure_deliver=getattr(args,'failure_deliver',None),paused=bool(getattr(args,'paused_reason',None)),paused_reason=getattr(args,'paused_reason',None));_emit(row,as_json);return 0
    if action=='pause':row=jobs.pause_job(ref);_emit(row,as_json);return 0 if row else 2
    if action=='resume':row=jobs.resume_job(ref);_emit(row,as_json);return 0 if row else 2
    if action=='run':row=jobs.trigger_job(ref);_emit(row,as_json);return 0 if row else 2
    if action=='remove':_emit({'removed':jobs.remove_job(ref)},as_json);return 0
    if action=='runs':_emit(executions.list_executions(job_id=ref,limit=getattr(args,'limit',50) or 50),as_json);return 0
    if action=='incidents':
        ia=getattr(args,'incident_action',None);iid=getattr(args,'incident_id',None)
        if ia=='ack':_emit({'acked':incidents.ack_incident(iid)},as_json)
        elif ia=='close':_emit({'closed':incidents.set_incident_state(iid,'closed')},as_json)
        elif ia=='show':_emit(incidents.get_incident(iid),as_json)
        else:_emit(incidents.list_incidents(getattr(args,'state',None)),as_json)
        return 0
    if action=='notepad':
        na=getattr(args,'notepad_action',None);key=getattr(args,'key',None);value=getattr(args,'value',None)
        if na=='set':_emit(notepad.set_note(ref,key,value),as_json)
        elif na in {'rm','remove','delete'}:_emit({'deleted':notepad.delete_note(ref,key)},as_json)
        elif na=='get':_emit(notepad.get_note(ref,key),as_json)
        elif na=='clear':_emit({'cleared':notepad.clear_notepad(ref)},as_json)
        else:_emit(notepad.list_notes(ref),as_json)
        return 0
    if action=='resnap':
        _emit(jobs.resnapshot_all_unpinned() if getattr(args,'all',False) else jobs.resnapshot_job(ref),as_json);return 0
    return _unsupported(path)

def _run(args):
    path=tuple(getattr(args,'_cmd_path',()) or ())
    as_json=bool(getattr(args,'json',False)); from . import cli_ops
    if path==('status',):_emit(asyncio.run(cli_ops.status_report()),as_json);return 0
    if path==('doctor',):
        r=cli_ops.doctor_report();_emit(r,as_json);return 0 if r['ok'] else 1
    if path in {('prompt-size',),('prompt_size',)}:_emit(cli_ops.prompt_size_report(),as_json);return 0
    if path==('config','show') or path==('config',):_emit(cli_ops.config_snapshot(),as_json);return 0
    if path==('config','path'):_emit(str(Path(os.environ.get('NOESEK_HOME','~/.noesek')).expanduser()/'config.yaml'));return 0
    if path==('sessions','list'):_emit(asyncio.run(cli_ops.sessions_list(getattr(args,'limit',20) or 20)),as_json);return 0
    if path==('sessions','export'):
        sid=getattr(args,'session_id',None);out=Path(getattr(args,'output',None) or f'noesek-session-{sid}.json')
        _emit({'messages':asyncio.run(cli_ops.session_export(int(sid),out)),'output':str(out)},as_json);return 0
    if path==('sessions','delete'):
        if not getattr(args,'yes',False):
            print('noesek: sessions delete requires --yes',file=sys.stderr);return 2
        sid=int(getattr(args,'session_id'));asyncio.run(cli_ops.session_delete(sid));_emit({'deleted':sid},as_json);return 0
    if path==('config','get'):_emit(cli_ops.config_get(getattr(args,'key')),as_json);return 0
    if path and path[0]=='cron':return _cron(args,path,as_json)
    if path in {('skills',),('skills','list')}:
        from .compat.skills import discover_skills;_emit(discover_skills(_roots('skills')),as_json);return 0
    if path in {('plugins',),('plugins','list')}:
        from .compat.plugins import discover_plugins;_emit(discover_plugins(_roots('plugins')),as_json);return 0
    if path==('plugins','show'):
        from .compat.plugins import discover_plugins
        rows=[x for x in discover_plugins(_roots('plugins')) if x['name']==getattr(args,'name')];_emit(rows[0] if rows else None,as_json);return 0 if rows else 2
    if path==('plugins','capabilities'):
        from .compat.plugins import discover_plugins
        rows=[x for x in discover_plugins(_roots('plugins')) if x['name']==getattr(args,'name')];_emit(rows[0]['capabilities'] if rows else [],as_json);return 0 if rows else 2
    if path in {('tools',),('tools','list')}:
        from .core.controller import Controller;_emit(Controller().registry(0).schemas(),as_json);return 0
    if path and path[0]=='mcp':
        from .compat import local_admin as a;act=path[1] if len(path)>1 else 'list'
        if act in {'list','picker','catalog'}:_emit(a.mcp_list(),as_json);return 0
        if act=='add':_emit(a.mcp_add(getattr(args,'name'),url=getattr(args,'url',None),command=getattr(args,'mcp_command',None),args=getattr(args,'args',[]),auth=getattr(args,'auth',None),timeout=getattr(args,'connect_timeout',None),env=getattr(args,'env',[])),as_json);return 0
        if act=='remove':_emit({'removed':a.mcp_remove(getattr(args,'name'))},as_json);return 0
        if act in {'configure','test'}:_emit(a.mcp_status(getattr(args,'name')),as_json);return 0 if a.mcp_get(getattr(args,'name')) else 2
        if act in {'login','reauth'}:
            name=getattr(args,'name',None)
            if not name or getattr(args,'all',False):return _unsupported(path)
            row=a.mcp_get(name)
            if not row:return 2
            if (getattr(args,'flow',None) or 'device')!='device':return _unsupported(path)
            cfg=row.get('device_flow') or {}
            if not all(cfg.get(x) for x in ('device_authorization_url','token_url','client_id')):print('MCP server has no device-flow endpoints configured',file=sys.stderr);return 2
            from .compat.mcp_device_flow import DeviceFlowClient,DeviceFlowConfig,FileTokenStore
            flow=DeviceFlowClient(DeviceFlowConfig(cfg['device_authorization_url'],cfg['token_url'],cfg['client_id'],cfg.get('scopes',[])),FileTokenStore())
            public=asyncio.run(flow.begin());public.update({'name':name,'state':'awaiting_user','token_ref':'mcp-'+name});a._write(f'device-flow-{name}.json',public);_emit(public,as_json);return 0
        if act=='serve':
            from .compat.acp_server import main as f
            f();return 0
    if path and path[0]=='hooks':
        from .compat import local_admin as a;act=path[1] if len(path)>1 else 'list'
        if act=='list':_emit(a.hook_list(),as_json);return 0
        if act=='doctor':_emit(a.hook_doctor(),as_json);return 0
        if act=='revoke':_emit({'revoked':a.hook_revoke(getattr(args,'command'))},as_json);return 0
        if act=='test':_emit(a.hook_plan(getattr(args,'event'),getattr(args,'for_tool',None)),as_json);return 0
    if path and path[0] in {'secrets','vault'}:
        from .compat import local_admin as a
        if path[0]=='secrets':
            act=path[1] if len(path)>1 else None
            _emit(a.password_manager_status(act) if act in {'bitwarden','onepassword'} else a.secret_sources(),as_json);return 0
        act=path[1] if len(path)>1 else 'list'
        if act in {'list','sources'}:_emit(a.vault_list() if act=='list' else a.secret_sources(),as_json);return 0
        if act=='add':_emit(a.vault_request(getattr(args,'kind',None)),as_json);return 0
        if act=='rm':_emit({'removed':a.vault_remove(getattr(args,'handle'))},as_json);return 0
        return _unsupported(path)
    if path and path[0]=='profile':
        from .compat import local_admin as a;act=path[1] if len(path)>1 else 'list'
        if act=='list':_emit(a.profile_list(),as_json);return 0
        if act in {'show','info'}:_emit(a.profile_get(getattr(args,'profile_name')),as_json);return 0
        if act=='create':_emit(a.profile_create(getattr(args,'profile_name'),getattr(args,'description',None)),as_json);return 0
        if act=='use':_emit({'active':a.profile_use(getattr(args,'profile_name'))},as_json);return 0
        if act=='describe':
            if not getattr(args,'text',None):return _unsupported(path)
            _emit(a.profile_describe(getattr(args,'profile_name'),getattr(args,'text')),as_json);return 0
        if act=='delete':
            if not getattr(args,'yes',False):raise ValueError('profile delete requires --yes')
            _emit({'deleted':a.profile_delete(getattr(args,'profile_name'))},as_json);return 0
        if act=='rename':_emit(a.profile_rename(getattr(args,'old_name'),getattr(args,'new_name')),as_json);return 0
        if act=='export':
            name=getattr(args,'profile_name');out=getattr(args,'output',None) or f'{name}.noesek-profile.json';_emit({'output':a.profile_export(name,out)},as_json);return 0
        if act=='import':_emit(a.profile_import(getattr(args,'archive'),getattr(args,'import_name',None)),as_json);return 0
        return _unsupported(path)
    if path and path[0]=='checkpoints':
        from .compat import local_admin as a;act=path[1] if len(path)>1 else 'status'
        if act in {'status','list'}:_emit(a.checkpoints(getattr(args,'limit',20)),as_json);return 0
        if act=='prune':_emit(a.checkpoint_prune(getattr(args,'retention_days',7),getattr(args,'max_size_mb',500),getattr(args,'force',False)),as_json);return 0
    if path in {('sessions','repair'),('sessions','repair-routing'),('sessions','optimize-storage'),('sessions','clean-markers')}:
        from .db import init_db,migrate;asyncio.run(init_db());asyncio.run(migrate());_emit({'ok':True,'action':path[1],'format':'noesek.db','changes':0},as_json);return 0
    if path==('fallback',):
        from .compat.providers import list_providers
        configured=[]
        try:configured=json.loads(os.environ.get('NOESEK_LLM_FALLBACKS','[]'))
        except json.JSONDecodeError:pass
        _emit({'configured':[{k:v for k,v in x.items() if k!='api_key'} for x in configured],'available':list_providers()},as_json);return 0
    if path==('backup',):
        out=getattr(args,'output',None) or getattr(args,'path',None)
        if not out:return _unsupported(path)
        _emit({'output':str(out),'files':cli_ops.backup(Path(out))},as_json);return 0
    if path==('acp',):
        from .compat.acp_server import main as f;f();return 0
    if path==('gateway','run'):
        from .main import run;run();return 0
    if path in {('update',),('uninstall',)} or (path and path[0]=='gateway' and path[1] in {'install','uninstall','start','stop','restart','migrate','migrate-legacy'}):
        from .compat.local_admin import save_plan
        approved=bool(getattr(args,'yes',False));_emit(save_plan('-'.join(path),{'argv_path':list(path),'options':{k:v for k,v in vars(args).items() if not k.startswith('_') and k!='func'}},approved),as_json);return 0
    if path and path[0]=='pairing':
        from .channels.authorization import NoesekAuthorizationGate
        gate=NoesekAuthorizationGate()
        act=path[1] if len(path)>1 else 'list'
        if act=='approve':_emit(gate.approve_code(getattr(args,'platform'),getattr(args,'code')) or {'approved':False},as_json);return 0
        if act=='revoke':_emit({'revoked':gate.revoke(getattr(args,'platform'),getattr(args,'user_id'))},as_json);return 0
        if act=='list':_emit(gate.list_approved(getattr(args,'platform',None)),as_json);return 0
        if act=='pending':_emit(gate.pairing_store.list_pending(getattr(args,'platform',None)),as_json);return 0
        if act=='clear-pending':_emit({'cleared':gate.pairing_store.clear_pending(getattr(args,'platform',None))},as_json);return 0
        return _unsupported(path)
    if path==('cron','incidents'):
        from cron import incidents
        _emit(incidents.list_incidents(),as_json);return 0
    if path==('sessions','rename'):
        _emit(asyncio.run(cli_ops.session_rename(int(getattr(args,'session_id')),getattr(args,'title'))),as_json);return 0
    if path==('sessions','prune'):
        days=int(getattr(args,'older_than',None) or 30)
        _emit(asyncio.run(cli_ops.sessions_prune(days,yes=bool(getattr(args,'yes',False)))),as_json);return 0
    if path==('sessions','stats'):
        _emit(asyncio.run(cli_ops.sessions_store_stats()),as_json);return 0
    if path==('insights',):
        _emit(asyncio.run(cli_ops.insights_report(int(getattr(args,'days',None) or 30))),as_json);return 0
    if path==('dump',):
        _emit(asyncio.run(cli_ops.dump_report()),as_json);return 0
    if path==('logs',):
        name=getattr(args,'log_name',None)
        try:_emit(cli_ops.logs_tail(None if name in {None,'agent'} else name,int(getattr(args,'lines',50) or 50)),as_json);return 0
        except LookupError:
            print(f"noesek: log '{name}' not found under ~/.noesek/logs",file=sys.stderr);return 2
    if path==('pause',):
        _emit(cli_ops.set_paused(True,getattr(args,'reason',None)),as_json);return 0
    if path==('resume',):
        _emit(cli_ops.set_paused(False),as_json);return 0
    if path==('console',):
        return _console()
    if path and path[0]=='worktree':
        from .compat import worktree_audit
        repo=Path(getattr(args,'repo',None) or '.').resolve()
        if path[1:] in {('list',),()}:
            _emit(worktree_audit.list_worktrees(repo),as_json);return 0
        if path[1:]==('prune',):
            yes=bool(getattr(args,'yes',False))
            _emit(worktree_audit.prune(repo,dry_run=bool(getattr(args,'dry_run',False)) or not yes,yes=yes),as_json);return 0
    if path==('completion',):
        shell=getattr(args,'shell',None) or 'bash';print(_completion(shell));return 0
    if path==('chat',) or not path:
        # Preserve the upstream one-shot spellings while delegating work to Noesek's controller.
        oz=getattr(args,'oneshot',None)
        query=getattr(args,'query',None) or (oz if isinstance(oz,str) else None)
        if oz is True and not query:
            print('noesek: --oneshot requires --query',file=sys.stderr);return 2
        fmt=getattr(args,'output_format','text') or 'text'
        if not query and fmt=='text':
            from .ui import main as uimain
            return uimain(model=getattr(args,'model',None))
        from types import SimpleNamespace
        from .cli import _chat
        from .core.llm import LLMError
        ns=SimpleNamespace(user='cli-user',oneshot=True,format=fmt,query=query)
        try: asyncio.run(_chat(ns));return 0
        except LLMError as e: print(f'noesek: {e}',file=sys.stderr);return 1
    return _unsupported(path)
def _console():
    import shlex
    print(f'noesek {__version__} console. Type commands without the `noesek` prefix; exit to leave.')
    while True:
        try: line=input('noesek> ').strip()
        except (EOFError,KeyboardInterrupt): print(); return 0
        if not line: continue
        if line in {'exit','quit'}: return 0
        try: main(shlex.split(line))
        except SystemExit: pass
def _completion(shell):
    names=sorted({x['path'][0] for x in _manifest()['commands'] if x['path']}) ; words=' '.join(names)
    if shell=='fish':return f"complete -c noesek -f -a '{words}'"
    if shell=='zsh':return f"#compdef noesek\n_arguments '1:command:({words})'"
    return f"_noesek() {{ COMPREPLY=($(compgen -W '{words}' -- \"${{COMP_WORDS[1]}}\")); }}\ncomplete -F _noesek noesek"
def main(argv=None):
    effective=list(argv) if argv is not None else sys.argv[1:]
    if not effective:
        # v3 full fork: bare `noesek` boots the complete vendored upstream CLI
        # with Noesek branding (see upstream_boot). Subcommands stay on this surface.
        from .upstream_boot import main as _boot;return _boot()
    parser=build_parser();args=parser.parse_args(argv);m=_manifest()
    if getattr(args,'compat_report',False):_emit(_compat_report(m),True);return 0
    if getattr(args,'version',False):print(f'noesek {__version__}');return 0
    r=_extras(args)
    if r is not None:return r
    return _run(args)
if __name__=='__main__':raise SystemExit(main())
