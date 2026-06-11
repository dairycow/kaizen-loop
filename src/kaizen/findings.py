from __future__ import annotations

from functools import cached_property
from typing import Literal

from pydantic import BaseModel, Field

Action = Literal["no-op", "auto-fix"]
Severity = Literal["info", "warning", "error"]
RiskLevel = Literal["low", "medium", "high"]


class Finding(BaseModel):
    id: str
    severity: Severity
    file: str = ""
    line: int = 0
    description: str = ""
    action: Action = "no-op"


class FindingsResult(BaseModel):
    items: list[Finding] = Field(default_factory=list)
    summary: str = ""
    risk_level: RiskLevel = "low"
    risk_rationale: str = ""

    @cached_property
    def has_auto_fix(self) -> bool:
        return any(f.action == "auto-fix" for f in self.items)

    @cached_property
    def auto_fix_items(self) -> list[Finding]:
        return [f for f in self.items if f.action == "auto-fix"]


def parse_findings(data: dict) -> FindingsResult:
    mapped = {
        "items": data.get("findings", []),
        "summary": data.get("summary", ""),
        "risk_level": data.get("risk_level", "low"),
        "risk_rationale": data.get("risk_rationale", ""),
    }
    return FindingsResult.model_validate(mapped)
