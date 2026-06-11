---
description: Bump version, tag, push, and publish a new release via CI
---

Cut a new release of this package.

Steps:
1. Read the current version from `pyproject.toml` and `src/kaizen/__init__.py` — they must match
2. Determine the next version bump (patch, minor, or major) based on the changes since the last tag. Use `git log LAST_TAG..HEAD --oneline` to review changes
3. Update the version in both `pyproject.toml` and `src/kaizen/__init__.py`
4. Commit with message `release: vX.Y.Z`
5. Create a git tag `vX.Y.Z`
6. Push the commit and tag to origin
7. Monitor the GitHub Actions release workflow until it completes (success or failure)
8. If successful, reinstall locally with `uv tool install kaizen-loop --reinstall --force` and verify with `kaizen --version`
9. If failed, diagnose the failure from the workflow logs and report back

Do NOT skip any of these steps. Always verify both version files are in sync before committing.
