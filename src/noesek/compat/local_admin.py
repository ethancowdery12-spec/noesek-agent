"""Permission-safe local stores for Hermes-compatible administrative CLI groups."""
from __future__ import annotations
import hashlib,json,os,re,shutil,sqlite3,time
from pathlib import Path
NAME=re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')
def home():
 p=Path(os.environ.get('NOESEK_HOME','~/.noesek')).expanduser();p.mkdir(parents=True,exist_ok=True,mode=0o700);return p
def _read(name,default):
 p=home()/name
 try:return json.loads(p.read_text())
 except (OSError,json.JSONDecodeError):return default
def _write(name,data):
 p=home()/name;t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n');t.chmod(0o600);os.replace(t,p)
def mcp_list():
 d=_read('mcp.json',{});return [{**{'name':k},**{x:y for x,y in v.items() if x not in {'headers','env','client_secret'}}} for k,v in sorted(d.items())]
def mcp_get(name):return _read('mcp.json',{}).get(name)
def mcp_add(name,*,url=None,command=None,args=None,auth=None,timeout=None,env=None):
 if not NAME.fullmatch(name):raise ValueError('invalid MCP server name')
 if bool(url)==bool(command):raise ValueError('choose exactly one of --url or --command')
 d=_read('mcp.json',{});d[name]={'transport':'http' if url else 'stdio','target':url or ' '.join([command,*list(args or [])]),'auth':auth,'connect_timeout':timeout,'env_refs':sorted(x.split('=',1)[0] for x in (env or []) if '=' in x),'allowed_tools':[],'enabled':False};_write('mcp.json',d);return mcp_get(name)
def mcp_remove(name):
 d=_read('mcp.json',{});ok=d.pop(name,None) is not None;_write('mcp.json',d);return ok
def mcp_status(name):
 row=mcp_get(name)
 if not row:return None
 token=__import__('noesek.compat.mcp_device_flow',fromlist=['FileTokenStore']).FileTokenStore().status('mcp-'+name)
 return {**{k:v for k,v in row.items() if k not in {'headers','env','client_secret'}},'name':name,'token':token}
def hooks():return _read('hooks.json',[])
def hook_list():return [{k:v for k,v in x.items() if k not in {'env','secret'}} for x in hooks()]
def hook_revoke(command):
 d=_read('hook-approvals.json',{});ok=d.pop(hashlib.sha256(command.encode()).hexdigest(),None) is not None;_write('hook-approvals.json',d);return ok
def hook_doctor():
 approved=_read('hook-approvals.json',{});out=[]
 for x in hook_list():
  cmd=x.get('command','');p=Path(cmd.split()[0]).expanduser() if cmd else Path('')
  out.append({'event':x.get('event'),'command':cmd,'exists':p.is_file(),'executable':p.is_file() and os.access(p,os.X_OK),'approved':hashlib.sha256(cmd.encode()).hexdigest() in approved})
 return out
def hook_plan(event,tool=None):
 return [{**x,'would_run':False,'approval_required':True} for x in hook_list() if x.get('event')==event and (not tool or not x.get('tool') or x.get('tool')==tool)]
def secret_sources():
 refs=_read('secret-references.json',{});return {'references':{k:{'source':v.get('source'),'reference':v.get('reference'),'present':bool(v.get('reference'))} for k,v in refs.items()},'values_exposed':False}
def vault_list():return _read('vault-references.json',[])
def vault_remove(handle):
 rows=vault_list();new=[x for x in rows if x.get('handle')!=handle];_write('vault-references.json',new);return len(new)!=len(rows)
def profiles():return _read('profiles.json',{'active':'default','profiles':{'default':{'description':'','provider':None,'channels':[]}}})
def profile_list():
 d=profiles();return [{'name':k,'active':k==d['active'],**v} for k,v in sorted(d['profiles'].items())]
def profile_get(name):return profiles()['profiles'].get(name)
def profile_create(name,description=''):
 if not NAME.fullmatch(name):raise ValueError('invalid profile name')
 d=profiles()
 if name in d['profiles']:raise ValueError('profile exists')
 d['profiles'][name]={'description':description or '', 'provider':None,'channels':[]};_write('profiles.json',d);return profile_get(name)
def profile_use(name):
 d=profiles()
 if name not in d['profiles']:raise LookupError(name)
 d['active']=name;_write('profiles.json',d);return name
def profile_describe(name,text):
 d=profiles()
 if name not in d['profiles']:raise LookupError(name)
 d['profiles'][name]['description']=text;_write('profiles.json',d);return d['profiles'][name]
def profile_delete(name):
 if name=='default':raise ValueError('cannot delete default profile')
 d=profiles();ok=d['profiles'].pop(name,None) is not None
 if d['active']==name:d['active']='default'
 _write('profiles.json',d);return ok
