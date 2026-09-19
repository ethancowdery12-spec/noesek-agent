#!/usr/bin/env python3
"""Static, reproducible inventory of a pinned Hermes argparse and slash-command surface."""
from __future__ import annotations
import ast, hashlib, json, os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; UP=Path(os.environ.get('HERMES_SOURCE',ROOT.parent/'hermes-agent'))
FILES=[UP/'hermes_cli/_parser.py',*sorted((UP/'hermes_cli/subcommands').glob('*.py')),UP/'hermes_cli/send_cmd.py',UP/'hermes_cli/portal_cli.py',UP/'hermes_cli/projects_cmd.py',UP/'hermes_cli/vault.py',UP/'hermes_cli/proxy_cli.py',UP/'hermes_cli/bundles.py',UP/'hermes_cli/checkpoints.py',UP/'hermes_cli/curator.py',UP/'hermes_cli/pets.py',UP/'hermes_cli/journey.py',UP/'hermes_cli/kanban_parser.py']
ROOT_HINT={'send_cmd':'send','portal_cli':'portal','projects_cmd':'project','vault':'vault','proxy_cli':'proxy','bundles':'bundles','checkpoints':'checkpoints','curator':'curator','pets':'pets','journey':'journey','kanban_parser':'kanban'}
def val(n,env):
 try:return ast.literal_eval(n)
 except: pass
 if isinstance(n,ast.Name): return env.get(n.id)
 if isinstance(n,(ast.List,ast.Tuple,ast.Set)): return [val(x,env) for x in n.elts]
 if isinstance(n,ast.UnaryOp) and isinstance(n.op,ast.USub):
  x=val(n.operand,env); return -x if isinstance(x,(int,float)) else None
 return None
def name(c): return c.func.attr if isinstance(c.func,ast.Attribute) else c.func.id if isinstance(c.func,ast.Name) else ''
def base(c): return c.func.value.id if isinstance(c.func,ast.Attribute) and isinstance(c.func.value,ast.Name) else None
def kw(c,env): return {x.arg:val(x.value,env) for x in c.keywords if x.arg}
def add_option(entries,target,c,env,args=None):
 flags=[val(x,env) for x in (args if args is not None else c.args)]; flags=[x for x in flags if isinstance(x,str)]
 if not flags:return
 d=kw(c,env); safe={k:v for k,v in d.items() if k in {'action','nargs','const','default','choices','required','metavar','dest','help'} and v is not None}
 entries.setdefault(target,{'help':'','options':[]})['options'].append({'flags':flags,**safe})
entries={():{'help':'Hermes Agent - AI assistant with tool-calling capabilities','options':[]}}; provenance=[]
for f in FILES:
 if not f.exists():continue
 raw=f.read_bytes(); provenance.append({'path':str(f.relative_to(UP)),'sha256':hashlib.sha256(raw).hexdigest()}); tree=ast.parse(raw)
 globalenv={}
 for n in tree.body:
  if isinstance(n,(ast.Assign,ast.AnnAssign)):
   names=[x.id for x in n.targets if isinstance(x,ast.Name)] if isinstance(n,ast.Assign) else ([n.target.id] if isinstance(n.target,ast.Name) else [])
   x=val(n.value,globalenv)
   if x is not None:
    for a in names:globalenv[a]=x
 root=(ROOT_HINT[f.stem],) if f.stem in ROOT_HINT else ()
 funcs=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
 for fn in funcs:
  env=dict(globalenv); parsers={}
  for a in fn.args.args:
   if 'subparser' in a.arg: parsers[a.arg]=root
   elif a.arg in {'parser','parent','p','subparser'}: parsers[a.arg]=root
  if fn.name in {'_add_top_level_flags'}: parsers['parser']=()
  if fn.name=='_build_chat_parser': parsers['subparsers']=()
  # repeated fixed-point discovers assigned parser/subparser variables
  for _ in range(8):
   changed=False
   for n in ast.walk(fn):
    if not isinstance(n,ast.Assign) or not isinstance(n.value,ast.Call):continue
    vars=[x.id for x in n.targets if isinstance(x,ast.Name)]; c=n.value; op=name(c); b=base(c)
    if op in {'add_subparsers','add_mutually_exclusive_group'} and b in parsers:
     for v in vars:
      if v not in parsers:parsers[v]=parsers[b];changed=True
    elif op=='add_parser' and b in parsers and c.args:
     nm=val(c.args[0],env)
     if isinstance(nm,str):
      path=parsers[b]+(nm,); d=kw(c,env); entries.setdefault(path,{'help':d.get('help') or d.get('description') or '','options':[]})
      if d.get('aliases'):entries[path]['aliases']=d['aliases']
      for v in vars:
       if parsers.get(v)!=path:parsers[v]=path;changed=True
   if not changed:break
  for n in ast.walk(fn):
   if isinstance(n,ast.Call) and name(n)=='add_parser' and base(n) in parsers and n.args:
    nm=val(n.args[0],env)
    if isinstance(nm,str):
     path=parsers[base(n)]+(nm,);d=kw(n,env);entries.setdefault(path,{'help':d.get('help') or d.get('description') or '','options':[]})
     if d.get('aliases'):entries[path]['aliases']=d['aliases']
  for n in ast.walk(fn):
   if not isinstance(n,ast.Call):continue
   op=name(n); b=base(n); target=parsers.get(b); args=n.args
   if op in {'_inherited_flag','inherited','add_json_flag','add_yes_flag','add_accept_hooks_flag'} and args and isinstance(args[0],ast.Name) and args[0].id in parsers:target=parsers[args[0].id];args=args[1:]
   if op in {'add_argument','_inherited_flag','inherited','add_json_flag','add_yes_flag','add_accept_hooks_flag'} and target is not None:add_option(entries,target,n,env,args)
# De-duplicate identical flags caused by helper wrappers being seen twice.
for e in entries.values():
 seen=set(); out=[]
 for o in e['options']:
  key=tuple(o['flags'])
  if key not in seen:seen.add(key);out.append(o)
 e['options']=out
cmd=UP/'hermes_cli/commands.py'; raw=cmd.read_bytes(); provenance.append({'path':'hermes_cli/commands.py','sha256':hashlib.sha256(raw).hexdigest()}); slash=[]
for n in ast.walk(ast.parse(raw)):
 if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='CommandDef' and n.args:
  nm=val(n.args[0],{}); desc=val(n.args[1],{}) if len(n.args)>1 else ''
  if isinstance(nm,str):
   row={'name':nm,'description':desc or ''}
   for x in n.keywords:
    if x.arg in {'aliases','args_hint','subcommands','cli_only','gateway_only','busy_policy'}:row[x.arg]=val(x.value,{})
   slash.append(row)
man={'schema':1,'upstream':{'repository':'https://github.com/NousResearch/hermes-agent','commit':'c712f06dcdd24053a4118f38d2090ac53137ecfc','license':'MIT','license_sha256':hashlib.sha256((UP/'LICENSE').read_bytes()).hexdigest(),'copyright':'Copyright (c) 2025 Nous Research'},'files':provenance,'commands':[{'path':list(p),**e} for p,e in sorted(entries.items())],'slash_commands':slash}
out=ROOT/'compat/hermes-cli-manifest.json';out.parent.mkdir(exist_ok=True);out.write_text(json.dumps(man,indent=2,sort_keys=True)+'\n');print(f'{len(entries)-1} command paths; {sum(len(e["options"]) for e in entries.values())} options; {len(slash)} slash commands')
