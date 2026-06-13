from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass

from kaizen.findings import FindingsResult, parse_findings
from kaizen.review_prompt import REVIEW_SCHEMA, build_review_prompt
from kaizen.agent import OpenCodeAgent


@dataclass
class ReviewResult:
    findings: FindingsResult | None = None
    skipped: bool = False


@dataclass
class PushResult:
    skipped: bool = False


@dataclass
class PRResult:
    pr_url: str = ""
    skipped: bool = False


def review(
    work_dir: str,
    base_commit: str,
    head_commit: str,
    agent: OpenCodeAgent,
    intent: str = "",
    repo_dir: str | None = None,
) -> ReviewResult:
    from kaizen.git import get_diff

    try:
        diff = get_diff(base_commit, head_commit, work_dir)
    except RuntimeError as e:
        print(f"  Could not get diff: {e}", file=sys.stderr)
        return ReviewResult(skipped=True)

    if not diff.strip():
        print("  No diff found, skipping review")
        return ReviewResult(skipped=True)

    max_diff_size = 50000
    if len(diff) > max_diff_size:
        diff = diff[:max_diff_size] + "\n... (truncated)"

    prompt = build_review_prompt(diff, intent=intent)
    result = agent.run(prompt, work_dir, schema=REVIEW_SCHEMA, repo_dir=repo_dir)

    findings = parse_findings(result.output)

    if not findings.items:
        print(f"  Clean: {findings.summary}")
        return ReviewResult(findings=findings)

    print(f"  Risk: {findings.risk_level} — {findings.risk_rationale}")
    print(f"  {findings.summary}\n")
    print(f"  {'ID':<6} {'SEV':<9} {'ACTION':<12} DESCRIPTION")
    print(f"  {'-' * 6} {'-' * 9} {'-' * 12} {'-' * 40}")
    for f in findings.items:
        desc = f.description[:60]
        print(f"  {f.id:<6} {f.severity:<9} {f.action:<12} {desc}")
    print()

    return ReviewResult(findings=findings)


def push(work_dir: str, branch: str) -> PushResult:
    from kaizen.git import force_push_with_lease

    print(f"  pushing {branch} to origin...")
    try:
        force_push_with_lease(work_dir, "origin", branch)
        print("  pushed successfully")
    except RuntimeError as e:
        print(f"  push failed: {e}", file=sys.stderr)
        return PushResult(skipped=True)

    return PushResult()


def create_pr(
    work_dir: str,
    branch: str,
    base_branch: str,
    findings: FindingsResult | None = None,
) -> PRResult:
    title = f"{branch}: changes"
    body = _build_body(branch, findings)

    existing = _find_existing_pr(branch)
    if existing:
        print(f"  updating PR: {existing}")
        _update_pr(existing, title, body)
        return PRResult(pr_url=existing)

    url = _create_pr(branch, base_branch, title, body, work_dir)
    if url:
        print(f"  PR created: {url}")
        return PRResult(pr_url=url)

    return PRResult(skipped=True)


def _build_body(branch: str, findings: FindingsResult | None) -> str:
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


def _find_existing_pr(branch: str) -> str:
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


def _update_pr(pr_url: str, title: str, body: str) -> None:
    try:
        subprocess.run(
            ["gh", "pr", "edit", pr_url, "--title", title, "--body", body],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
