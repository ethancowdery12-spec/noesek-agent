"""Guardian gate (roadmap item 91 wiring; docs/GUARDIAN_EVAL.md).

Scores every proposed tool call with the fine-tuned Laya checkpoint before
execution and maps the score to a verdict:

  risk score >= deny threshold      -> hard refuse (never user-approvable)
  score inside the escalate band    -> existing approval flow
  otherwise                         -> proceeds

laya is loaded lazily inside the scorer and is never a repo dependency:
importing this package costs nothing and CI never downloads a checkpoint.
"""
