---
description: "Refresh committed benchmark tool snapshots and provenance without changing benchmark semantics accidentally."
argument-hint: "Optional: mcp, rosetta, skills, all, or dry-run"
agent: "agent"
tools: [read, search, edit, execute, todo]
---

# Refresh Benchmark Snapshots Prompt

Use this prompt when refreshing `data/mcp_tools.json`, `data/rosetta_tools.json`,
`data/skills.json`, or their derived CSV results.

## Procedure

1. Read [AGENTS.md](../../AGENTS.md), [README.md](../../README.md), and
   [data/PROVENANCE.md](../../data/PROVENANCE.md).
2. Confirm which snapshot source is being refreshed: `mcp`, `rosetta`, `skills`,
   or `all`.
3. Prefer environment variables over local paths:
   - `MIKROTIK_MCP_PATH` for `data/mcp_tools.json`.
   - `ROSETTA_BIN` for rosetta MCP stdio.
   - `ROUTEROS_SKILLS_DIR` for skill discovery.
   - `CHR_IMG` for RouterOS CHR validation.
4. Run the narrowest refresh command available. Use `./run_all.sh --refresh-tools`
   only when all tool snapshots should be re-extracted.
5. Re-run the affected metric scripts or `./run_all.sh` when outputs should be
   regenerated.
6. Inspect diffs for every changed `data/*.json` and `data/*.csv` file before
   finishing.
7. Update [data/PROVENANCE.md](../../data/PROVENANCE.md) when source checkout,
   version, command, path, or capture method changes.

## Guardrails

- Do not hard-code local checkout paths in code or docs.
- Do not commit generated caches, local virtual environments, QEMU logs, or live
  router data.
- Do not treat snapshot churn as meaningful benchmark movement until the diff is
  explained.
- Do not update `REPORT.md` claims unless the refreshed metrics actually change
  the interpretation.

## Done Output

Report:

- commands run and whether they succeeded.
- snapshots/results changed.
- provenance updates made.
- any required local dependencies that were missing.
- whether `./run_all.sh` passed or why it was intentionally not run.