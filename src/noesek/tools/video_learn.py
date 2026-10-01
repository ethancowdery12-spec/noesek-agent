"""Offline transcript learning pack. Own code, no fetch/install/training.
Caption event starts are not word timings. Sources never grant permission.
"""
from __future__ import annotations
import math
import re
from urllib.parse import urlparse, parse_qs
from pydantic import BaseModel, Field, field_validator
from .skill_inspect import SkillInspectInput, skill_inspect

class VideoLearnInput(BaseModel):
    video_url: str = Field(max_length=2000)
    transcript: str = Field(default="", max_length=100_000)
    caption_json: dict = Field(default_factory=dict)

    @field_validator('caption_json', mode='before')
    @classmethod
    def bounded_json(cls, value):
        if not isinstance(value, dict): raise ValueError('caption JSON must be an object')
        # Iterative and early bounded, including ignored metadata and unknown fields.
        todo=[(value,0)]; nodes=chars=0
        while todo:
            item, depth=todo.pop(); nodes+=1
            if depth>8 or nodes>30000: raise ValueError('caption JSON depth/node limit exceeded')
            if isinstance(item,dict):
                if len(item)>10000: raise ValueError('caption object too large')
                for k,v in item.items():
                    if not isinstance(k,str): raise ValueError('caption keys must be strings')
                    chars+=len(k); todo.append((v,depth+1))
            elif isinstance(item,list):
                if len(item)>10000: raise ValueError('caption list too large')
                todo.extend((v,depth+1) for v in item)
            elif isinstance(item,str): chars+=len(item)
            elif item is not None and not isinstance(item,(bool,int,float)):
                raise ValueError('caption JSON contains non-JSON values')
            if chars>200000: raise ValueError('caption JSON text limit exceeded')
        return value

def _invalid(error, **detail):
    return {'ok':False,'status':'invalid_captions','error':error,**detail,'installed':False}

def video_learn(inp: VideoLearnInput) -> dict:
    try:
        u=urlparse(inp.video_url); host=(u.hostname or '').lower(); port=u.port
        if port is not None or u.username is not None or u.password is not None: raise ValueError('unsupported URL authority')
    except ValueError: return {'ok':False,'error':'invalid YouTube URL'}
    if u.scheme not in ('https','http') or host not in ('youtu.be','youtube.com','www.youtube.com','m.youtube.com'):
        return {'ok':False,'error':'a YouTube video URL is required'}
    if host!='youtu.be' and u.path!='/watch':return {'ok':False,'error':'watch video URL required'}
    id=u.path.strip('/') if host=='youtu.be' else (parse_qs(u.query).get('v') or [''])[0]
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}',id): return {'ok':False,'error':'invalid video id'}
    url=f'https://www.youtube.com/watch?v={id}'
    events=inp.caption_json.get('events',[])
    if not isinstance(events,list) or len(events)>10000: return _invalid('events must be a bounded list')
    segments=[]; chars=0; empty=0
    for index,event in enumerate(events):
        if not isinstance(event,dict): return _invalid('event must be an object',event_index=index)
        raw=event.get('segs',[])
        if not isinstance(raw,list) or len(raw)>1000: return _invalid('segs must be a list of at most 1000 entries',event_index=index)
        parts=[]
        for seg in raw:
            if not isinstance(seg,dict) or 'utf8' not in seg or not isinstance(seg['utf8'],str):
                return _invalid('segment must contain string utf8',event_index=index)
            parts.append(seg.get('utf8',''))
        text=''.join(parts).strip()
        start=event.get('tStartMs'); seconds=None
        if start is not None:
            if isinstance(start,bool) or not isinstance(start,(int,float)) or not 0<=start<=604800000:
                return _invalid('timestamp must be finite, nonnegative milliseconds within seven days',event_index=index)
            if not math.isfinite(start): return _invalid('timestamp must be finite',event_index=index)
            seconds=start/1000
        if not text: empty+=1; continue
        chars+=len(text)+(1 if segments else 0)
        if chars>100000: return _invalid('joined caption text exceeds 100000 characters')
        segments.append({'text':text,'start_seconds':seconds,'citation':url+f'&t={int(seconds)}s' if seconds is not None else url})
    caption_text='\n'.join(s['text'] for s in segments)
    transcript=inp.transcript.strip()
    if not segments and transcript: segments=[{'text':transcript,'start_seconds':None,'citation':url}]
    if not segments: return {'ok':False,'status':'transcript_required','error':'provide actual captions or transcript; no summary may substitute'}
    # Both provided inputs are scanned, even when captions are chosen for segmentation.
    reviews=[]
    if caption_text: reviews.append(skill_inspect(SkillInspectInput(content=caption_text,source=url)))
    if transcript: reviews.append(skill_inspect(SkillInspectInput(content=transcript,source=url)))
    findings=[dict(f,input='captions' if caption_text and i==0 else 'transcript') for i,r in enumerate(reviews) for f in r['findings']]
    review={'status':'review_required' if findings else 'no_patterns_detected','findings':findings[:100],
            'truncated':len(findings)>100 or any(r['truncated'] for r in reviews),'executed':False,'authorized_to_install':False,
            'caveat':'Static pattern absence is not a safety guarantee.'}
    repos=set()
    for text in (caption_text,transcript):
        for match in re.findall(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',text):
            match=match.rstrip('.,'); match=match[:-4] if match.endswith('.git') else match
            if re.fullmatch(r'https://github\.com/[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9_][A-Za-z0-9_.-]*',match):repos.add(match)
    return {'ok':True,'video_id':id,'url':url,'segments':segments,'timestamps_available':all(s['start_seconds'] is not None for s in segments),
            'transcript_binding':'caller_supplied_unverified',
            'timing_precision':'caption_event_start_only' if caption_text else 'untimed',
            'input_coverage':{'captions':'used' if caption_text else 'no_text','transcript':'scanned_not_used_for_segments' if caption_text and transcript else 'used' if transcript else 'not_provided','empty_caption_events':empty},
            'repos':sorted(repos),'review':review,'trust':'untrusted_source','installed':False,
            'next_steps':['Verify named tools and original papers','Read source license before reuse','Write acceptance tests','Implement only owner-authorized changes','Record evidence and remaining gaps']}
