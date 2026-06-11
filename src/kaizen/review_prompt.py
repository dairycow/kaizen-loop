from __future__ import annotations

from pydantic import BaseModel, Field

REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "severity": {"type": "string", "enum": ["info", "warning", "error"]},
                    "file": {"type": "string"},
                    "line": {"type": "integer"},
                    "description": {"type": "string"},
                    "action": {"type": "string", "enum": ["no-op", "auto-fix"]},
                },
                "required": ["id", "severity", "description", "action"],
            },
        },
        "summary": {"type": "string"},
        "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
        "risk_rationale": {"type": "string"},
    },
    "required": ["findings", "summary", "risk_level"],
}

FIX_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "changes_made": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
    },
    "required": ["changes_made", "summary"],
}


class FixOutput(BaseModel):
    changes_made: list[str] = Field(default_factory=list)
    summary: str = ""


def build_review_prompt(diff: str, intent: str = "") -> str:
    intent_section = ""
    if intent:
        intent_section = f"\n## User Intent\n\n{intent}\n"

    return (
        "You are reviewing a git diff for bugs, security issues, and code quality.\n\n"
        "## Instructions\n\n"
        "1. Analyze the diff for correctness, security, and quality\n"
        "2. For each issue classify severity (info/warning/error) and action:\n"
        "   - no-op: informational, no action needed\n"
        "   - auto-fix: mechanical fix (typos, missing error handling, dead code, obvious bugs, behavioral changes)\n"
        "3. Provide an overall risk assessment\n\n"
        "## Output\n\n"
        "Return structured output with:\n"
        "- findings: array of issues found (empty array if clean)\n"
        "- summary: one-sentence overall assessment\n"
        "- risk_level: low, medium, or high\n"
        "- risk_rationale: brief explanation of the risk level\n"
        f"{intent_section}\n"
        "## Diff\n\n"
        f"```diff\n{diff}\n```\n"
    )


def build_fix_prompt(findings_items: list[dict]) -> str:
    lines = [
        "Fix the following issues found during code review.\n",
        "Do NOT commit. Just make the code changes.\n",
    ]

    for f in findings_items:
        loc = f" ({f['file']}:{f.get('line', '?')})" if f.get("file") else ""
        lines.append(f"1. [{f['severity']}]{loc} — {f['description']} ({f['action']})")

    lines.append("\nAfter fixing, run any available tests or linters to verify.")
    lines.append("\n## Output\n\nReturn structured output with:")
    lines.append("- changes_made: array of descriptions of fixes applied")
    lines.append("- summary: one-sentence summary of fixes")

    return "\n".join(lines)
