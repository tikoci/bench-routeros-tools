---
description: "Use when implementing future live benchmark adapters, CLI model runners, live-agent result capture, or live harness documentation."
applyTo: "harness/live/**/*.py,harness/run_agent.py,docs/LIVE_AGENT_HARNESS.md"
---

# Live agent harness

Read `docs/LIVE_AGENT_HARNESS.md` before changing the live harness surface.
Live benchmarks should reuse the existing corpus, scorer, and command validator
rather than growing a separate benchmark path.

- Keep `AgentAdapter.run_task(task, approach) -> AgentRunResult` as the adapter
  boundary unless a measured live-run need forces a change.
- Prefer non-interactive CLI modes for repeatable runs. Do not treat unstable or
  interactive CLI flags as benchmark data.
- Persist enough metadata to replay or audit a run: exact executable and args,
  approach, task id, prompt hash, stdout, stderr, exit code, final commands,
  validation errors, retries, tool/retrieval calls, and refusal/blocker state.
- Default live runs to disposable CHR fixtures. Keep RouterOS write/destructive
  tasks behind an explicit `--allow-mutation` style gate.
- Validate final commands with `/console/inspect` when a CHR is available, then
  feed them through the existing scorer path.
- The ladder (`run_live_ladder.py`) compares 4 conditions: `baseline`,
  `rosetta-context`, `skills-context` (offline, single-turn) and `vendordoc-steer`
  (**agentic, web-enabled** — steers the agent to fetch `manual.mikrotik.com`). Web
  access is per-approach (`call_claude(allow_web=...)`): only `vendordoc-steer` gets
  it; every other approach explicitly disallows web so the comparison isolates
  injected context. Keep that gating — it is the experiment's control.
- Some tasks are `removed_capability` traps with no satisfiable gold (the v6 form
  has no v7 equivalent; device-verify before asserting one, cf.
  `data/route_unreachable_device_verify.csv`). They score `trap-fell`/`trap-avoided`,
  not against a gold; tools that iterate the corpus must tolerate empty
  `gold_commands` (fall back to `acceptable_variants`/`relevant_areas`).
- When only scoring changes (a scorer rule or a gold), re-label captured runs with
  `harness/live/rescore.py` (no model calls) — do **not** re-run the model or use
  `backfill_cells.py` (which re-runs and writes a stale CSV/matrix schema).
- Save prompts and outputs, not credentials, device inventories, WinBox CDBs,
  Dude databases, or packet captures.