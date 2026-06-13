---
name: kaizen-loop
description: Use kaizen to autonomously drive code changes through the work, review, fix, and ship pipeline. Use when the user wants to delegate a task to kaizen, run batch jobs with a shared opencode server, inspect run history, configure kaizen, or troubleshoot kaizen issues. Do NOT use for direct code editing — kaizen operates as a separate CLI that orchestrates opencode sessions.
---

## What kaizen does

kaizen is a CLI tool (`kaizen-loop` package) that drives opencode through an autonomous loop:

1. **SETUP** — fetches `origin/<default-branch>`, creates branch `kaizen/<hash>`, creates isolated git worktree
2. **WORK** — runs opencode sessions iteratively with notes.md memory across iterations
3. **REVIEW** — agent reviews the diff, returns structured findings (severity + action), auto-fixes mechanical issues
4. **SHIP** — force-pushes to origin, creates PR via `gh`
5. **CLEANUP** — removes worktree and deletes branch on success; preserves worktree on failure (for resume)

## When to use this skill

- The user asks to run kaizen, delegate work to kaizen, or use kaizen for autonomous changes
- The user asks about kaizen configuration, run history, or shared server usage
- The user wants to batch multiple tasks via kaizen
- Do NOT use when the user wants you to directly edit code — kaizen is a separate orchestration tool

## IMPORTANT: Running from within opencode

**CRITICAL**: When you invoke kaizen from within an opencode session (which is always the case when this skill is loaded), you MUST run it in the background. kaizen's full pipeline (work → review → ship) can take 10+ minutes, which will exceed the Bash tool's timeout and cause a failed tool call.

**Always use this pattern:**

```bash
nohup kaizen "your prompt here" > /tmp/kaizen-latest.log 2>&1 &
echo "PID: $!"
```

Then immediately report to the user that kaizen has been started, and show them how to check on it:

```bash
RUN_ID=$(ls -t .kaizen/runs/ | head -1) && python3 -c "import json; print(json.load(open('.kaizen/runs/$RUN_ID/run.json'))['status'])"
```

```bash
tail -f /tmp/kaizen-latest.log
```

Do NOT run kaizen synchronously (i.e., `kaizen "prompt"` without backgrounding). It will time out.

## Basic usage

```bash
kaizen "add a --json flag to the status command"
```

This creates an isolated branch, the agent does the work, the pipeline reviews it, fixes what it can, pushes to origin, and opens a PR.

### Prerequisites

- Python 3.10+
- opencode (`curl -fsSL https://opencode.ai/install | bash`)
- git
- `gh` CLI (for PR creation)

### Install or update

```bash
uv tool install kaizen-loop --reinstall --force
```

Verify:

```bash
kaizen --version
```

## CLI options

```bash
kaizen "prompt" [-C /path/to/repo] [--max-iterations N] [--max-review-rounds N] [--no-worktree]
```

| Option | Meaning |
|---|---|
| `-C, --directory` | Path to git repo (default: current dir) |
| `--max-iterations` | Max work iterations (default: unlimited) |
| `--max-review-rounds` | Max review rounds (default: 3) |
| `--no-worktree` | Work in current tree instead of isolated worktree |

## Shared server for batch work

kaizen auto-discovers a running `opencode serve` process. For batch work, start a server once:

```bash
opencode serve --hostname 127.0.0.1 --port 4096 &
```

Then run multiple kaizen invocations — each will auto-discover the same server:

```bash
kaizen "fix issue #1"
kaizen "fix issue #2"
```

### Check for existing server

```bash
curl -sf http://127.0.0.1:4096/global/health
```

A 200 response means a server is running. You can also check:

```bash
pgrep -a opencode
```

### Stop the server

```bash
kill %1
```

Or via HTTP:

```bash
curl -X POST http://127.0.0.1:4096/instance/dispose
```

## Configuration

`~/.kaizen/config.json` (auto-created on first run):

```json
{
  "max_work_iterations": null,
  "max_review_rounds": 3,
  "max_consecutive_failures": 3,
  "use_worktree": true
}
```

## Run history

All runs are stored in `<repo>/.kaizen/runs/<run-id>/`. Each run directory contains:

| File | Content |
|---|---|
| `run.json` | All run metadata: prompt, branch, base/head commit SHAs, status (`pending`/`completed`/`failed`), PR URL, worktree path |
| `notes.md` | Iteration-by-iteration log with summaries, changes, and learnings |

To inspect recent runs:

```bash
ls -lt .kaizen/runs/ | head
```

To check a specific run's status:

```bash
python3 -c "import json; print(json.load(open('.kaizen/runs/<run-id>/run.json'))['status'])"
```

