"""Evidence-coverage receipt. Own implementation of ClaudeX cross-model
review (MIT) and Reticle's pass/fail/unknown pattern (mixed FSL/Apache).
No source copied; caller claims remain unverified claims, not live proof.
"""
from typing import Literal
from pydantic import BaseModel, Field, field_validator

class CheckEvidence(BaseModel):
    name: str = Field(min_length=1,max_length=150)
    state: Literal['pass','fail','unknown']
    evidence: str = Field(min_length=1,max_length=2000)
    @field_validator('name','evidence')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():raise ValueError('nonblank evidence required')
        return value.strip()

class ReviewReceiptInput(BaseModel):
    builder: str = Field(min_length=1,max_length=100)
    reviewer: str = Field(min_length=1,max_length=100)
    expected_files: list[str] = Field(min_length=1,max_length=100)
    reviewed_files: list[str] = Field(default_factory=list,max_length=100)
    checks: list[CheckEvidence] = Field(min_length=1,max_length=30)
    @field_validator('expected_files','reviewed_files')
    @classmethod
    def bounded_files(cls,value):
        if any(not x.strip() or len(x)>500 for x in value):raise ValueError('invalid file reference')
        return [x.strip() for x in value]

def review_receipt(inp):
    missing=sorted(set(inp.expected_files)-set(inp.reviewed_files))
    pending=[c.name for c in inp.checks if c.state=='unknown']
    failed=[c.name for c in inp.checks if c.state=='fail']
    blockers=[]
    if not inp.builder.strip() or not inp.reviewer.strip() or inp.builder.strip().casefold()==inp.reviewer.strip().casefold():
        blockers.append('independent_reviewer')
    if missing:blockers.append('unreviewed_files')
    if pending:blockers.append('unknown_checks')
    return {'verdict':'fail' if failed else 'incomplete' if blockers else 'pass',
            'blockers':blockers,'files_pending':missing,'checks_pending':pending,'checks_failed':failed,
            'checks':[x.model_dump() for x in inp.checks], 'executed':False,
            'evidence_trust':'caller_supplied_unverified',
            'caveat':'A receipt checks completeness and role separation, not truth. Verify the underlying commands, screenshots and source before claiming completion.'}
