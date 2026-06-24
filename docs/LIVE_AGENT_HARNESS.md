# Live Agent Harness Roadmap

The current benchmark is structural: it measures context cost, tool-selection
ambiguity, retrieval reachability, command syntax validity, scorer behavior, and
capability/safety tradeoffs without calling a model backend.

Live runs should reuse the same `tasks/corpus.yaml` and scorer, but add a model
adapter that produces candidate RouterOS commands from an approach-specific
prompt/context bundle.

## Live conditions (`run_live_ladder.py`)

The Claude scale ladder compares **four** conditions per task. The first three are
offline single-turn (the only deliberate difference is injected context); the
fourth is **agentic + live-web** and carries a documented confound — read it as the
realistic vendor-manual workflow, with `rosetta-context` as the closest offline-RAG
comparison.

| condition | what it adds | shape |
|---|---|---|
| `baseline` | task intent only | offline, single-turn |
| `rosetta-context` | rosetta `routeros_search` result text injected | offline, single-turn |
| `skills-context` | always-on skill frontmatter + best-matching SKILL.md body | offline, single-turn |
| `vendordoc-steer` | **steer the agent to fetch `manual.mikrotik.com`** (`llms.txt` + the page `.md`), per MikroTik forum [270916](https://forum.mikrotik.com/t/steering-ai-to-use-new-manual-mikrotik-com/270916) | **agentic, multi-turn, web-enabled** |

`vendordoc-steer` is the only condition given web access (`call_claude(allow_web=True)`
→ `--allowedTools "WebFetch WebSearch"`); every other condition explicitly disallows
web so the comparison isolates injected context, not capability. It is asked to end
with a `SOURCE:` line citing the page it read; the runner parses that into
`cited_source` so a miss can be diagnosed as *steered-but-didn't-fetch* vs
*fetched-but-still-wrong* (the more interesting failure).

## Task types: gold vs removed-capability traps

Most tasks score a candidate against `gold_commands`. One task type has **no
satisfiable gold**: a `removed_capability` trap, where the v6 form a model is primed
to emit has *no* v7 equivalent at its path (device-verified, e.g.
`route-unreachable` → `data/route_unreachable_device_verify.csv`). The scorer
(`lib/scorer.py`) handles it explicitly: `trap-fell` (emitted a removed v6 form per
`trap_tokens`) vs `trap-avoided` (emitted the documented v7 `acceptable_variants`, or
no command at all = recognized the removal). Corpus-iterating harnesses fall back to
`acceptable_variants`/`relevant_areas` when `gold_commands` is empty.

## Re-scoring without re-running

When only the *scoring* changes (a scorer rule or a gold), do **not** re-run the
model. `harness/live/rescore.py` re-applies the current scorer to each captured run's
stored `parsed_commands` and rebuilds `live_ladder.{csv,jsonl,_matrix.csv}` in the
runner's current schema (idempotent for unchanged tasks; prints every label that
moved). Prefer it over `backfill_cells.py`, which re-runs the model *and* writes an
older CSV/matrix schema. Anchor tests for the parse fold and removed-capability
scoring live in `harness/live/test_parse_commands.py` and `test_removed_capability.py`
(`python -m unittest harness.live.test_removed_capability`).

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
