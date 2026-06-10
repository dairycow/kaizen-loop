from dataclasses import dataclass, field

ACTION_NOOP = "no-op"
ACTION_AUTO_FIX = "auto-fix"
ACTION_ASK_USER = "ask-user"

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_ERROR = "error"


@dataclass
class Finding:
    id: str
    severity: str
    file: str = ""
    line: int = 0
    description: str = ""
    action: str = ACTION_NOOP


@dataclass
class FindingsResult:
    items: list[Finding] = field(default_factory=list)
    summary: str = ""
    risk_level: str = "low"
    risk_rationale: str = ""

    @property
    def needs_approval(self) -> bool:
        return any(f.action == ACTION_ASK_USER for f in self.items)

    @property
    def has_auto_fix(self) -> bool:
        return any(f.action == ACTION_AUTO_FIX for f in self.items)

    @property
    def auto_fix_items(self) -> list[Finding]:
        return [f for f in self.items if f.action == ACTION_AUTO_FIX]

    @property
    def ask_user_items(self) -> list[Finding]:
        return [f for f in self.items if f.action == ACTION_ASK_USER]


def parse_findings(data: dict) -> FindingsResult:
    items = []
    for i, f in enumerate(data.get("findings", [])):
        items.append(Finding(
            id=f.get("id", f"f{i + 1}"),
            severity=f.get("severity", SEVERITY_INFO),
            file=f.get("file", ""),
            line=f.get("line", 0),
            description=f.get("description", ""),
            action=f.get("action", ACTION_NOOP),
        ))
    return FindingsResult(
        items=items,
        summary=data.get("summary", ""),
        risk_level=data.get("risk_level", "low"),
        risk_rationale=data.get("risk_rationale", ""),
    )
