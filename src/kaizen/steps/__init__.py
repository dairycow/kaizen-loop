from dataclasses import dataclass

from kaizen.findings import FindingsResult


@dataclass
class StepOutcome:
    needs_approval: bool = False
    auto_fixable: bool = False
    findings: FindingsResult | None = None
    skipped: bool = False
    skip_remaining: bool = False
    pr_url: str = ""
