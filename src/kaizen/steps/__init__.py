from pydantic import BaseModel

from kaizen.findings import FindingsResult


class StepOutcome(BaseModel):
    findings: FindingsResult | None = None
    skipped: bool = False
    skip_remaining: bool = False
    pr_url: str = ""