## Pipeline details

### Work phase

- Each iteration creates a **fresh opencode session** (per-iteration, not reused) — this prevents cascading failures when one iteration errors out
- Each iteration: reads prior notes.md → does one incremental piece of work → reports success/failure
- On success: auto-commits with message `kaizen <N>: <summary>`, appends to notes.md
- On failure: resets hard, logs learnings, increments consecutive failure count
- Aborts after `max_consecutive_failures` (default: 3) consecutive failures
- HTTP 500 errors from the server are retried automatically (up to 4 retries with exponential backoff)

### Resume

If a run is interrupted (failure, cancellation, crash), kaizen can resume it. On the next invocation with the **same prompt in the same repo**, kaizen detects the existing worktree and run directory, counts commits since the base, and resumes work from that iteration. Failed runs with commits preserve the worktree and branch instead of cleaning up.

### Review phase

- Agent reviews the full diff against base commit
- Returns structured findings with severity (`info`/`warning`/`error`) and action (`no-op`/`auto-fix`)
- `no-op`: informational, silently accepted
- `auto-fix`: mechanical fix — agent fixes automatically, re-reviews up to `max_review_rounds`
- Provides overall risk level: `low`, `medium`, or `high`

### Ship phase

- Force-pushes branch to origin (with lease for safety)
- Creates PR via `gh pr create` with title and body including risk assessment
- Updates existing PR if one already exists for the branch

### Branch naming

Branches are named `kaizen/<hash>` where hash is the first 12 characters of `sha256(repo_path + "\n" + prompt)`. The same prompt in the same repo always produces the same branch, enabling resume. For example: `kaizen/a1b2c3d4e5f6`.

## Troubleshooting

**Server won't start**: Check if another opencode instance is running (`pgrep -a opencode`). Kill stale processes.

**HTTP 500 or Connection refused during batch runs**: Too many concurrent kaizen sessions are overwhelming the LLM API rate limit. Reduce the number of parallel kaizen processes to 3–4. kaizen retries transient 500s automatically, but sustained rate limiting requires fewer concurrent runs.

**Worktree creation failed**: Ensure no stale worktrees exist. Run `git worktree prune` in the repo.

**Push failed**: Check git remote access. Ensure `origin` is configured and you have push permissions.

**PR creation failed**: Ensure `gh` CLI is installed and authenticated (`gh auth status`).

**Run stuck/cancelled**: Use Ctrl+C once for graceful stop, twice for force stop. If the run has commits, the worktree and branch are preserved for resume; otherwise they are cleaned up.

## Example workflows

**Remember**: Always background kaizen when running from within opencode.

### Single task

```bash
nohup kaizen "refactor the database connection pool to use async/await" > /tmp/kaizen-latest.log 2>&1 &
echo "PID: $!"
```

### Target a specific repo

```bash
nohup kaizen "add unit tests for auth module" -C /path/to/my-project > /tmp/kaizen-latest.log 2>&1 &
echo "PID: $!"
```

### Limit iterations for quick changes

```bash
nohup kaizen "fix typo in README" --max-iterations 1 > /tmp/kaizen-latest.log 2>&1 &
echo "PID: $!"
```

### Batch with shared server

```bash
opencode serve --hostname 127.0.0.1 --port 4096 &
nohup kaizen "implement feature A" > /tmp/kaizen-a.log 2>&1 &
nohup kaizen "implement feature B" > /tmp/kaizen-b.log 2>&1 &
nohup kaizen "add tests for both features" > /tmp/kaizen-tests.log 2>&1 &
```

Batch runs with a shared server can run in parallel since each uses its own worktree and per-iteration sessions.

**Concurrency guidance**: Each kaizen session makes concurrent LLM API calls. Running too many sessions simultaneously (typically >3–4) can trigger API rate limits, causing server errors and connection failures. If you see repeated `HTTP 500` or `Connection refused` errors in the logs, reduce the number of parallel kaizen processes. kaizen retries transient 500s automatically (up to 4 retries), but sustained rate limiting requires fewer concurrent runs.

### Work in current tree (no worktree isolation)

```bash
nohup kaizen "update dependencies" --no-worktree > /tmp/kaizen-latest.log 2>&1 &
echo "PID: $!"
```

### Checking on a running task

```bash
tail -20 /tmp/kaizen-latest.log
RUN_ID=$(ls -t .kaizen/runs/ | head -1) && python3 -c "import json; r=json.load(open('.kaizen/runs/$RUN_ID/run.json')); print(f'status={r[\"status\"]} branch={r[\"branch\"]}')"
```
