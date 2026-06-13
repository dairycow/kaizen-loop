import json
import os
from pathlib import Path


DEFAULT_CONFIG = {
    "max_work_iterations": None,
    "max_review_rounds": 3,
    "max_consecutive_failures": 3,
    "use_worktree": True,
}


def config_path() -> str:
    return os.path.expanduser("~/.kaizen/config.json")


def load_config() -> dict:
    path = config_path()
    if os.path.exists(path):
        try:
            with open(path) as f:
                cfg = json.load(f)
            return {**DEFAULT_CONFIG, **cfg}
        except (json.JSONDecodeError, OSError):
            pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Path(path).write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n")
    return {**DEFAULT_CONFIG}
