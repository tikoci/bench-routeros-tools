---
description: "Analyze RouterOS benchmark CSV outputs and keep conclusions aligned with structural-vs-live evidence boundaries."
argument-hint: "Optional: report, live-run path, approach comparison, or metric focus"
agent: "agent"
tools: [read, search, edit, execute, todo]
---

# RouterOS Benchmark Analysis Prompt

Use this prompt to interpret benchmark outputs, update narrative docs, or compare
structural results with a live-run pilot.

## Inputs To Read

1. [README.md](../../README.md) for the metric map and caveats.
2. [REPORT.md](../../REPORT.md) for the current interpretation.
3. [approaches.yaml](../../approaches.yaml) for approach definitions.
4. Relevant `data/*.csv` files for metric outputs.
5. Live-run artifacts, if supplied by the user or produced by `/fleet`.

## Analysis Rules

- Keep structural metrics separate from live-agent success rates.
- Treat token counts as comparative GPT-family proxies, not absolute costs.
- Treat lexical routing and tool-ambiguity metrics as transparent proxies, not
  model-choice traces.
- Treat rosetta retrieval rank granularity as coarse; emphasize hit and
  reconstruction signals.
- Use command validity as scorer/validator grounding, not as proof that an agent
  solved a task.
- When live runs exist, label them as pilot evidence unless backend invocation,
  prompt construction, artifact schema, and task sampling are stable.

## Useful Checks

- Re-run `./run_all.sh` before changing claims when data files may be stale.
- Compare changed CSVs against `REPORT.md` tables and recommendations.
- Look for regressions in capability matrix, command validity, and context budget
  before celebrating small retrieval or token improvements.
- For live pilots, separate failures into prompt construction, backend refusal,
  invalid RouterOS syntax, wrong semantic command, missing state, and harness
  failure.

## Done Output

Produce a concise analysis with:

- what changed or what was compared.
- the strongest supported conclusion.
- caveats and residual risk.
- docs or data files updated.
- the next measurement that would most reduce uncertainty.