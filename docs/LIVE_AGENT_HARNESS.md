# Live Agent Harness Roadmap

The current benchmark is structural: it measures context cost, tool-selection
ambiguity, retrieval reachability, command syntax validity, scorer behavior, and
capability/safety tradeoffs without calling a model backend.

Live runs should reuse the same `tasks/corpus.yaml` and scorer, but add a model
adapter that produces candidate RouterOS commands from an approach-specific
prompt/context bundle.

## Adapter seam

The intended interface is:

```python
class AgentAdapter:
    def run_task(self, task: dict, approach: str) -> AgentRunResult:
        ...
```

`harness/live/adapter.py` contains the initial interface plus CLI adapter stubs.
The stubs are deliberately conservative: they build a subprocess shape but do
not yet claim a stable `claude` or `copilot` invocation contract.

## CLI entrypoints

Prefer non-interactive CLI modes for benchmark runs. `claude -c` and
`copilot -c` are useful for continuing interactive sessions, but a repeatable
harness should prefer print/non-interactive forms once each CLI's stable flags
are confirmed. Store the exact command, stdout, stderr, exit code, and prompt
hash with each result.

## Near-term `/fleet` plan

The first live work should be deliberately small and cheap. Use the `/fleet`
workspace prompt to implement or run this ladder:

1. `prompt-only`: materialize prompts for selected tasks and approaches without
    calling a model. **Implemented:** `harness/live/run_live.py --dry-run`.
2. `live-generation`: one backend, 3 to 5 tasks, no router execution. Score final
    commands and run syntax validation. **Implemented:** `harness/live/run_live.py`
    runs baseline vs rosetta-context over a balanced 6-task subset with an
    isolated `claude -p`, scores via `lib.scorer`, and validates each command on
    the CHR `/console/inspect` validator. Writes `data/live_pilot.csv` and a
    per-run `data/live_pilot.jsonl`. See REPORT.md §8.
3. `mini-matrix`: 2 to 3 approaches across a fixed task subset. **Implemented:**
    `run_live.py` defaults to 3 conditions (baseline / rosetta-context /
    skills-context) × 2 models (Haiku 4.5 + Sonnet 4.6) × 6 tasks = 36 calls
    (~$0.79). Override with `--models a,b` / `LIVE_MODELS` / `LIVE_TASKS`. See
    REPORT.md §8. Natural next step: repeat each cell k times for a variance band.
4. `closed-loop-chr`: disposable CHR only, `/console/inspect` pre-validation,
    optional mutation behind an explicit allow flag, and readback verification.

### Isolation contract used by `run_live.py` (rung 2)

To stop the local environment's globally-installed routeros-* skills and rosetta
MCP from silently augmenting the "baseline" condition, each `claude -p` call runs
with `--disable-slash-commands` (no skills), `--strict-mcp-config` (no MCP unless
explicitly passed), `--setting-sources ''` (no user/project settings), and from a
scratch `/tmp` cwd (no project `CLAUDE.md`). The only deliberate difference
between conditions is the text injected into the prompt. Residual base scaffolding
(Claude Code's ~28K-token system prompt, possibly `~/.claude` memory) is constant
across conditions, so the **delta** is the trustworthy signal, not the absolute
rate — record and report it that way.

Treat `claude -c` and `copilot -c` as pilot interfaces until their exact local
non-interactive behavior is documented. Before spending model calls, inspect CLI
help/version output and record the selected invocation contract.

Representative full scenarios should include syntax-only command generation,
state-aware read tasks, safe CHR write/readback tasks, and refusal/blocker cases.
Prefer a small balanced set over broad corpus coverage until artifact capture and
scoring are stable.

## Result shape

Live adapters should emit:

- final RouterOS commands
- retrieval/tool calls used
- validation errors and retries
- live-state reads
- completion marker or refusal/blocker

Then feed the final commands through `lib.scorer.predict_label()` and, when
possible, `harness/validate_commands.py`.

## Safety rules

- Default live tasks to CHR fixtures, not production routers.
- Keep write/destructive tasks behind an explicit `--allow-mutation` flag.
- Validate commands with `/console/inspect` before execution.
- Save prompts and outputs, not credentials or real device inventories.
