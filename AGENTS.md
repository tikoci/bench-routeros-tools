# Agent Instructions

This repo is the standalone benchmark for RouterOS agent-support strategies. It
evaluates external tools (`mikrotik-mcp`, `rosetta`, and `routeros-skills`) from
the outside; do not make the benchmark depend on being checked out inside any
one of those repos.

Keep this file short. Put durable path-specific rules in
`.github/instructions/*.instructions.md` with narrow `applyTo` globs.

## Start points

- [README.md](README.md) explains setup, metrics, and graceful degradation.
- [REPORT.md](REPORT.md) is the current benchmark interpretation and caveats.
- [docs/LIVE_AGENT_HARNESS.md](docs/LIVE_AGENT_HARNESS.md) is the roadmap for
  future live-agent runs.
- [data/PROVENANCE.md](data/PROVENANCE.md) records how committed tool snapshots
  were captured.

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
- Future live benchmark work belongs under `harness/live/` and the live harness
  docs. Preserve reproducibility: record prompts, command lines, stdout, stderr,
  exit codes, prompt hashes, and validation metadata.
- Prefer `uv`/`uvx` for new Python environment and tool invocations when
  available, while keeping the existing `.venv` workflow usable as a fallback.
- Never put real router credentials, WinBox CDBs, Dude databases, packet
  captures, or customer hostnames in fixtures or prompts.

## Validation

Use:

```bash
uv venv
uv pip install -e .
./run_all.sh
```

If `uv` is unavailable, use the portable fallback:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
./run_all.sh
```

`validate_commands.py` should use CHR + `/console/inspect` when QEMU and a CHR
image are available, and degrade to rosetta static validation otherwise.

