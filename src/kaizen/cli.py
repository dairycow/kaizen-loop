from __future__ import annotations

import argparse
import os
import signal
import sys

from kaizen import __version__
from kaizen.agent import OpenCodeAgent
from kaizen.config import load_config
from kaizen.git import is_git_repo


def cmd_loop(args: argparse.Namespace) -> None:
    cwd = args.cwd
    if not is_git_repo(cwd):
        print("Error: not a git repo", file=sys.stderr)
        sys.exit(1)

    if not args.prompt:
        print("Error: prompt required", file=sys.stderr)
        sys.exit(1)

    config = load_config()
    use_worktree = not args.no_worktree

    agent = OpenCodeAgent(
        project_dir=cwd,
    )

    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

    try:
        from kaizen.loop import run_loop

        result = run_loop(
            prompt=args.prompt,
            cwd=cwd,
            agent=agent,
            max_work_iterations=args.max_iterations,
            max_review_rounds=args.max_review_rounds
            or config.get("max_review_rounds", 3),
            use_worktree=use_worktree,
        )

        if result == "passed":
            print("\n  kaizen loop passed")
        elif result == "cancelled":
            print("\n  kaizen loop cancelled")
            sys.exit(1)
        else:
            print("\n  kaizen loop failed")
            sys.exit(1)
    except Exception as e:
        print(f"\n  fatal: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        agent.close()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]

    parser = argparse.ArgumentParser(
        prog="kaizen",
        description="Continuous code improvement: work → review → fix → ship",
    )
    parser.add_argument("--version", action="version", version=f"kaizen {__version__}")
    parser.add_argument(
        "--directory", "-C", help="Path to git repo (default: current dir)"
    )

    parser.add_argument("prompt", nargs="?", help="What the agent should do")
    parser.add_argument("--max-iterations", type=int, help="Max work iterations")
    parser.add_argument("--max-review-rounds", type=int, help="Max review rounds")
    parser.add_argument(
        "--no-worktree",
        action="store_true",
        help="Work in current tree instead of worktree",
    )

    args = parser.parse_args()
    args.cwd = args.directory or os.getcwd()

    if args.prompt:
        cmd_loop(args)
    else:
        parser.print_help()
