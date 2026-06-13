from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property


@dataclass
class Finding:
    id: str
    severity: str
    file: str = ""
    line: int = 0
    description: str = ""
    action: str = "no-op"


@dataclass
class FindingsResult:
    items: list[Finding] = field(default_factory=list)
    summary: str = ""
    risk_level: str = "low"
    risk_rationale: str = ""

    @cached_property
    def auto_fix_items(self) -> list[Finding]:
        return [f for f in self.items if f.action == "auto-fix"]


def parse_findings(data: dict) -> FindingsResult:
    items = []
    for raw in data.get("findings", []):
        items.append(
            Finding(
                id=raw.get("id", ""),
                severity=raw.get("severity", "info"),
                file=raw.get("file", ""),
                line=raw.get("line", 0),
                description=raw.get("description", ""),
                action=raw.get("action", "no-op"),
            )
        )
    return FindingsResult(
        items=items,
        summary=data.get("summary", ""),
        risk_level=data.get("risk_level", "low"),
        risk_rationale=data.get("risk_rationale", ""),
    )
