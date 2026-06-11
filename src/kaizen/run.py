import os
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RunInfo:
    run_id: str
    run_dir: str
    prompt: str
    branch: str
    base_commit: str
    head_commit: str
    worktree_path: str | None = None
    repo_cwd: str | None = None
    pr_url: str | None = None


def runs_home() -> str:
    return os.path.expanduser("~/.kaizen/runs")


def setup_run(
    prompt: str,
    branch: str,
    base_commit: str,
    head_commit: str,
    worktree_path: str | None = None,
    repo_cwd: str | None = None,
) -> RunInfo:
    run_id = uuid.uuid4().hex[:8]
    run_dir = os.path.join(runs_home(), run_id)
    os.makedirs(run_dir, exist_ok=True)

    Path(os.path.join(run_dir, "prompt.md")).write_text(prompt + "\n")
    Path(os.path.join(run_dir, "branch")).write_text(branch + "\n")
    Path(os.path.join(run_dir, "base-commit")).write_text(base_commit + "\n")
    Path(os.path.join(run_dir, "head-commit")).write_text(head_commit + "\n")
    Path(os.path.join(run_dir, "status")).write_text("pending\n")

    if worktree_path:
        Path(os.path.join(run_dir, "worktree")).write_text(worktree_path + "\n")
    if repo_cwd:
        Path(os.path.join(run_dir, "repo-cwd")).write_text(repo_cwd + "\n")

    notes_path = os.path.join(run_dir, "notes.md")
    if not os.path.exists(notes_path):
        Path(notes_path).write_text(
            f"# kaizen run: {run_id}\n\n"
            f"Objective: {prompt}\n\n"
            "## Iteration Log\n"
        )

    return RunInfo(
        run_id=run_id,
        run_dir=run_dir,
        prompt=prompt,
        branch=branch,
        base_commit=base_commit,
        head_commit=head_commit,
        worktree_path=worktree_path,
        repo_cwd=repo_cwd,
    )


def update_run_status(run_dir: str, status: str) -> None:
    Path(os.path.join(run_dir, "status")).write_text(status + "\n")


def update_run_head(run_dir: str, head: str) -> None:
    Path(os.path.join(run_dir, "head-commit")).write_text(head + "\n")


def update_run_pr_url(run_dir: str, pr_url: str) -> None:
    Path(os.path.join(run_dir, "pr-url")).write_text(pr_url + "\n")


def append_notes(
    notes_path: str, iteration: int, summary: str,
    changes: list[str], learnings: list[str],
) -> None:
    lines = [f"\n### Iteration {iteration}\n", f"**Summary:** {summary}\n"]
    if changes:
        lines.append("**Changes:**")
        lines.extend(f"- {c}" for c in changes)
        lines.append("")
    if learnings:
        lines.append("**Learnings:**")
        lines.extend(f"- {item}" for item in learnings)
        lines.append("")
    with open(notes_path, "a") as f:
        f.write("\n".join(lines))