def profile_rename(old,new):
 if not NAME.fullmatch(new):raise ValueError('invalid profile name')
 d=profiles()
 if old not in d['profiles'] or new in d['profiles']:raise ValueError('source missing or target exists')
 d['profiles'][new]=d['profiles'].pop(old)
 if d['active']==old:d['active']=new
 _write('profiles.json',d);return profile_get(new)
def checkpoints(limit=20):
 root=home()/'checkpoints';rows=[]
 if root.exists():
  for p in sorted(root.iterdir(),key=lambda x:x.stat().st_mtime,reverse=True)[:limit]:rows.append({'name':p.name,'bytes':sum(x.stat().st_size for x in p.rglob('*') if x.is_file()),'modified_at':p.stat().st_mtime})
 return rows
def checkpoint_prune(days=7,max_mb=500,force=False):
 if not force:raise ValueError('checkpoint prune requires --force')
 root=home()/'checkpoints';cut=time.time()-days*86400;removed=[]
 if root.exists():
  for p in root.iterdir():
   if p.stat().st_mtime<cut:shutil.rmtree(p);removed.append(p.name)
 return {'removed':removed,'remaining':checkpoints(10000)}

def _key():
 p=home()/'operator-signing.key'
 if not p.exists():p.write_bytes(os.urandom(32));p.chmod(0o600)
 return p.read_bytes()
def _signed(kind,payload,approved=False):
 import hmac
 body={'schema':'noesek.operator-plan.v1','kind':kind,'created_at':time.time(),'approved':bool(approved),'payload':payload}
 raw=json.dumps(body,sort_keys=True,separators=(',',':')).encode();body['signature']='hmac-sha256:'+hmac.new(_key(),raw,hashlib.sha256).hexdigest();return body
def verify_signed(body):
 import hmac
 sig=body.get('signature','');unsigned={k:v for k,v in body.items() if k!='signature'};raw=json.dumps(unsigned,sort_keys=True,separators=(',',':')).encode()
 return hmac.compare_digest(sig,'hmac-sha256:'+hmac.new(_key(),raw,hashlib.sha256).hexdigest())
def save_plan(kind,payload,approved=False):
 body=_signed(kind,payload,approved);d=home()/'plans';d.mkdir(exist_ok=True,mode=0o700);p=d/f'{kind}-{int(time.time()*1000)}.json';p.write_text(json.dumps(body,indent=2,sort_keys=True)+'\n');p.chmod(0o600);return {'path':str(p),'digest':hashlib.sha256(p.read_bytes()).hexdigest(),'approved':body['approved'],'executed':False}
def vault_request(kind=None):
 request={'schema':'noesek.vault-request.v1','kind':kind or 'login','fields':{'login':['username','password'],'payment':['label','card'],'address':['label','address']}.get(kind or 'login',[]),'accepts_secret_on_cli':False}
 return save_plan('vault-request',request,False)
def password_manager_status(name):return {'name':name,'interface':'reference-resolver','configured':False,'dry_run':True,'values_exposed':False,'required_reference_scheme':'op://' if name=='onepassword' else 'bws://'}
def profile_export(name,output):
 row=profile_get(name)
 if not row:raise LookupError(name)
 import hmac
 payload={'schema':'noesek.profile.v1','name':name,'profile':row};raw=json.dumps(payload,sort_keys=True,separators=(',',':')).encode();payload['signature']='hmac-sha256:'+hmac.new(_key(),raw,hashlib.sha256).hexdigest();p=Path(output);p.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n');p.chmod(0o600);return str(p)
def profile_import(path,name=None):
 import hmac
 d=json.loads(Path(path).read_text());sig=d.pop('signature','');raw=json.dumps(d,sort_keys=True,separators=(',',':')).encode()
 if d.get('schema')!='noesek.profile.v1' or not hmac.compare_digest(sig,'hmac-sha256:'+hmac.new(_key(),raw,hashlib.sha256).hexdigest()):raise PermissionError('invalid profile archive signature')
 target=name or d['name'];profile_create(target,d['profile'].get('description',''));allp=profiles();allp['profiles'][target]=d['profile'];_write('profiles.json',allp);return profile_get(target)
def save_device_flow(name,state):
 # The secret device_code is stored separately with 0600; public state keeps only a reference.
 ref='device-'+hashlib.sha256((name+str(time.time())).encode()).hexdigest()[:16];secret=home()/'device-flows';secret.mkdir(exist_ok=True,mode=0o700);p=secret/f'{ref}.secret';p.write_text(json.dumps({'device_code':state.pop('device_code',None)}));p.chmod(0o600);public={**state,'name':name,'secret_ref':ref};_write(f'device-flow-{name}.json',public);return public
