from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from kaizen.agent import OpenCodeAgent
from kaizen.config import load_config
from kaizen.findings import ACTION_ASK_USER, ACTION_AUTO_FIX, FindingsResult, Finding
from kaizen.git import (
    checkout,
    commit_all,
    copy_user_identity,
    create_branch,
    create_worktree_from_ref,
    delete_branch,
    fetch,
    get_default_branch,
    head_commit,
    remove_worktree,
    resolve_ref,
    slugify_prompt,
)
from kaizen.orchestrator import Orchestrator
from kaizen.review_prompt import build_fix_prompt
from kaizen.run import RunInfo, setup_run, update_run_head, update_run_pr_url, update_run_status
from kaizen.steps.pr import PRStep
from kaizen.steps.push import PushStep
from kaizen.steps.review import ReviewStep


@dataclass
class _WorkContext:
    branch: str
    work_dir: str
    worktree_path: str | None
    base_commit: str
    run_info: RunInfo
    default_branch: str


def _setup_work_context(
    prompt: str,
    cwd: str,
    use_worktree: bool = True,
) -> _WorkContext:
    config = load_config()

    kaizen_dir = os.path.join(cwd, ".kaizen")
    os.makedirs(kaizen_dir, exist_ok=True)
    gitignore = os.path.join(kaizen_dir, ".gitignore")
    if not os.path.exists(gitignore):
        Path(gitignore).write_text("worktrees/\nruns/\n")

    root_gitignore = os.path.join(cwd, ".gitignore")
    if os.path.exists(root_gitignore):
        content = Path(root_gitignore).read_text()
        if ".kaizen" not in content.splitlines():
            Path(root_gitignore).write_text(content.rstrip() + "\n.kaizen/\n")
    else:
        Path(root_gitignore).write_text(".kaizen/\n")

    fetch(cwd)
    default_branch = get_default_branch(cwd)
    try:
        base_commit = resolve_ref(cwd, f"origin/{default_branch}")
    except RuntimeError:
        base_commit = head_commit(cwd)

    branch = slugify_prompt(prompt)
    work_dir = cwd
    worktree_path: str | None = None

    if use_worktree:
        worktree_path = os.path.join(cwd, ".kaizen", "worktrees", branch.replace("/", "-"))
        print(f"  creating worktree: {worktree_path}")
        try:
            create_worktree_from_ref(cwd, worktree_path, branch, f"origin/{default_branch}")
        except RuntimeError as e:
            print(f"  worktree creation failed: {e}", file=sys.stderr)
            sys.exit(1)
        copy_user_identity(cwd, worktree_path)
        work_dir = worktree_path
    else:
        try:
            create_branch(branch, cwd)
        except RuntimeError:
            pass

    current_head = head_commit(work_dir)
    run_info = setup_run(
        prompt=prompt,
        branch=branch,
        base_commit=base_commit,
        head_commit=current_head,
        worktree_path=worktree_path,
        repo_cwd=cwd,
    )

    return _WorkContext(
        branch=branch,
        work_dir=work_dir,
        worktree_path=worktree_path,
        base_commit=base_commit,
        run_info=run_info,
        default_branch=default_branch,
    )


