from __future__ import annotations

import sys

from kaizen.steps import StepOutcome


class PushStep:
    def name(self) -> str:
        return "push"

    def execute(self, work_dir: str, branch: str) -> StepOutcome:
        from kaizen.git import force_push_with_lease

        print(f"  pushing {branch} to origin...")
        try:
            force_push_with_lease(work_dir, "origin", branch)
            print("  pushed successfully")
        except RuntimeError as e:
            print(f"  push failed: {e}", file=sys.stderr)
            return StepOutcome(skipped=True)

        return StepOutcome()
