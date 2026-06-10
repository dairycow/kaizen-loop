# kaizen-loop

Continuous code improvement: autonomous work → review → fix → ship.

A zero-dependency Python harness that drives [opencode](https://opencode.ai) through the full cycle of writing, validating, and shipping code — with as little human-in-the-loop as possible.

## Quick start

```bash
# Install
pip install -e .

# Run
kaizen "add a --json flag to the status command"
```

That's it. kaizen creates an isolated branch, the agent does the work, the pipeline reviews it, fixes what it can, pushes to origin, and opens a PR.

### Prerequisites

- Python 3.10+
- [opencode](https://opencode.ai) (`curl -fsSL https://opencode.ai/install | bash`)
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
| `--opencode-bin` | Path to opencode binary |

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
                   │  │  ask-user findings?     │ │
                   │  │  → escalate to human    │ │
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
| `auto-fix` | Mechanical fix (typos, dead code, missing error handling) | Agent fixes automatically |
| `ask-user` | Changes product behavior or challenges deliberate intent | Escalated to you |

You only interact when `ask-user` findings appear. Everything else is automated.

### Worktree isolation

By default kaizen creates a git worktree for each run. Your working directory stays clean while the agent operates in isolation. The worktree is removed after the run completes.

```
my-project/                    ← your tree, untouched
  .kaizen/worktrees/<slug>/    ← agent works here
```

The opencode server starts in the main repo directory; individual sessions point at the worktree. This lets opencode see the full project context while the agent modifies only the isolated branch.

### Iteration memory

The work phase uses a `notes.md` file to carry context across iterations. Each iteration the agent reads prior notes, does one incremental piece of work, and appends its summary. Failed iterations still record learnings.

## Configuration

`~/.kaizen/config.json` (created automatically on first run):

```json
{
  "max_work_iterations": null,
  "max_review_rounds": 3,
  "max_consecutive_failures": 3,
  "opencode_bin": "opencode",
  "use_worktree": true
}
```

## Project structure

```
src/kaizen/
  agent.py            # opencode HTTP server integration
  git.py              # git operations
  config.py           # ~/.kaizen/config.json
  run.py              # run state + notes
  orchestrator.py     # work iteration loop
  work_prompt.py      # iteration prompt builder
  findings.py         # finding types and action classification
  review_prompt.py    # review + fix prompt builders
  loop.py             # coordinates work → review → fix → ship
  cli.py              # CLI entry point
  steps/              # review, push, pr
```

## License

MIT
