# Agent Instructions

This repo is the standalone benchmark for RouterOS agent-support strategies. It
evaluates external tools (`mikrotik-mcp`, `rosetta`, and `routeros-skills`) from
the outside; do not make the benchmark depend on being checked out inside any
one of those repos.

## Working rules

- Keep generated caches and local environments out of git (`.venv/`,
  `__pycache__/`, QEMU logs).
- Prefer env vars over hard-coded local paths:
  - `MIKROTIK_MCP_PATH` for refreshing `data/mcp_tools.json`.
  - `ROSETTA_BIN` for rosetta MCP stdio.
  - `ROUTEROS_SKILLS_DIR` for skill discovery.
  - `CHR_IMG` for the RouterOS CHR image used by syntax validation.
- Treat `data/*.json` as input snapshots and `data/*.csv` as reproducible result
  snapshots. If a script rewrites them, inspect the diff before committing.
- Keep the benchmark structural unless a live-agent adapter is explicitly being
  worked on. Do not overclaim model effectiveness from deterministic proxies.
- Never put real router credentials, WinBox CDBs, Dude databases, packet
  captures, or customer hostnames in fixtures or prompts.

## Validation

Use:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
./run_all.sh
```

`validate_commands.py` should use CHR + `/console/inspect` when QEMU and a CHR
image are available, and degrade to rosetta static validation otherwise.

