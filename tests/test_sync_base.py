import os
import subprocess
from pathlib import Path

import pytest

from kaizen.git import (
    head_commit,
    rebase_abort,
    rebase_onto,
    resolve_ref,
)
from kaizen.loop import _WorkContext, _sync_base
from kaizen.run import setup_run


def _run(args: list[str], cwd: str) -> str:
    result = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if result.returncode != 0:
        parts = [result.stderr.strip(), result.stdout.strip()]
        raise RuntimeError(" | ".join(p for p in parts if p))
    return result.stdout.strip()


def _commit(path: str, msg: str, filename: str = "file.txt", content: str | None = None) -> str:
    Path(os.path.join(path, filename)).write_text(content if content is not None else msg)
    _run(["git", "add", "-A"], path)
    _run(["git", "commit", "-m", msg], path)
    return head_commit(path)


@pytest.fixture()
def repo(tmp_path: Path) -> dict:
    origin = str(tmp_path / "origin.git")
    _run(["git", "init", "--bare", "-b", "main", origin], str(tmp_path))

    clone = str(tmp_path / "work")
    _run(["git", "clone", origin, clone], str(tmp_path))
    _run(["git", "config", "user.email", "test@test.com"], clone)
    _run(["git", "config", "user.name", "Test"], clone)
    _run(["git", "config", "commit.gpgsign", "false"], clone)

    base = _commit(clone, "initial")
    _run(["git", "push", "origin", "main"], clone)
    _run(["git", "checkout", "-b", "work"], clone)

    return {"origin": origin, "clone": clone, "base": base, "tmp": str(tmp_path)}


def _make_ctx(clone: str, base: str) -> tuple[_WorkContext, str]:
    run_dir = os.path.join(clone, ".kaizen", "runs", "test")
    run_info = setup_run(
        prompt="test",
        branch="work",
        base_commit=base,
        head_commit=head_commit(clone),
        run_dir=run_dir,
        run_id="test",
        repo_cwd=clone,
    )
    ctx = _WorkContext(
        branch="work",
        work_dir=clone,
        worktree_path=None,
        base_commit=base,
        run_info=run_info,
        default_branch="main",
    )
    return ctx, run_dir


def test_sync_noop(repo, capsys):
    clone = repo["clone"]
    ctx, _ = _make_ctx(clone, repo["base"])
    _sync_base(ctx, clone)
    assert ctx.base_commit == repo["base"]


def test_sync_rebase_success(repo):
    clone = repo["clone"]
    base = repo["base"]

    _commit(clone, "work change", filename="work.txt")

    other = os.path.join(repo["tmp"], "other")
    _run(["git", "clone", repo["origin"], other], repo["tmp"])
    _run(["git", "config", "user.email", "t@t.com"], other)
    _run(["git", "config", "user.name", "T"], other)
    _run(["git", "config", "commit.gpgsign", "false"], other)
    _commit(other, "main advance", filename="main.txt")
    _run(["git", "push", "origin", "main"], other)

    ctx, _ = _make_ctx(clone, base)
    _sync_base(ctx, clone)

    new_base = resolve_ref(clone, "origin/main")
    assert ctx.base_commit == new_base
    assert new_base != base
    from kaizen.run import load_run

    persisted = load_run(ctx.run_info.run_dir)
    assert persisted is not None
    assert persisted.base_commit == new_base


def test_sync_rebase_conflict(repo, capsys):
    clone = repo["clone"]
    base = repo["base"]

    Path(os.path.join(clone, "file.txt")).write_text("work change")
    _run(["git", "add", "-A"], clone)
    _run(["git", "commit", "-m", "work change"], clone)

    other = os.path.join(repo["tmp"], "other")
    _run(["git", "clone", repo["origin"], other], repo["tmp"])
    _run(["git", "config", "user.email", "t@t.com"], other)
    _run(["git", "config", "user.name", "T"], other)
    _run(["git", "config", "commit.gpgsign", "false"], other)
    Path(os.path.join(other, "file.txt")).write_text("main change")
    _run(["git", "add", "-A"], other)
    _run(["git", "commit", "-m", "main change"], other)
    _run(["git", "push", "origin", "main"], other)

    ctx, _ = _make_ctx(clone, base)
    _sync_base(ctx, clone)

    assert ctx.base_commit == base
    work_content = Path(os.path.join(clone, "file.txt")).read_text()
    assert work_content == "work change"
    captured = capsys.readouterr()
    assert "conflicted" in captured.err or "conflicted" in captured.out


def test_rebase_abort_clears_state(tmp_path):
    repo_a = str(tmp_path / "a")
    repo_b = str(tmp_path / "b")
    for p in (repo_a, repo_b):
        _run(["git", "init", "-b", "main", p], str(tmp_path))
        _run(["git", "config", "user.email", "t@t.com"], p)
        _run(["git", "config", "user.name", "T"], p)
        _run(["git", "config", "commit.gpgsign", "false"], p)
        Path(os.path.join(p, "f.txt")).write_text("base")
        _run(["git", "add", "-A"], p)
        _run(["git", "commit", "-m", "base"], p)

    base = head_commit(repo_a)
    _commit(repo_a, "a change", filename="f.txt", content="a")
    _run(["git", "checkout", "-b", "work"], repo_a)

    _commit(repo_b, "b change", filename="f.txt", content="b")

    b_head = head_commit(repo_b)
    with pytest.raises(RuntimeError):
        rebase_onto(repo_a, b_head, base)
    rebase_abort(repo_a)
    _run(["git", "rev-parse", "HEAD"], repo_a)
