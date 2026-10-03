"""Rule-based checker for answers written for a reader who needs the next action first.
Idea from the MIT i-have-adhd skill (lead with the action, number the steps, end with one next
action, no tangents, specific time estimates, restate progress); rules and wording are our own.
Pure text analysis: no model call, no rewrite, no claim about the reader. Hints are heuristics.
"""
import re
from pydantic import BaseModel,Field
_OPENERS=('great question','good question','let me think','let me explain','sure','certainly','absolutely','of course',"i'd be happy","i would be happy",'happy to help','thanks for asking','so,','well,','ok so','okay so')
_CLOSERS=('hope this helps','hope that helps','let me know if','feel free to','don\'t hesitate','happy to help further','anything else')
_SEQUENCE=re.compile(r'\b(first|second|third|then|next|after that|afterwards|finally|lastly)\b',re.I)
_TANGENT=re.compile(r'\b(by the way|on another note|unrelated|side note|while we\'re at it|also worth mentioning|as an aside)\b',re.I)
_VAGUE_TIME=re.compile(r'\b(a bit|a while|a little while|shortly|soon|quickly|in no time|a few (?:hours|days|weeks)|some time)\b',re.I)
_VERBS=('run','open','edit','replace','add','remove','delete','create','install','copy','paste','click','go','set','change','check','use','type','save','restart','start','stop','read','write','call','send','ask','pick','choose','try','fix','update','rename','move','commit','push','pull','build','test','deploy','look','add','save','press','select','enable','disable')
_STATE=re.compile(r'(step\s+\d+\s+of\s+\d+|\d+\s*/\s*\d+\s+done|done:|so far:|where we are:)',re.I)

class AnswerShapeInput(BaseModel):
    text:str=Field(min_length=1,max_length=20000)
    multi_turn:bool=False

def _lines(text):return [l for l in text.splitlines() if l.strip()]
def _is_action(line):
    s=line.strip().lstrip('-*>0123456789.) ').strip().lower()
    if line.strip().startswith(('`','$','>')) or re.match(r'^\d+[.)]\s',line.strip()):return True
    if s.startswith('next:') or s.startswith('first action:'):return True
    return bool(re.match(r'^('+'|'.join(_VERBS)+r')\b',s))

def answer_shape(inp):
    lines=_lines(inp.text);text=inp.text;low=text.lower();findings=[]
    def add(rule,detail,fix):findings.append({'rule':rule,'detail':detail,'fix':fix})
    first=lines[0].strip();fl=first.lower()
    if fl.startswith(_OPENERS):add('lead_with_action',f'opens with filler: "{first[:60]}"','Make the first line something the reader can do.')
    elif not _is_action(first):add('lead_with_action','first line is not an action, command or path','Put the command, path or first step on line 1; explain after.')
    numbered=sum(1 for l in lines if re.match(r'^\s*\d+[.)]\s',l))
    seq=len(_SEQUENCE.findall(text))
    if seq>=3 and numbered<2:add('number_steps',f'{seq} sequence words but {numbered} numbered steps','Turn the sequence into a numbered list, one bounded action per line.')
    for l in lines:
        if re.match(r'^\s*\d+[.)]\s',l) and len(re.findall(r'\b(and then|then)\b',l,re.I))>=2:add('number_steps','a numbered step chains several actions with "then"','Split it into separate steps.');break
    if numbered>8:add('number_steps',f'{numbered} steps is long','Cut or fold trivial steps; a short finished path beats a complete abandoned one.')
    last=lines[-1].strip();ll=last.lower()
    if any(c in low[-300:] for c in _CLOSERS):add('end_with_next_action','ends with a pleasantry closer','Replace it with one concrete action doable in two minutes.')
    elif not (ll.startswith('next:') or _is_action(last)):add('end_with_next_action','last line is not a concrete next action','End with "Next: <one small action>".')
    if _TANGENT.search(text) and 'separately' not in low:add('suppress_tangents','mentions a side topic inline','Finish the main answer, then offer the side topic as a separate question.')
    for m in _VAGUE_TIME.finditer(text):add('specific_time',f'vague time "{m.group(0)}"','Give a number: "2 minutes", "about 1 hour".');break
    if inp.multi_turn and not _STATE.search(text):add('restate_state','no progress line in a multi-turn answer','Add "Step N of M done: ..." so the reader does not have to remember it.')
    words=len(text.split())
    return {'ok':True,'passed':not findings,'findings':findings,'rules_checked':7 if inp.multi_turn else 6,'words':words,'steps_numbered':numbered,
            'caveat':'Heuristic text checks only. Passing does not mean the answer is correct or suits a given reader.'}
