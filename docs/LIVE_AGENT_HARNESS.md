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
    calling a model.
2. `live-generation`: one backend, 3 to 5 tasks, no router execution. Score final
    commands and run syntax validation.
3. `mini-matrix`: 2 to 3 approaches across a fixed task subset, capped at about
    12 model calls unless the user specifies another budget.
4. `closed-loop-chr`: disposable CHR only, `/console/inspect` pre-validation,
    optional mutation behind an explicit allow flag, and readback verification.

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
