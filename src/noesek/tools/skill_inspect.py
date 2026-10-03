"""Bounded offline pattern hints. Own code, not a safety certificate.
No secret text echoed. No dependency analysis, installer or network call.
"""
import ast,re
from pydantic import BaseModel,Field
class SkillInspectInput(BaseModel):
    content:str=Field(min_length=1,max_length=100000)
    source:str=Field(default='provided text',max_length=500)
_PROBES=[
 ('download_execute','high',r'\b(?:curl|wget).{0,250}\|\s*(?:ba)?sh\b|\b(?:curl|wget).{0,200};.{0,100}(?:ba)?sh\b'),
 ('secret_access','high',r'(?:\.ssh[/\\]id_|\.aws[/\\]credentials|\.env\b|os\.environ|API[_ -]?KEY|password|session[_ -]?cookie)'),
 ('instruction_override','high',r'ignore (?:all |previous |prior )?(?:instructions|rules)|do not tell (?:the )?user|hide (?:this|the) (?:action|instruction)'),
 ('outbound_transfer','medium',r'\b(?:upload|forward|send|exfiltrate|post)\b.{0,150}https?://'),
 ('persistence','high',r'\bcrontab\b|authorized_keys|\.bashrc|\.zshrc|\.profile\b|systemctl\s+enable|launchctl\s+load|schtasks\s+/create'),
 ('reverse_shell','high',r'/dev/tcp/|\bnc\b[^;|&]{0,40}\s-e\b|\bbash\s+-i\s*>&|socket\.socket\(.{0,200}(?:dup2|subprocess)'),
 ('encoded_payload','medium',r'(?:base64\s+(?:-d|--decode)|b64decode|atob\()[^\n]{0,200}(?:\||exec|eval|sh\b)|[A-Za-z0-9+/]{200,}={0,2}'),
 ('privilege_escalation','medium',r'\bsudo\s+|chmod\s+(?:-R\s+)?(?:0?777|u\+s)\b|chown\s+root'),
 ('exfil_service','medium',r'(?:pastebin\.com|transfer\.sh|webhook\.site|requestbin|ngrok\.io|discord(?:app)?\.com/api/webhooks)'),
 ('destructive_command','high',r'\bformat\s+[a-z]:|\bDROP\s+TABLE\b'),
]
_HIDDEN=re.compile('[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]')
_BAD_CALLS={'eval','exec','compile','__import__'}
def _ast_findings(content):
    try:tree=ast.parse(content)
    except (SyntaxError,ValueError,RecursionError):return []
    out=[]
    for node in ast.walk(tree):
        if not isinstance(node,ast.Call):continue
        f=node.func;name=f.id if isinstance(f,ast.Name) else (f.attr if isinstance(f,ast.Attribute) else '')
        owner=f.value.id if isinstance(f,ast.Attribute) and isinstance(f.value,ast.Name) else ''
        if name in _BAD_CALLS and node.args and not isinstance(node.args[0],ast.Constant):
            out.append((node.lineno,'dynamic_code_execution','high'))
        elif owner=='os' and name in {'system','popen'}:out.append((node.lineno,'shell_call','medium'))
        elif owner=='subprocess' and any(k.arg=='shell' and isinstance(k.value,ast.Constant) and k.value.value is True for k in node.keywords):
            out.append((node.lineno,'shell_call','medium'))
    return out
def skill_inspect(inp):
    # Normalize continuation, whitespace and full comment lines; preserve location map.
    chars=[];locations=[]
    for number,line in enumerate(inp.content.splitlines(),1):
        if line.lstrip().startswith('#'):continue
        line=line.rstrip().removesuffix('\\')
        chars.extend(line+' ');locations.extend([number]*(len(line)+1))
    text=''.join(chars);found=[]
    for code,severity,pattern in _PROBES:
        for match in re.finditer(pattern,text,re.I):
            found.append({'code':code,'severity':severity,'line':locations[match.start()]})
            if len(found)>100:break
    for match in re.finditer(r'\brm\b([^;|&]{0,500})',text,re.I):
        args=match.group(1)
        flags=re.findall(r'(?<!\S)--?([a-z]+)\b',args,re.I)
        recursive=any(f=='recursive' or (len(f)<10 and 'r' in f) for f in flags)
        force=any(f=='force' or (len(f)<10 and 'f' in f) for f in flags)
        if recursive and force:found.append({'code':'destructive_command','severity':'high','line':locations[match.start()]})
    for number,line in enumerate(inp.content.splitlines(),1):
        if _HIDDEN.search(line):found.append({'code':'hidden_unicode','severity':'high','line':number})
    for number,code,severity in _ast_findings(inp.content):found.append({'code':code,'severity':severity,'line':number})
    found=sorted({(f['line'],f['code'],f['severity']) for f in found})
    findings=[{'line':line,'code':code,'severity':severity} for line,code,severity in found[:100]]
    return {'source':inp.source,'status':'review_required' if findings else 'no_patterns_detected',
            'findings':findings,'truncated':len(found)>100,'executed':False,'authorized_to_install':False,
            'caveat':'A bounded static pattern scan is not a safety guarantee. It does not parse every shell syntax. Inspect dependencies, permissions, destinations and the full source before installation.'}
