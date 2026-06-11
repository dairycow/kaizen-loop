import os
import re
import subprocess


def _git(args: list[str], cwd: str) -> str:
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if result.returncode != 0:
        parts = [result.stderr.strip(), result.stdout.strip()]
        raise RuntimeError(" | ".join(p for p in parts if p))
    return result.stdout.strip()


def is_git_repo(cwd: str) -> bool:
    try:
        _git(["rev-parse", "--git-dir"], cwd)
        return True
    except RuntimeError:
        return False


def git_root(cwd: str) -> str:
    return _git(["rev-parse", "--show-toplevel"], cwd)


def current_branch(cwd: str) -> str:
    try:
        return _git(["symbolic-ref", "--short", "HEAD"], cwd)
    except RuntimeError:
        return _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)


def head_commit(cwd: str) -> str:
    return _git(["rev-parse", "HEAD"], cwd)


def ensure_clean_tree(cwd: str) -> None:
    status = _git(["status", "--porcelain"], cwd)
    if status:
        raise RuntimeError("Working tree is not clean. Commit or stash changes first.")


def get_default_branch(cwd: str) -> str:
    try:
        ref = _git(["symbolic-ref", "refs/remotes/origin/HEAD"], cwd)
        return ref.split("/")[-1]
    except RuntimeError:
        try:
            refs = _git(["branch", "-r"], cwd)
            for line in refs.splitlines():
                line = line.strip()
                if line == "origin/main":
                    return "main"
                if line == "origin/master":
                    return "master"
        except RuntimeError:
            pass
    return "main"


def resolve_ref(cwd: str, ref: str) -> str:
    return _git(["rev-parse", ref], cwd)


def get_diff(base: str, head: str, cwd: str) -> str:
    return _git(["diff", f"{base}..{head}"], cwd)


def fetch(cwd: str, remote: str = "origin") -> None:
    _git(["fetch", remote], cwd)


def create_branch(name: str, cwd: str) -> None:
    _git(["checkout", "-b", name], cwd)


def checkout(branch: str, cwd: str) -> None:
    _git(["checkout", branch], cwd)


def branch_exists(cwd: str, branch: str) -> bool:
    try:
        _git(["rev-parse", "--verify", branch], cwd)
        return True
    except RuntimeError:
        return False


def delete_branch(branch: str, cwd: str) -> None:
    try:
        _git(["branch", "-D", branch], cwd)
    except RuntimeError:
        pass


def commit_all(message: str, cwd: str) -> None:
    _git(["add", "-A"], cwd)
    diff = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if diff.returncode == 0:
        return
    _git(
        ["-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", "commit", "-m", message],
        cwd,
    )


def reset_hard(cwd: str) -> None:
    _git(["reset", "--hard", "HEAD"], cwd)
    _git(["clean", "-fdx", "-e", ".kaizen"], cwd)


def branch_commit_count(base: str, cwd: str) -> int:
    if not base:
        return 0
    return int(_git(["rev-list", "--count", "--first-parent", f"{base}..HEAD"], cwd))


def branch_diff_stats(base: str, cwd: str) -> dict:
    if not base:
        return {"files_changed": 0, "lines_added": 0, "lines_deleted": 0}
    rng = f"{base}..HEAD"
    name_status = _git(["diff", "--name-status", rng], cwd)
    numstat = _git(["diff", "--numstat", rng], cwd)
    files_changed = len([line for line in name_status.splitlines() if line.strip()])
    lines_added = 0
    lines_deleted = 0
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0] != "-":
            lines_added += int(parts[0] or 0)
            lines_deleted += int(parts[1] or 0)
    return {"files_changed": files_changed, "lines_added": lines_added, "lines_deleted": lines_deleted}


def slugify_prompt(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)[:50].strip("-")
    return f"kaizen/{slug}" if slug else "kaizen/run"


def create_worktree(repo_cwd: str, branch_name: str, target_path: str) -> str:
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    if os.path.isdir(target_path):
        remove_worktree(repo_cwd, target_path)
    try:
        _git(["worktree", "add", target_path, "-b", branch_name, "HEAD"], repo_cwd)
    except RuntimeError as e:
        if "already exists" not in str(e).lower():
            raise
        remove_worktree(repo_cwd, target_path)
        try:
            _git(["branch", "-D", branch_name], repo_cwd)
        except RuntimeError:
            pass
        _git(["worktree", "prune"], repo_cwd)
        _git(["worktree", "add", target_path, "-b", branch_name, "HEAD"], repo_cwd)
    return target_path


def create_worktree_from_ref(repo_cwd: str, target_path: str, branch_name: str, ref: str) -> str:
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    if os.path.isdir(target_path):
        remove_worktree(repo_cwd, target_path)
    _git(["worktree", "add", "-b", branch_name, target_path, ref], repo_cwd)
    return target_path


def remove_worktree(repo_cwd: str, target_path: str) -> None:
    try:
        _git(["worktree", "remove", "--force", target_path], repo_cwd)
    except RuntimeError:
        pass
    try:
        _git(["worktree", "prune"], repo_cwd)
    except RuntimeError:
        pass


def push_branch(cwd: str, remote: str = "origin", branch: str | None = None) -> None:
    args = ["push", remote]
    if branch:
        args.extend(["-u", branch])
    _git(args, cwd)


def force_push_with_lease(cwd: str, remote: str, branch: str) -> None:
    _git(["push", "--force-with-lease", remote, f"HEAD:refs/heads/{branch}"], cwd)


def copy_user_identity(src_cwd: str, dst_cwd: str) -> None:
    for key in ["user.name", "user.email"]:
        try:
            val = _git(["config", key], src_cwd)
            if val:
                _git(["config", key, val], dst_cwd)
        except RuntimeError:
            pass
