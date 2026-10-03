"""Own-code word-timed storyboard from the two supplied motion videos.
Not a renderer; it plans source-timed scenes without paid generation or
Remotion source reuse. License/cost checks precede any eventual render.
"""
import math
from pydantic import BaseModel,Field,field_validator
class WordBeat(BaseModel):
    text:str=Field(min_length=1,max_length=200)
    start:float=Field(ge=0,le=604800,allow_inf_nan=False)
    end:float=Field(ge=0,le=604800,allow_inf_nan=False)
    @field_validator('start','end',mode='before')
    @classmethod
    def no_bool(cls,value):
        if isinstance(value,bool):raise ValueError('boolean is not a timestamp')
        return value
class MotionStoryboardInput(BaseModel):
    words:list[WordBeat]=Field(min_length=1,max_length=1000)
    beats:dict[int,str]=Field(default_factory=dict)
    fps:int=Field(default=30,ge=1,le=120)
    @field_validator('beats', mode='before')
    @classmethod
    def bound_beats(cls,value):
        if not isinstance(value,dict) or len(value)>1000: raise ValueError('at most 1000 beats')
        if any(not isinstance(v,str) or not v.strip() or len(v)>500 for v in value.values()): raise ValueError('invalid beat text')
        return value
def motion_storyboard(inp):
    prior=0
    for w in inp.words:
        if w.end<=w.start or w.start<prior:return {'ok':False,'error':'word timing must be positive, ordered and non-overlapping'}
        prior=w.end
    if any(k<0 or k>=len(inp.words) for k in inp.beats):return {'ok':False,'error':'beat references an unknown word'}
    if any(not isinstance(v,str) or not v.strip() or len(v)>500 for v in inp.beats.values()):return {'ok':False,'error':'beat text must be nonblank and at most 500 characters'}
    scenes=[{'word_index':i,'word':w.text,'start_frame':math.floor(w.start*inp.fps),
             'end_frame':max(math.floor(w.start*inp.fps)+1,math.ceil(w.end*inp.fps)),
             'visual':inp.beats.get(i,'No extra graphic')} for i,w in enumerate(inp.words)]
    if any(scenes[i]['start_frame'] < scenes[i-1]['end_frame'] for i in range(1,len(scenes))):
        return {'ok':False,'error':'frame quantization collision','policy':'Separate word intervals must occupy separate frames. Lower timing density or use grouped-word scenes.'}
    return {'ok':True,'fps':inp.fps,'scenes':scenes,'rendered':False,
            'checks':['source-only numbers','reduced-motion alternative','readable safe zones','no graphic overlaps','inspect actual rendered frames','verify final word and audio duration'],
            'motion':'Keep a continuous shape where useful; natural easing, no decorative bounce. Timing follows supplied word evidence.',
            'caveat':'Storyboard only. Voice timing is caller-supplied; validate against the original audio before rendering.'}
