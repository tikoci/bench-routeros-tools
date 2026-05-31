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
- Save prompts and outputs, not credentials, device inventories, WinBox CDBs,
  Dude databases, or packet captures.