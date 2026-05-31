#!/usr/bin/env bash
# Run the full RouterOS agent-support benchmark.
#
# Deterministic metrics (token cost, tool ambiguity, proxies, scorer replay,
# capability matrix) always run. Retrieval (needs rosetta + Bun) and command
# validity (prefers a CHR VM, falls back to rosetta static schema) degrade
# gracefully if their dependencies are absent.
#
# Usage:
#   ./run_all.sh                 # run all metrics
#   ./run_all.sh --refresh-tools # re-extract mcp/rosetta tool artifacts first
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
PY=".venv/bin/python"

if [ ! -x "$PY" ]; then
  echo "error: benchmark venv missing. Set it up:"
  echo "  python3 -m venv .venv"
  echo "  .venv/bin/pip install -e ."
  exit 1
fi

run() {
  echo
  echo "==================================================================="
  echo "== $1"
  echo "==================================================================="
  shift
  "$@"
}

if [ "${1:-}" = "--refresh-tools" ]; then
  run "refresh: external tool schemas" "$PY" harness/refresh_tools.py
fi

run "A. token / context cost"        "$PY" harness/token_cost.py
run "G. tool-selection ambiguity"    "$PY" harness/tool_ambiguity.py
run "proxies (routing signal, budget)" "$PY" harness/proxies.py
run "agent replay + capability matrix" "$PY" harness/run_agent.py
run "C. rosetta retrieval quality"   "$PY" harness/retrieval_eval.py
run "D. command validity (CHR/static)" "$PY" harness/validate_commands.py

echo
echo "Done. Raw results in data/*.csv"
echo "Read REPORT.md for the analysis."
