import json
import os
from dataclasses import dataclass, asdict
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
    status: str = "pending"


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

    info = RunInfo(
        run_id=run_id,
        run_dir=run_dir,
        prompt=prompt,
        branch=branch,
        base_commit=base_commit,
        head_commit=head_commit,
        worktree_path=worktree_path,
        repo_cwd=repo_cwd,
    )
    _save(info)

    notes_path = os.path.join(run_dir, "notes.md")
    if not os.path.exists(notes_path):
        Path(notes_path).write_text(
            f"# kaizen run: {run_id}\n\nObjective: {prompt}\n\n## Iteration Log\n"
        )

    return info


def load_run(run_dir: str) -> RunInfo | None:
    path = os.path.join(run_dir, "run.json")
    if not os.path.isfile(path):
        return None
    try:
        data = json.loads(Path(path).read_text())
        return RunInfo(run_dir=run_dir, **{k: v for k, v in data.items() if k != "run_dir"})
    except (json.JSONDecodeError, TypeError):
        return None


def update_run_status(run_dir: str, status: str) -> None:
    info = load_run(run_dir)
    if info:
        info.status = status
        _save(info)


def update_run_head(run_dir: str, head: str) -> None:
    info = load_run(run_dir)
    if info:
        info.head_commit = head
        _save(info)


def update_run_pr_url(run_dir: str, pr_url: str) -> None:
    info = load_run(run_dir)
    if info:
        info.pr_url = pr_url
        _save(info)


def _save(info: RunInfo) -> None:
    path = os.path.join(info.run_dir, "run.json")
    d = asdict(info)
    del d["run_dir"]
    Path(path).write_text(json.dumps(d, indent=2) + "\n")


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
