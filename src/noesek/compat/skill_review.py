from dataclasses import dataclass,asdict,field
import uuid
@dataclass
class SkillProposal:
    name:str; content:str; evidence:list[str]; proposal_id:str=field(default_factory=lambda:str(uuid.uuid4())); state:str="pending"
    def __post_init__(self):
        if not self.name or not self.content.strip() or not self.evidence: raise ValueError("name, content and evidence are required")
    def decide(self,approved:bool,reviewer:str):
        if self.state!="pending" or not reviewer: raise ValueError("proposal is not reviewable")
        self.state="approved" if approved else "rejected"; return asdict(self)
