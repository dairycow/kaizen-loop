---
description: Install or update kaizen from PyPI via uv tool
---

Install or update kaizen from PyPI using `uv tool`.

Steps:
1. Check if kaizen is already installed by running `kaizen --version`
2. Install or update using `uv tool install kaizen-loop --reinstall --force`
3. Verify the installation by running `kaizen --version`
4. Check if opencode is installed and if not, install it using `curl -fsSL https://opencode.ai/install | bash`
5. Verify opencode is working by running `opencode --version`