import random
import time

from pydantic import BaseModel, Field

from kaizen.agent import OpenCodeAgent
from kaizen.config import load_config
from kaizen.git import (
    branch_commit_count,
    commit_all,
    push_branch,
    reset_hard,
)
from kaizen.run import RunInfo, append_notes
from kaizen.work_prompt import build_iteration_prompt

_BACKOFF_BASE_DELAY = 5.0
_BACKOFF_MAX_DELAY = 120.0

WORK_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "success": {"type": "boolean"},
        "summary": {"type": "string"},
        "key_changes_made": {"type": "array", "items": {"type": "string"}},
        "key_learnings": {"type": "array", "items": {"type": "string"}},
        "should_fully_stop": {"type": "boolean"},
    },
    "required": ["success", "summary", "key_changes_made", "key_learnings"],
}


class WorkOutput(BaseModel):
    success: bool
    summary: str
    key_changes_made: list[str] = Field(default_factory=list)
    key_learnings: list[str] = Field(default_factory=list)
    should_fully_stop: bool = False


class Orchestrator:
    def __init__(
        self,
        agent: OpenCodeAgent,
        run_info: RunInfo,
        prompt: str,
        cwd: str,
        start_iteration: int = 0,
        max_iterations: int | None = None,
        stop_when: str | None = None,
        push_remote: str | None = None,
        repo_dir: str | None = None,
    ):
        self.agent = agent
        self.run_info = run_info
        self.prompt = prompt
        self.cwd = cwd
        self.repo_dir = repo_dir
        self.config = load_config()
        self.iteration = start_iteration
        self.max_iterations = max_iterations
        self.stop_when = stop_when
        self.push_remote = push_remote
        self.success_count = 0
        self.fail_count = 0
        self.consecutive_failures = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.commit_count = branch_commit_count(run_info.base_commit, cwd)
        self.start_time: float = 0
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def run(self) -> str:
        self.start_time = time.time()
        status = "stopped"

        try:
            with self.agent.session(self.cwd, repo_dir=self.repo_dir) as sess:
                while not self._stop_requested:
                    if self.max_iterations and self.iteration >= self.max_iterations:
                        print(f"  max iterations reached ({self.max_iterations})")
                        status = "aborted"
                        break

                    self.iteration += 1
                    print(f"\n  --- work iteration {self.iteration} ---")

                    iter_prompt = build_iteration_prompt(
                        self.iteration,
                        self.run_info.run_id,
                        self.prompt,
                        self.stop_when,
                    )

                    try:
                        result = sess.send(iter_prompt, schema=WORK_SCHEMA)
                    except Exception as e:
                        print(f"  [ERROR] {e}")
                        self.fail_count += 1
                        self.consecutive_failures += 1
                        reset_hard(self.cwd)
                        if self.consecutive_failures >= self.config.get(
                            "max_consecutive_failures", 3
                        ):
                            print(
                                f"  {self.consecutive_failures} consecutive failures, aborting"
                            )
                            status = "aborted"
                            break
                        delay = min(
                            _BACKOFF_BASE_DELAY
                            * (2 ** (self.consecutive_failures - 1)),
                            _BACKOFF_MAX_DELAY,
                        )
                        delay *= 0.5 + random.random() * 0.5
                        print(
                            f"  backing off {delay:.0f}s (failure {self.consecutive_failures})..."
                        )
                        deadline = time.time() + delay
                        while time.time() < deadline and not self._stop_requested:
                            time.sleep(min(0.5, max(0, deadline - time.time())))
                        continue

                    work = WorkOutput.model_validate(result.output)

                    self.total_input_tokens += result.input_tokens
                    self.total_output_tokens += result.output_tokens

                    if work.success:
                        commit_msg = f"kaizen {self.iteration}: {work.summary}"
                        try:
                            commit_all(commit_msg, self.cwd)
                        except RuntimeError as e:
                            print(f"  [COMMIT FAILED] {e}")
                            self.fail_count += 1
                            self.consecutive_failures += 1
                            continue

                        self.commit_count = branch_commit_count(
                            self.run_info.base_commit, self.cwd
                        )
                        self.success_count += 1
                        self.consecutive_failures = 0
                        append_notes(
                            self.run_info.run_dir + "/notes.md",
                            self.iteration,
                            work.summary,
                            work.key_changes_made,
                            work.key_learnings,
                        )
                        print(f"  committed: {work.summary}")

                        if self.push_remote:
                            try:
                                push_branch(self.cwd, self.push_remote)
                                print(f"  pushed to {self.push_remote}")
                            except RuntimeError as e:
                                print(f"  [PUSH FAILED] {e}")
                    else:
                        self.fail_count += 1
                        self.consecutive_failures += 1
                        reset_hard(self.cwd)
                        append_notes(
                            self.run_info.run_dir + "/notes.md",
                            self.iteration,
                            f"[FAIL] {work.summary}",
                            [],
                            work.key_learnings,
                        )
                        print(f"  failed: {work.summary}")

                    if self.stop_when and work.should_fully_stop:
                        print(f"  stop condition met: {self.stop_when}")
                        status = "stopped"
                        break

                    if self.consecutive_failures >= self.config.get(
                        "max_consecutive_failures", 3
                    ):
                        print(
                            f"  {self.consecutive_failures} consecutive failures, aborting"
                        )
                        status = "aborted"
                        break

        except KeyboardInterrupt:
            print("\n  interrupted")
            status = "stopped"

        return status

    def elapsed(self) -> float:
        if not self.start_time:
            return 0
        return time.time() - self.start_time
