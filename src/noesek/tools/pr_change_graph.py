"""Deterministic file-change graph, inspired by PR Lens (MIT), own code.
Only diff facts are shown. No guessed call/import edges or model diagram.
"""
import html
from pydantic import BaseModel,Field
from ..review.diffparse import parse_unified_diff

class PRChangeGraphInput(BaseModel):
    diff:str=Field(min_length=1,max_length=200000)

def pr_change_graph(inp):
    headers=sum(line.startswith("diff --git ") for line in inp.diff.split("\n"))
    if headers>100:return {"ok":False,"error":"more than 100 files; narrow the diff","file_count":headers}
    files=parse_unified_diff(inp.diff)
    invalid=[{"path":f.path,"errors":f.errors} for f in files if f.errors]
    if invalid:return {"ok":False,"status":"invalid_diff","errors":invalid}
    if len(files)>100:return {'ok':False,'error':'more than 100 files; narrow the diff, no partial graph returned','file_count':len(files)}
    if not files:return {'ok':False,'error':'no recognized git diff file headers'}
    nodes=[];lines=['flowchart TD']
    for i,f in enumerate(files):
        nodes.append({'id':f'f{i}','path':f.path,'old_path':f.old_path,'status':f.status,
                      'binary':f.is_binary,'added_lines':sorted(f.added_lines),'churn':f.churn})
        label=html.escape(f'{f.path} ({f.status})',quote=True).replace('\n',' ').replace('\r',' ')
        # Mermaid syntax stays outside the label; entities neutralize delimiters.
        label=label.replace('[','&#91;').replace(']','&#93;').replace('`','&#96;')
        lines.append(f'  f{i}["{label}"]')
    return {'ok':True,'nodes':nodes,'edges':[],'mermaid':'\n'.join(lines),'model_generated':False,
            'source_trust':'caller_supplied_diff','rendered':False,
            'caveat':'File-level change graph only, no semantic dependency edges. Validate the supplied diff against the actual PR and inspect a rendered diagram before delivery.'}
