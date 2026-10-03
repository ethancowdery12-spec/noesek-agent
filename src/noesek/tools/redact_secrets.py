"""Secret and ID redaction for the user's own text (Noesek-authored patterns, no upstream code).
Replaces API keys, tokens, key=value secrets, bearer tokens, URL credentials, private key blocks,
US SSNs and Luhn-valid card numbers with [REDACTED:<class>]. Deterministic, no model call, no network.
Reports counts per class and never echoes a removed value. Pattern based, so it can miss unusual
formats and can over-match; read the result before sharing."""
import re
from pydantic import BaseModel,Field
from ..core.redact import redact_sensitive_text
_PEM=re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----',re.S)
_PATTERNS=[('private_key',_PEM),
 ('github_token',re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b')),
 ('aws_access_key',re.compile(r'\b(?:AKIA|ASIA)[0-9A-Z]{16}\b')),
 ('slack_token',re.compile(r'\bxox[abprs]-[A-Za-z0-9-]{10,}\b')),
 ('api_key',re.compile(r'\bsk-[A-Za-z0-9_-]{20,}\b')),
 ('jwt',re.compile(r'\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b')),
 ('ssn',re.compile(r'(?<![\d-])(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}(?![\d-])'))]
_CARD=re.compile(r'(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])')
class RedactSecretsInput(BaseModel):
    text:str=Field(min_length=1,max_length=200000,description='Text to clean of secrets before sharing')
def _luhn(d):
    s=0
    for i,c in enumerate(reversed(d)):
        n=int(c)
        if i%2:
            n*=2
            if n>9:n-=9
        s+=n
    return s%10==0
def redact_secrets(inp):
    out=inp.text;counts={}
    for cls,rx in _PATTERNS:
        out,n=rx.subn(f'[REDACTED:{cls}]',out)
        if n:counts[cls]=n
    def card(m):
        d=re.sub(r'\D','',m.group(0))
        if 13<=len(d)<=19 and _luhn(d):counts['card_number']=counts.get('card_number',0)+1;return '[REDACTED:card_number]'
        return m.group(0)
    out=_CARD.sub(card,out)
    after=redact_sensitive_text(out,force=True)
    if after!=out:
        counts['credential_pair_or_bearer']=sum(1 for a,b in zip(out.split(),after.split()) if a!=b) or 1
    return {'ok':True,'cleaned_text':after,'redacted':sum(counts.values()),'by_class':counts,'original_returned':False,'note':'Pattern based: unusual formats can be missed. Read the result before sharing.'}
