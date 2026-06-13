from __future__ import annotations

import sys

from kaizen.agent import OpenCodeAgent
from kaizen.findings import parse_findings
from kaizen.review_prompt import REVIEW_SCHEMA, build_review_prompt
from kaizen.steps import StepOutcome


class ReviewStep:
    def name(self) -> str:
        return "review"

    def execute(
        self,
        work_dir: str,
        base_commit: str,
        head_commit: str,
        agent: OpenCodeAgent,
        intent: str = "",
        repo_dir: str | None = None,
    ) -> StepOutcome:
        from kaizen.git import get_diff

        try:
            diff = get_diff(base_commit, head_commit, work_dir)
        except RuntimeError as e:
            print(f"  Could not get diff: {e}", file=sys.stderr)
            return StepOutcome(skipped=True)

        if not diff.strip():
            print("  No diff found, skipping review")
            return StepOutcome(skipped=True)

        max_diff_size = 50000
        if len(diff) > max_diff_size:
            diff = diff[:max_diff_size] + "\n... (truncated)"

        prompt = build_review_prompt(diff, intent=intent)
        result = agent.run(prompt, work_dir, schema=REVIEW_SCHEMA, repo_dir=repo_dir)

        findings = parse_findings(result.output)

        if not findings.items:
            print(f"  Clean: {findings.summary}")
            return StepOutcome(findings=findings)

        print(f"  Risk: {findings.risk_level} — {findings.risk_rationale}")
        print(f"  {findings.summary}\n")
        print(f"  {'ID':<6} {'SEV':<9} {'ACTION':<12} DESCRIPTION")
        print(f"  {'-' * 6} {'-' * 9} {'-' * 12} {'-' * 40}")
        for f in findings.items:
            desc = f.description[:60]
            print(f"  {f.id:<6} {f.severity:<9} {f.action:<12} {desc}")
        print()

        return StepOutcome(
            findings=findings,
        )
