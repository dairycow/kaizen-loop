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
6. Read the config at `~/.kaizen/config.json` (create it if it does not exist). Compare its keys against the current defaults defined in `src/kaizen/config.py` (`DEFAULT_CONFIG`). If any default key is missing from the device config, add it with the default value, preserving all existing keys. Write the merged config back to `~/.kaizen/config.json` only if changes were made.