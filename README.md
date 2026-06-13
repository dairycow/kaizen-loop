# kaizen-loop

Continuous code improvement: autonomous work → review → fix → ship.

A zero-dependency Python harness that drives [opencode](https://opencode.ai) through the full cycle of writing, validating, and shipping code — fully autonomous.

## Quick start

```bash
# Install
pip install -e .

# Start an opencode server (one-time, leave it running)
opencode serve --hostname 127.0.0.1 --port 4096 &

# Run
kaizen "add a --json flag to the status command"
```

kaizen auto-discovers a running `opencode serve` process on your machine (preferring one started in the same project directory). If no server is found, it fails with instructions. It never starts or manages a server process itself.

### Prerequisites

- Python 3.10+
- [opencode](https://opencode.ai) (`curl -fsSL https://opencode.ai/install | bash`)
- An `opencode serve` instance running (see [Server](#server))
- `git`
- `gh` CLI (for PR creation)

### Options

```
kaizen "prompt" [-C /path/to/repo] [--max-iterations N] [--max-review-rounds N] [--no-worktree]
```

| Option | Meaning |
|---|---|
| `-C, --directory` | Path to git repo (default: current dir) |
| `--max-iterations` | Max work iterations |
| `--max-review-rounds` | Max review rounds |
| `--no-worktree` | Work in current tree instead of a worktree |

## How it works

```
                    kaizen "add --json flag"
                               │
                   ┌───────────────────────────┐
                   │  SETUP                     │
                   │  fetch origin/main          │
                   │  create branch kaizen/<slug>│
                   │  create isolated worktree   │
                   └────────────┬──────────────┘
                                │
                ┌───────────────────────────────┐
                │  WORK                         │
                │  agent reads prompt + notes    │
                │  makes changes, commits        │
                │  repeats until done or limit   │
                └───────────────┬───────────────┘
                                │
                   ┌────────────────────────────┐
                    │  REVIEW                     │
                    │  agent reviews diff          │
                    │  returns structured findings │
                    │  ┌────────────────────────┐ │
                    │  │  auto-fix findings?     │ │
                    │  │  → agent fixes, re-review│ │
                    │  └────────────────────────┘ │
                    └────────────┬───────────────┘
                                │
                      ┌──────────────────┐
                      │  SHIP            │
                      │  push to origin  │
                      │  create PR (gh)  │
                      └────────┬─────────┘
                               │
                      ┌──────────────────┐
                      │  CLEANUP         │
                      │  remove worktree │
                      │  delete branch   │
                      │  print PR URL    │
                      └──────────────────┘
```

### Findings

The review step returns structured findings with actions:

| Action | Meaning | Who handles it |
|---|---|---|
| `no-op` | Informational | Silently accepted |
| `auto-fix` | Mechanical fix (typos, dead code, missing error handling, behavioral changes) | Agent fixes automatically |

### Worktree isolation

By default kaizen creates a git worktree for each run. Your working directory stays clean while the agent operates in isolation. The worktree is removed after the run completes.

```
my-project/                    ← your tree, untouched
  .kaizen/worktrees/<slug>/    ← agent works here
```

The opencode server runs in the main repo directory; individual sessions point at the worktree. This lets opencode see the full project context while the agent modifies only the isolated branch.

### Iteration memory

The work phase uses a `notes.md` file to carry context across iterations. Each iteration the agent reads prior notes, does one incremental piece of work, and appends its summary. Failed iterations still record learnings.

## Server

kaizen is a pure client — it does **not** start or manage an opencode server. You need one running before invoking kaizen.

### Start a server

```bash
opencode serve --hostname 127.0.0.1 --port 4096 &
```

### Auto-discovery

kaizen auto-discovers a running `opencode serve` process by:

1. Finding processes matching `opencode serve` via `pgrep`
2. Parsing the `--port` from each process's command line
3. Preferring servers whose working directory matches the project
4. Health-checking each candidate
5. Using the first healthy server found

If no server is found:

```
Error: No opencode server found.
Start one with: opencode serve --hostname 127.0.0.1 --port 4096
```

### Batch work

For batch work, start one server and reuse it across runs:

```bash
opencode serve --hostname 127.0.0.1 --port 4096 &
kaizen "fix issue #1"
kaizen "fix issue #2"
```

Each kaizen run creates its own worktree and uses per-iteration sessions, so multiple runs can share a server safely. However, each session makes concurrent LLM API calls — running more than 3–4 kaizen processes in parallel may trigger API rate limits. kaizen retries transient HTTP 500 errors automatically (up to 4 retries with exponential backoff), but sustained rate limiting requires reducing the number of parallel runs.

### Checking server status

```bash
curl -sf http://127.0.0.1:4096/global/health
```

A `200` response means the server is ready.

### Stopping the server

```bash
kill %1    # if launched with & in the current shell
```

## Configuration

`~/.kaizen/config.json` (created automatically on first run):

```json
{
  "max_work_iterations": null,
  "max_review_rounds": 3,
  "max_consecutive_failures": 3,
  "use_worktree": true
}
```

## Project structure

```
src/kaizen/
  __init__.py         # package init
  __main__.py         # `python -m kaizen` support
  agent.py            # opencode HTTP client + auto-discovery
  git.py              # git operations
  config.py           # ~/.kaizen/config.json
  run.py              # run state persistence (single JSON per run)
  orchestrator.py     # work iteration loop
  work_prompt.py      # iteration prompt builder
  findings.py         # finding types and action classification
  review_prompt.py    # review + fix prompt builders
  loop.py             # coordinates work → review → fix → ship
  steps.py            # review, push, and PR steps
  cli.py              # CLI entry point
```

## License

MIT
