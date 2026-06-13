from __future__ import annotations

import json
import subprocess

from kaizen.findings import FindingsResult
from kaizen.steps import StepOutcome


class PRStep:
    def name(self) -> str:
        return "pr"

    def execute(
        self,
        work_dir: str,
        branch: str,
        base_branch: str,
        findings: FindingsResult | None = None,
    ) -> StepOutcome:
        title = f"{branch}: changes"
        body = self._build_body(branch, findings)

        existing = self._find_existing_pr(branch)
        if existing:
            print(f"  updating PR: {existing}")
            self._update_pr(existing, title, body)
            return StepOutcome(pr_url=existing)

        url = self._create_pr(branch, base_branch, title, body, work_dir)
        if url:
            print(f"  PR created: {url}")
            return StepOutcome(pr_url=url)

        return StepOutcome(skipped=True)

    def _build_body(self, branch: str, findings: FindingsResult | None) -> str:
        lines = ["## What Changed", ""]
        if findings and findings.summary:
            lines.append(findings.summary)
        else:
            lines.append(f"Changes on branch `{branch}`.")
        lines.append("")
        if findings:
            lines.append("## Risk Assessment")
            lines.append("")
            lines.append(f"**Risk:** {findings.risk_level}")
            if findings.risk_rationale:
                lines.append(findings.risk_rationale)
            lines.append("")
        lines.append("---")
        lines.append("*Validated through kaizen pipeline*")
        return "\n".join(lines)

    def _find_existing_pr(self, branch: str) -> str:
        try:
            result = subprocess.run(
                ["gh", "pr", "list", "--head", branch, "--json", "url", "--limit", "1"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                prs = json.loads(result.stdout)
                if prs:
                    return prs[0].get("url", "")
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        return ""

    def _create_pr(
        self,
        branch: str,
        base_branch: str,
        title: str,
        body: str,
        work_dir: str,
    ) -> str:
        try:
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--head",
                    branch,
                    "--base",
                    base_branch,
                    "--title",
                    title,
                    "--body",
                    body,
                ],
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "pull" in line.lower():
                        return line.strip()
                return result.stdout.strip()
            print(f"  gh pr create failed: {result.stderr.strip()}")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            print(f"  gh not available: {e}")
        return ""

    def _update_pr(self, pr_url: str, title: str, body: str) -> None:
        try:
            subprocess.run(
                ["gh", "pr", "edit", pr_url, "--title", title, "--body", body],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
