---
description: "Implement or run a small, budget-bounded live RouterOS agent benchmark fleet using the existing corpus, scorer, and validator."
argument-hint: "Optional: backend, budget, approaches, task count, dry-run/live"
agent: "agent"
tools: [read, search, edit, execute, todo]
---

# Fleet Live Benchmark Prompt

Use this prompt to move from structural proxy metrics toward a small live
verification run without turning the benchmark into an open-ended model-spend
exercise.

## Start Here

1. Read [AGENTS.md](../../AGENTS.md), [README.md](../../README.md), and
   [docs/LIVE_AGENT_HARNESS.md](../../docs/LIVE_AGENT_HARNESS.md).
2. Load relevant path instructions before editing: live harness, Python workflow,
   benchmark data, and RouterOS grounding.
3. Confirm the requested mode:
   - `dry-run`: build prompts, task selections, output schema, and commands only.
   - `pilot`: run the smallest useful live generation sample.
   - `mini-matrix`: compare a few approaches across a fixed task subset.
   - `chr-loop`: validate and optionally execute against disposable CHR fixtures.

## Default Budget

When the user does not specify a budget, cap the first pass at 12 model calls:

- 1 backend unless the user explicitly asks for multiple.
- 3 to 5 tasks for `pilot`.
- 2 to 3 approaches x 3 tasks for `mini-matrix`.
- At most 1 retry per task, and only when the validation error is actionable.
- Reuse saved prompts and outputs; do not rerun completed calls unless the user
  asks for `--force`-style behavior.

## Backend Choice

Prefer a stable non-interactive CLI mode that prints the model answer and exits.
If the only practical local path is `claude -c` or `copilot -c`, treat the result
as a pilot run until the exact invocation contract is documented. Record the full
command, prompt hash, stdout, stderr, exit code, model/backend label, and any
manual setup assumptions.

Before spending model calls, cheaply inspect local CLI help/version output and
write down the chosen command shape. Do not use interactive sessions for a
repeatable benchmark unless there is no better local interface and the limitation
is clearly recorded.

## Scenario Ladder

Build in this order:

1. `prompt-only`: materialize approach-specific prompts from `tasks/corpus.yaml`
   and verify they contain the expected context.
2. `live-generation`: ask the model for RouterOS CLI commands only, then score
   with `lib.scorer.predict_label()` and validate syntax with
   `harness/validate_commands.py`.
3. `retrieval-aware`: include rosetta/skills context according to
   `approaches.yaml`, and record any retrieval/tool calls the backend exposes.
4. `closed-loop-chr`: use a disposable CHR, validate final commands with
   `/console/inspect`, execute only safe or explicitly allowed mutations, and
   verify state with readback commands.

Prefer representative true benchmark scenarios over broad coverage at first:

- syntax-only command generation with no device state dependency.
- read/state-aware task where the answer depends on inspecting RouterOS state.
- safe write task on disposable CHR with pre-validation and readback.
- refusal or blocker task where a production-router credential, destructive
  action, or missing state should stop the agent.

## Safety And Data

- Default to disposable CHR fixtures, not production routers.
- Keep mutation behind an explicit `--allow-mutation` gate.
- Never save credentials, device inventories, WinBox CDBs, Dude databases,
  packet captures, or customer hostnames.
- If committing live artifacts, update [data/PROVENANCE.md](../../data/PROVENANCE.md)
  and keep result files reproducible or clearly marked as live-run snapshots.

## Done Output

Finish with a concise report containing:

- mode, backend, budget, approaches, task ids, and exact commands run.
- model-call count and any skipped calls.
- result artifact paths.
- score/validation summary and notable failures.
- whether results are pilot evidence or benchmark-quality data.
- next smallest step.