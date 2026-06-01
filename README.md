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
- **Live pilots (grounded, preliminary):** see
  [`docs/REPORT_LIVE.md`](docs/REPORT_LIVE.md) (Claude + closed-loop CHR),
  [`docs/REPORT_LIVE_GPT.md`](docs/REPORT_LIVE_GPT.md) (cross-vendor GPT), and
  [`docs/AGENTIC_FUTURES.md`](docs/AGENTIC_FUTURES.md) (forward recommendations).
  - The "weird syntax" trap (`type=blackhole`) is **structural, not a small-model
    artifact**: it persists across a **4-rung Claude scale ladder to the frontier
    (Opus 4.8: 0/9)** _and_ across every GPT tier — invariant to vendor **and**
    scale. Only **2 of 36** ladder generations reached the device-valid bare
    `blackhole` flag.
  - The device disagreed with the **gold itself**: `blackhole=yes` is
    device-rejected, yet `/console/inspect` accepted it — an _inspect-vs-runtime
    gap_. Gold corrected to the bare flag; only a device-grounded run tier caught
    it. **This is the strongest argument for an explain → validate → run loop.**
  - **Augmentation is model-dependent:** it lifts weak models (and erases their
    fabrication) but is net-neutral-to-negative for strong ones (it invites
    over-specification). Not a constant win.

> Scope: RouterOS **7.22.1**. Token counts are a GPT-family proxy
> (`tiktoken o200k_base`) — comparative, not absolute. Live-pilot cells are small
> N (the ladder uses k=3 repeats for a stability band); read column patterns and
> bands, not single cells.

Related tikoci projects under test/reference:
[rosetta](https://github.com/tikoci/rosetta) ·
[routeros-skills](https://github.com/tikoci/routeros-skills) ·
[quickchr](https://github.com/tikoci/quickchr) (CHR/QEMU) ·
[restraml](https://github.com/tikoci/restraml) (REST schema) ·
[centrs](https://github.com/tikoci/centrs) (scoped-verb RouterOS MCP / runner — the in-progress alternative to a 166-tool execution MCP) ·
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
| **Live pilot** — real `copilot -p`/`claude -p` generation, scored + CHR-validated | `harness/live/run_live.py`, `run_gpt_matrix.py`, `run_live_ladder.py` | `data/live_pilot.*`, `live_gpt_matrix.*`, `live_ladder.*` |

The first six metrics are **structural** (no model calls). The live pilots are the
only ones that call a model; they are preliminary (see
[`docs/REPORT_LIVE.md`](docs/REPORT_LIVE.md), [`REPORT_LIVE_GPT.md`](docs/REPORT_LIVE_GPT.md),
and [`AGENTIC_FUTURES.md`](docs/AGENTIC_FUTURES.md)) and not part of `./run_all.sh`.

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

## Live pilot (landed)

A first **grounded live-agent pilot** is now committed. It runs `copilot -p`
(the only live backend available in the dev environment), contrasts `baseline`
vs `rosetta` context over 6 representative tasks, caches every call by prompt
hash, and adds a closed-loop CHR demo via `quickchr exec`.

- Harness: [`harness/live/run_live.py`](harness/live/run_live.py)
  (`backends.py`, `contexts.py`, `adapter.py`).
- Artifacts: `data/live_pilot.csv`, `data/live_pilot.jsonl`,
  `data/live_chr_demo.csv` (`data/live_cache/` is git-ignored).
- Findings: [`docs/REPORT_LIVE.md`](docs/REPORT_LIVE.md) — clearly marked **PILOT
  evidence (n=6, single backend)**, kept separate from structural metrics.

The headline grounded result: on `route-blackhole` the device (CHR 7.23)
**rejected the corpus gold** (`blackhole=yes`) and **accepted the rosetta-guided
output** (bare `blackhole` flag) — the static scorer had it backwards. Only
device execution surfaced the oracle bug. This is the concrete case for an
explain → validate → **run** loop and for scoped execution CLIs (`quickchr` /
`centrs`) as a real validation tier rather than a 166-tool MCP firehose.

Reproduce (uses cache, no live calls if present):

```bash
.venv/bin/python harness/live/run_live.py --dry-run   # prompts only
.venv/bin/python harness/live/run_live.py             # writes data/live_pilot.*
```

## Future live benchmark direction

The next milestone is not a large model bake-off. It is a cheap, auditable live
verification loop that proves the harness can ask a local CLI-backed agent for
RouterOS commands, score them, validate them, and save enough metadata to replay
or explain the result.

The preferred path is:

1. Build `prompt-only` dry runs from `tasks/corpus.yaml` and `approaches.yaml`.
2. Run a tiny `live-generation` pilot: one backend, 3 to 5 tasks, no execution on
  a router, final commands scored and syntax-validated.
3. Expand to a small `mini-matrix`: 2 to 3 approaches across a fixed task subset,
  capped at roughly 12 model calls by default.
4. Add `closed-loop-chr` scenarios only after prompt construction, result
  capture, and CLI invocation are stable. Use disposable CHR fixtures,
  `/console/inspect` pre-validation, and readback checks.

`claude -c` or `copilot -c` may be useful for early pilots, but benchmark-quality
runs should prefer a non-interactive command that prints an answer and exits.
Every live result should record the exact command, prompt hash, stdout, stderr,
exit code, backend label, final commands, validation errors, retries, and whether
the run is pilot evidence or benchmark-quality data.
