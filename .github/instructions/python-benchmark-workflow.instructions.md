---
description: "Use when editing Python benchmark harness code, pyproject metadata, requirements, or shell entrypoints. Covers uv-first setup and validation."
applyTo: "**/*.py,pyproject.toml,requirements.txt,run_all.sh,.github/workflows/*.yml,.github/workflows/*.yaml"
---

# Python benchmark workflow

This project is a Python 3.11+ benchmark harness with committed data snapshots.
Prefer modern Python tooling without breaking the documented fallback path.

- Prefer `uv venv` plus `uv pip install -e .` for local setup when `uv` is
  available.
- Keep `python3 -m venv .venv` plus `.venv/bin/pip install -e .` working for
  portability and CI/debug instructions.
- Run the narrowest useful metric script while editing, then `./run_all.sh`
  before finishing changes that affect benchmark results.
- Do not hard-code sibling checkout paths. Use `MIKROTIK_MCP_PATH`,
  `ROSETTA_BIN`, `ROUTEROS_SKILLS_DIR`, and `CHR_IMG`.
- Keep scripts deterministic by default. Networked refreshes should remain
  explicit, such as `./run_all.sh --refresh-tools`.