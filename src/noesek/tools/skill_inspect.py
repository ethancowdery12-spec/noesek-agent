"""Bounded offline pattern hints. Own code, not a safety certificate.
No secret text echoed. No dependency analysis, installer or network call.
"""
import re
from pydantic import BaseModel,Field
class SkillInspectInput(BaseModel):
    content:str=Field(min_length=1,max_length=100000)
    source:str=Field(default='provided text',max_length=500)
_PROBES=[
 ('download_execute','high',r'\b(?:curl|wget).{0,250}\|\s*(?:ba)?sh\b|\b(?:curl|wget).{0,200};.{0,100}(?:ba)?sh\b'),
 ('secret_access','high',r'(?:\.ssh[/\\]id_|\.aws[/\\]credentials|\.env\b|os\.environ|API[_ -]?KEY|password|session[_ -]?cookie)'),
 ('instruction_override','high',r'ignore (?:all |previous |prior )?(?:instructions|rules)|do not tell (?:the )?user|hide (?:this|the) (?:action|instruction)'),
 ('outbound_transfer','medium',r'\b(?:upload|forward|send|exfiltrate|post)\b.{0,150}https?://'),
 ('destructive_command','high',r'\bformat\s+[a-z]:|\bDROP\s+TABLE\b'),
]
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
    found=sorted({(f['line'],f['code'],f['severity']) for f in found})
    findings=[{'line':line,'code':code,'severity':severity} for line,code,severity in found[:100]]
    return {'source':inp.source,'status':'review_required' if findings else 'no_patterns_detected',
            'findings':findings,'truncated':len(found)>100,'executed':False,'authorized_to_install':False,
            'caveat':'A bounded static pattern scan is not a safety guarantee. It does not parse every shell syntax. Inspect dependencies, permissions, destinations and the full source before installation.'}