def run_loop(
    prompt: str,
    cwd: str,
    agent: OpenCodeAgent,
    max_work_iterations: int | None = None,
    max_review_rounds: int = 3,
    use_worktree: bool = True,
) -> str:
    ctx = _setup_work_context(prompt, cwd, use_worktree)

    print(f"  run {ctx.run_info.run_id} on branch {ctx.branch}")
    print(f"  base: {ctx.default_branch} ({ctx.base_commit[:8]})")

    try:
        # ── Phase 1: WORK ──
        print(f"\n{'=' * 50}")
        print(f"  PHASE: WORK")
        print(f"{'=' * 50}")

        config = load_config()
        orch = Orchestrator(
            agent=agent,
            run_info=ctx.run_info,
            prompt=prompt,
            cwd=ctx.work_dir,
            max_iterations=max_work_iterations or config.get("max_work_iterations"),
            repo_dir=cwd,
        )
        orch.run()

        current_head = head_commit(ctx.work_dir)
        update_run_head(ctx.run_info.run_dir, current_head)

        # ── Phase 2: REVIEW (with fix loop) ──
        print(f"\n{'=' * 50}")
        print(f"  PHASE: REVIEW")
        print(f"{'=' * 50}")

        review_step = ReviewStep()
        final_findings: FindingsResult | None = None

        for round_num in range(max_review_rounds):
            print(f"\n  review round {round_num + 1}/{max_review_rounds}")

            current_head = head_commit(ctx.work_dir)
            outcome = review_step.execute(
                work_dir=ctx.work_dir,
                base_commit=ctx.base_commit,
                head_commit=current_head,
                agent=agent,
                intent=prompt,
                repo_dir=cwd,
            )

            if outcome.skipped:
                print("  review skipped")
                break

            if outcome.findings:
                final_findings = outcome.findings

            if not outcome.needs_approval or not outcome.findings or not outcome.findings.items:
                print("  review clean")
                break

            findings = outcome.findings
            auto_fix_items = findings.auto_fix_items
            ask_user_items = findings.ask_user_items

            if auto_fix_items:
                print(f"\n  auto-fixing {len(auto_fix_items)} issues...")
                fix_prompt = build_fix_prompt([_finding_to_dict(f) for f in auto_fix_items])
                try:
                    agent.run(fix_prompt, ctx.work_dir, repo_dir=cwd)
                    commit_all(f"kaizen: fix {len(auto_fix_items)} review findings", ctx.work_dir)
                    current_head = head_commit(ctx.work_dir)
                    update_run_head(ctx.run_info.run_dir, current_head)
                    print("  fixes committed")
                    continue
                except Exception as e:
                    print(f"  auto-fix failed: {e}")

            if ask_user_items:
                _present_findings(findings)
                action = _get_user_action(findings)
                if action == "approve":
                    break
                elif action == "fix":
                    instructions = _get_user_instructions()
                    fix_prompt = build_fix_prompt(
                        [_finding_to_dict(f) for f in ask_user_items],
                        user_instructions=instructions,
                    )
                    try:
                        agent.run(fix_prompt, ctx.work_dir, repo_dir=cwd)
                        commit_all("kaizen: fix user-flagged findings", ctx.work_dir)
                        current_head = head_commit(ctx.work_dir)
                        update_run_head(ctx.run_info.run_dir, current_head)
                    except Exception as e:
                        print(f"  fix failed: {e}")
                    continue
                elif action == "abort":
                    update_run_status(ctx.run_info.run_dir, "cancelled")
                    return "cancelled"
                else:
                    break
            else:
                break

        # ── Phase 3: SHIP ──
        print(f"\n{'=' * 50}")
        print(f"  PHASE: SHIP")
        print(f"{'=' * 50}")

        push_step = PushStep()
        push_outcome = push_step.execute(work_dir=ctx.work_dir, branch=ctx.branch)
        if push_outcome.skipped:
            print("  push skipped, cannot create PR")
            update_run_status(ctx.run_info.run_dir, "failed")
            return "failed"

        pr_step = PRStep()
        pr_outcome = pr_step.execute(
            work_dir=ctx.work_dir,
            branch=ctx.branch,
            base_branch=ctx.default_branch,
            findings=final_findings,
        )

        if pr_outcome.pr_url:
            update_run_pr_url(ctx.run_info.run_dir, pr_outcome.pr_url)

        update_run_status(ctx.run_info.run_dir, "completed")
        return "passed"

    except Exception as e:
        print(f"\n  [FATAL] {e}", file=sys.stderr)
        update_run_status(ctx.run_info.run_dir, "failed")
        return "failed"

    finally:
        # ── Phase 4: CLEANUP ──
        print(f"\n  cleaning up...")
        if ctx.worktree_path:
            remove_worktree(cwd, ctx.worktree_path)
        else:
            try:
                checkout(ctx.default_branch, cwd)
            except RuntimeError:
                pass
        delete_branch(ctx.branch, cwd)


def _finding_to_dict(f: Finding) -> dict:
    d: dict = {
        "id": f.id,
        "severity": f.severity,
        "description": f.description,
        "action": f.action,
    }
    if f.file:
        d["file"] = f.file
    if f.line:
        d["line"] = f.line
    return d


def _present_findings(findings: FindingsResult) -> None:
    print(f"\n  Risk: {findings.risk_level} — {findings.risk_rationale}")
    print(f"  {findings.summary}\n")
    if findings.items:
        print(f"  {'ID':<6} {'SEV':<9} {'ACTION':<12} DESCRIPTION")
        print(f"  {'-' * 6} {'-' * 9} {'-' * 12} {'-' * 40}")
        for f in findings.items:
            desc = f.description[:60]
            print(f"  {f.id:<6} {f.severity:<9} {f.action:<12} {desc}")
    print()


def _get_user_action(findings: FindingsResult) -> str:
    while True:
        print("  [a]pprove  [f]ix  [A]bort")
        try:
            choice = input("  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return "abort"
        if choice in ("a", "approve"):
            return "approve"
        elif choice in ("f", "fix"):
            return "fix"
        elif choice == "abort":
            return "abort"


def _get_user_instructions() -> str:
    print("  Enter fix instructions (empty for none):")
    try:
        return input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        return ""
