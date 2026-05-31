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

