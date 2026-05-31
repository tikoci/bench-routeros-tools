# RouterOS Agent-Support Benchmark

A repeatable harness that measures **how best to help an AI agent work with
MikroTik RouterOS**. RouterOS training data is sparse and its CLI is idiosyncratic,
so several augmentation strategies exist. This benchmark grounds the choice
between them in numbers instead of intuition.

> **This is a _structural_ benchmark, not an "effectiveness winner" benchmark.**
> Without a model API wired in, it does not auto-run end-to-end agent success.
> It measures the structural properties that determine effectiveness (context
> cost, tool-selection burden, retrieval coverage, command validity, capability,
> safety) and ships a pluggable harness so live-agent success can be added later.
> A small **live pilot** (`claude -p`) is now wired in on top of that.
> See [`REPORT.md`](REPORT.md) for the analysis and the tradeoff-framed
> recommendation.

## TL;DR — results at a glance (2026-05-31)

A 10,000-foot view of what the data says. Full analysis + caveats in
[`REPORT.md`](REPORT.md); every claim traces to a CSV under `data/`.

- **No single winner — it's a cost/capability tradeoff.** Compare _within_ a
  capability tier (knowledge vs execution), not across.
- **For read-only/planning, [rosetta](https://github.com/tikoci/rosetta) is the
  efficient frontier:** ~6.3K always-on tokens buys retrieval that surfaces the
  right command for **89%** of tasks (structural) and reconstructs the gold path
  for **100%**. Read-only, version-aware, safe.
- **For live mutation, [`mikrotik-mcp`](https://github.com/jeff-nasseri/mikrotik-mcp)
  is uniquely capable but heavy:** its **166** SSH tools cost **~28K always-on
  tokens** (4.5× rosetta, 25× skills), an avg **36/166** tools lexically match
  each task, the right tool is a clear top-3 pick only **62%** of the time, and
  **27** tools are destructive with no dry-run. Token cost is the visible symptom;
  **tool-selection ambiguity and destructive-tool proximity** are the deeper risk.
- **Don't stack everything.** `mcp+rosetta+skills` is ~40K tokens after one task —
  doesn't fit a 32K budget. Additive in capability, additive in confusion.
- **Recommended architecture: an `explain → validate → run` split** — rosetta(±
  [skills](https://github.com/tikoci/routeros-skills)) to plan, `/console/inspect`
  to validate, a _small scoped_ execution surface to apply. Not the 166-tool
  firehose.
- **Live pilot (preliminary, 2 models × 3 conditions × 6 tasks):**
  - The "weird syntax" error (`type=blackhole` instead of `blackhole=yes`) is
    **not** a small-model artifact — **both Haiku 4.5 and Sonnet 4.6 hallucinate
    it from training.** Strongest argument that a grounding/validation layer earns
    its keep _even as base models improve_.
  - **Augmentation helps a weak model, but is net-neutral-to-negative for a strong
    one** on common tasks (extra context invited over-specification). Value of
    augmentation is model- and task-dependent.
  - The committed structural retrieval number (89% hit@5) **overstates** practical
    usefulness for natural-language intents whose path segments are common words —
    a measurement caveat the live loop surfaced.

> Scope: RouterOS **7.22.1**. Token counts are a GPT-family proxy
> (`tiktoken o200k_base`) — comparative, not absolute. Live-pilot cells are N=1
> (no variance estimate); read column patterns, not single cells.

Related tikoci projects under test/reference:
[rosetta](https://github.com/tikoci/rosetta) ·
[routeros-skills](https://github.com/tikoci/routeros-skills) ·
[quickchr](https://github.com/tikoci/quickchr) (CHR/QEMU) ·
[restraml](https://github.com/tikoci/restraml) (REST schema) ·
[centrs](https://github.com/tikoci/centrs) (MAC-Telnet runner) ·
[m2ir](https://github.com/tikoci/m2ir) (binary formats) ·
external [`mikrotik-mcp`](https://github.com/jeff-nasseri/mikrotik-mcp).

## The six approaches compared

| Config | What it adds | Tier |
|---|---|---|
| `baseline` | nothing (training only) | knowledge |
| `skills` | [routeros-skills](https://github.com/tikoci/routeros-skills) markdown guides | knowledge |
| `rosetta` | [rosetta](https://github.com/tikoci/rosetta) docs-as-RAG MCP | knowledge |
| `skills+rosetta` | both knowledge aids | knowledge |
| `mcp` | external `mikrotik-mcp` snapshot — 166 SSH-execution tools | execution |
| `mcp+rosetta+skills` | everything | execution |

## What it measures

| Metric | Script | Output |
|---|---|---|
| **A** Token / context cost (always-on, activation, marginal) | `harness/token_cost.py` | `data/token_cost*.csv` |
| **G** Tool-selection ambiguity across 166 tools | `harness/tool_ambiguity.py` | `data/tool_ambiguity.csv` |
| **C** rosetta retrieval coverage of gold commands | `harness/retrieval_eval.py` | `data/retrieval.csv` |
| **D** Command syntax validity (gold + decoys) | `harness/validate_commands.py` | `data/command_validity.csv` |
| **B/E/F** Routing-signal, scorer-vs-fixtures, budget sim | `harness/proxies.py`, `harness/run_agent.py` | `data/proxy_*.csv`, `data/agent_replay.csv` |
| Capability matrix (read/validate/write/...) | `harness/run_agent.py` | `data/capability_matrix.csv` |
| **Live pilot** — real `claude -p` generation, scored + CHR-validated | `harness/live/run_live.py` | `data/live_pilot.csv`, `.jsonl` |

The first six metrics are **structural** (no model calls). The live pilot is the
only one that calls a model; it is preliminary (see [`REPORT.md`](REPORT.md) §8)
and not part of `./run_all.sh`.

## Setup

```sh
# from the repo root
uv venv
uv pip install -e .
```

Portable fallback:

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
```

Optional dependencies (the suite degrades gracefully without them):

- **rosetta retrieval** needs [Bun](https://bun.sh) and rosetta at
  `~/GitHub/rosetta`, or set `ROSETTA_BIN=/path/to/rosetta/bin/rosetta.js`.
- **CHR command validation** needs `qemu-system-x86_64` and a CHR image at
  `~/GitHub/chr-armed/Machines/chr-7.22.1-x86.img`, or set
  `CHR_IMG=/path/to/chr.img`. It falls back to rosetta's static schema when no
  VM is reachable.
- **routeros-skills refreshes** default to `~/GitHub/routeros-skills`; override
  with `ROUTEROS_SKILLS_DIR=/path/to/routeros-skills`.
- **mikrotik-mcp refreshes** need `MIKROTIK_MCP_PATH=/path/to/mikrotik-mcp` or
  an installed `mcp_mikrotik` package.

## Run

```sh
./run_all.sh                  # all metrics
./run_all.sh --refresh-tools  # re-extract mcp + rosetta tool schemas first
```

Individual metrics:

```sh
.venv/bin/python harness/token_cost.py
.venv/bin/python harness/tool_ambiguity.py
# ...etc
```

## Agent workflow shortcuts

This repo includes workspace prompt files for the next benchmark-maintenance and
live-verification steps:

| Prompt | Use |
|---|---|
| [`/fleet`](.github/prompts/fleet.prompt.md) | Implement or run a small, budget-bounded live benchmark fleet. Start with dry-run or pilot mode before spending many model calls. |
| [`/refresh-benchmark-snapshots`](.github/prompts/refresh-benchmark-snapshots.prompt.md) | Refresh committed MCP, rosetta, or routeros-skills snapshots and update provenance. |
| [`/routeros-benchmark-analysis`](.github/prompts/routeros-benchmark-analysis.prompt.md) | Interpret CSV outputs or live-pilot artifacts while keeping structural and live evidence separate. |

Path-scoped instructions live under `.github/instructions/`. The important ones
for future live work are
[`live-agent-harness.instructions.md`](.github/instructions/live-agent-harness.instructions.md),
[`python-benchmark-workflow.instructions.md`](.github/instructions/python-benchmark-workflow.instructions.md),
[`benchmark-data.instructions.md`](.github/instructions/benchmark-data.instructions.md),
and
[`routeros-grounding.instructions.md`](.github/instructions/routeros-grounding.instructions.md).

## How the inputs are captured (reproducibility)

The three approaches' context is captured into committed artifacts so token
numbers reproduce without live servers:

- `data/mcp_tools.json` — 166 tool schemas from external `mcp_mikrotik.app`.
- `data/rosetta_tools.json` — 14 tool schemas pulled from rosetta over MCP stdio.
- `data/skills.json` — routeros-skills frontmatter and bodies.

See [`data/PROVENANCE.md`](data/PROVENANCE.md) for snapshot provenance and the
refresh command. By default the suite reads committed snapshots; live checkouts
are only needed for `./run_all.sh --refresh-tools`.

`approaches.yaml` is the single source of truth for what each config "is".
`tasks/corpus.yaml` holds 45 RouterOS **7.22.1** tasks (gold commands + decoys +
state/safety tags). The CHR validator proved all 46 gold command lines are real
RouterOS syntax (it caught one authoring error during development).

## Interpreting results

- **Token counts are a GPT-family proxy** (`tiktoken` `o200k_base`). They are
  comparative across approaches, not absolute for any specific model.
- **Tool-ambiguity and routing-signal use lexical matching** — a transparent
  proxy for selection difficulty, not a model's actual choice.
- **Retrieval rank granularity is coarse** (rosetta returns one combined result
  block); `hit@5` and `explain_reconstructs` are the load-bearing signals.
- **Command validity ≠ effectiveness.** It validates the corpus and the scorer
  oracle, which the future live-agent harness depends on.

See [`REPORT.md`](REPORT.md) for the full analysis. See
[`docs/LIVE_AGENT_HARNESS.md`](docs/LIVE_AGENT_HARNESS.md) for the planned
`claude` / `copilot` live-run adapter seam.

## Future live benchmark direction

The next milestone is not a large model bake-off. It is a cheap, auditable live
verification loop that proves the harness can ask a local CLI-backed agent for
RouterOS commands, score them, validate them, and save enough metadata to replay
or explain the result.

The preferred path is:

1. Build `prompt-only` dry runs from `tasks/corpus.yaml` and `approaches.yaml`.
   → `harness/live/run_live.py --dry-run` does this.
2. ✅ **Done.** A tiny `live-generation` pilot: one backend, ~5 tasks, no router
   execution, final commands scored and syntax-validated.
   → `harness/live/run_live.py` (baseline vs rosetta-context, `claude -p`,
   ~$0.15). See [`REPORT.md`](REPORT.md) §8 for the findings.
3. ✅ **Done.** A small `mini-matrix`: 3 conditions (baseline / rosetta-context /
   skills-context) × 2 models (Haiku 4.5 + Sonnet 4.6) × 6 tasks.
   → `harness/live/run_live.py` (~$0.79). REPORT.md §8.
4. Add `closed-loop-chr` scenarios only after prompt construction, result
  capture, and CLI invocation are stable. Use disposable CHR fixtures,
  `/console/inspect` pre-validation, and readback checks.

`claude -c` or `copilot -c` may be useful for early pilots, but benchmark-quality
runs should prefer a non-interactive command that prints an answer and exits.
Every live result should record the exact command, prompt hash, stdout, stderr,
exit code, backend label, final commands, validation errors, retries, and whether
the run is pilot evidence or benchmark-quality data.
