"""Consent-scoped writing sample metrics, inspired by Alter (Apache-2.0).
Own code, no prompt copied. No persona, model training, storage or export.
"""
import re
from pydantic import BaseModel,Field,field_validator,StrictBool
class WritingProfileInput(BaseModel):
    samples:list[str]=Field(min_length=1,max_length=20)
    user_authorized:StrictBool=Field(default=False,description="Only true when the owner authorized using these exact samples for this purpose")
    @field_validator('samples')
    @classmethod
    def bounds(cls,value):
        if sum(len(x) for x in value)>50000:raise ValueError('samples exceed 50000 characters')
        return value

def writing_profile(inp):
    if not inp.user_authorized:return {'ok':False,'error':'owner authorization for these samples is required'}
    text='\n\n'.join(inp.samples).replace('’',"'")
    words=re.findall(r"\b[\w']+\b",text)
    if not words:return {'ok':False,'error':'no words found in supplied samples'}
    sentences=[re.findall(r"\b[\w']+\b",s) for s in re.split(r'(?<!\d)[.!?]+|[.!?]+(?!\d)',text)]
    sentences=[s for s in sentences if s]
    paragraphs=[p for p in re.split(r'\n\s*\n',text) if p.strip()]
    return {'ok':True,'sample_count':len(inp.samples),'sentence_count':len(sentences),
            'average_sentence_words':round(sum(map(len,sentences))/len(sentences),1),
            'average_paragraph_words':round(len(words)/max(1,len(paragraphs)),1),
            'question_count':text.count('?'),'exclamation_count':text.count('!'),
            'contraction_count':sum(bool(re.search(r"(?i)(?:n't|'(?:re|ve|ll|d|m))$",w)) for w in words),
            'authorization_trust':'caller_assertion_not_verified',
            'trained_model':False,'saved':False,'profile_is_instruction':False,
            'caveat':'Metrics describe only the supplied sample. They do not establish identity, preferences, consent, or a complete writing voice. Drafts still need owner review.'}
