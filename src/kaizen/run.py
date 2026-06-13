import os
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
    run_id: str,
    worktree_path: str | None = None,
    repo_cwd: str | None = None,
) -> RunInfo:
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
            f"# kaizen run: {run_id}\n\nObjective: {prompt}\n\n## Iteration Log\n"
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


def load_run(run_dir: str) -> RunInfo | None:
    if not os.path.isdir(run_dir):
        return None
    try:
        prompt = Path(os.path.join(run_dir, "prompt.md")).read_text().strip()
        branch = Path(os.path.join(run_dir, "branch")).read_text().strip()
        base_commit = Path(os.path.join(run_dir, "base-commit")).read_text().strip()
        head_commit = Path(os.path.join(run_dir, "head-commit")).read_text().strip()
    except FileNotFoundError:
        return None
    worktree_path = None
    wt_file = os.path.join(run_dir, "worktree")
    if os.path.exists(wt_file):
        worktree_path = Path(wt_file).read_text().strip() or None
    repo_cwd = None
    rc_file = os.path.join(run_dir, "repo-cwd")
    if os.path.exists(rc_file):
        repo_cwd = Path(rc_file).read_text().strip() or None
    run_id = os.path.basename(run_dir)
    pr_url = None
    pr_file = os.path.join(run_dir, "pr-url")
    if os.path.exists(pr_file):
        pr_url = Path(pr_file).read_text().strip() or None
    return RunInfo(
        run_id=run_id,
        run_dir=run_dir,
        prompt=prompt,
        branch=branch,
        base_commit=base_commit,
        head_commit=head_commit,
        worktree_path=worktree_path,
        repo_cwd=repo_cwd,
        pr_url=pr_url,
    )


def append_notes(
    notes_path: str,
    iteration: int,
    summary: str,
    changes: list[str],
    learnings: list[str],
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
