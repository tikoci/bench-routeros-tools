# RouterOS Agent-Support: Benchmark Report

**Question.** RouterOS training data is sparse and the CLI is "weird," so AI
agents need help. Several ways to provide that help exist — curated skills,
a docs-as-RAG MCP (rosetta), and an execution MCP (mikrotik-mcp) — plus
combinations. Which is the more optimal path, and what should we worry about
besides context window?

**Answer up front (tradeoff-framed, not a single winner).**

- For **read-only assistance under a tight context budget**, `rosetta` is the
  most efficient: ~6.3K always-on tokens buys retrieval that surfaces the right
  command for **89%** of tasks and reconstructs the gold command path for
  **100%**.
- For **live device mutation**, `mcp` is uniquely capable but expensive and
  risky: its 166 tools cost **~28.2K always-on tokens** (4.5× rosetta, 25×
  skills) and impose a real **tool-selection burden** — an average of **36 of
  166 tools** lexically match each task and the correct tool is a clear top-3
  pick only **62%** of the time.
- The promising architecture is a **split**: knowledge/retrieval (rosetta ±
  skills) for *planning and validation*, and a *small, scoped* execution surface
  for *applying* changes — not the 166-tool firehose, and not all three stacked
  (`mcp+rosetta+skills` blows even a 32K post-task budget).

> Scope: RouterOS **7.22.1**. Token counts are a GPT-family proxy
> (`tiktoken o200k_base`) — comparative, not absolute. "Effectiveness"
> conclusions about end-to-end task success are **deferred** to live-agent runs;
> everything below is structural and reproducible today.

---

## 1. Context cost — the headline concern, normalized

Raw always-on cost (what's resident before any task work):

| Approach | Tier | Always-on tokens | Relative |
|---|---|---:|---:|
| baseline | knowledge | 0 | — |
| skills | knowledge | 1,133 | 1× |
| rosetta | knowledge | 6,285 | 6.3× |
| skills+rosetta | knowledge | 7,418 | 6.5× |
| **mcp** | execution | **28,178** | **25×** |
| mcp+rosetta+skills | execution | 35,596 | 31× |

**Marginal cost of adding each component** (the honest framing — what extra
capability you buy per token):

| Transition | Adds | Marginal always-on tokens |
|---|---|---:|
| baseline → skills | skill frontmatter | +1,133 |
| baseline → rosetta | 14 tool schemas | +6,285 |
| baseline → mcp | 166 tool schemas | +28,178 |
| mcp → mcp+rosetta+skills | rosetta + skills | +7,418 |

Two things to note so the comparison stays fair:

1. **These are different capability tiers.** "skills are cheaper than mcp" is
   true but incomplete — skills cannot execute. Compare *within* a tier, and
   compare *cost vs the capability it unlocks* across tiers.
2. **skills use progressive disclosure.** Only the 1,133-token frontmatter is
   always-on; a full skill body (avg **2,873 tokens**) loads only when invoked.
   rosetta is similar — tool schemas are always-on, doc text is pulled on demand.
   mikrotik-mcp has no such lever: **all 166 schemas are always-on, every turn.**

### Context-budget simulation (always-on + one task activation)

| Approach | After one task | Fits 8K | Fits 16K | Fits 32K |
|---|---:|:--:|:--:|:--:|
| baseline | 0 | ✅ | ✅ | ✅ |
| skills | 4,006 | ✅ | ✅ | ✅ |
| rosetta | 7,485 | ✅ | ✅ | ✅ |
| skills+rosetta | 11,491 | ❌ | ✅ | ✅ |
| mcp | 28,578 | ❌ | ❌ | ✅ |
| mcp+rosetta+skills | 40,069 | ❌ | ❌ | ❌ |

The all-in stack does not fit a 32K working budget after a single task
interaction. On small-context or cost-sensitive deployments, stacking everything
is actively counterproductive.

---

## 2. Tool-selection burden — the concern beyond tokens

A 166-tool surface fails not only on token cost but on *picking the right tool*.
Measured lexically over the 45-task corpus:

- **36.4 of 166** tools match a task on average (name/description overlap).
- **12.9** are "close-call" candidates (≥50% of the top match score).
- The correct tool is a clear **top-3** pick only **62%** of the time.
- The tool list mixes risk classes: **27 destructive**, 70 write, 69 read-only —
  destructive tools sit lexically adjacent to safe ones in the candidate set.

This is a first-class finding: even if the 28K tokens were free, selection
ambiguity among many similar tools is a correctness and safety hazard. It argues
directly against "expose every command as its own tool."

---

## 3. Does the knowledge actually help? (deterministic proxies)

Without a model we can't measure task success, but we can measure whether each
approach *exposes the answer*:

| Proxy | skills | rosetta | mcp |
|---|:--:|:--:|:--:|
| **Routing signal** — always-on context points at the right next action | 53% | 100%¹ | 80% |
| **Retrieval covers gold** — search surfaces the gold command path (hit@5) | n/a | **89%** | n/a |
| **Reconstructability** — `explain_command` recovers the gold path | n/a | **100%** | n/a |

¹ rosetta always exposes a single unified `routeros_search` entry point, so the
next action is unambiguous; the *quality* of what it returns is the 89%/100% row.

Reading this:

- **rosetta** has the strongest "answer is reachable" profile: one obvious search
  tool, high retrieval coverage, perfect path reconstruction via `explain`.
- **skills** frontmatter only routes 53% of tasks to a relevant skill — the
  guides are broad-topic, so intent→skill mapping is lossy. Skills shine as
  *deep reference once selected*, not as a router.
- **mcp** routes 80% by tool name/description, but see §2 — "a relevant tool
  exists" is not "the model picks it among 13 close calls."

---

## 4. Command validity & scorer trust (infrastructure, not effectiveness)

Validated on a live CHR 7.22.1 VM via `/console/inspect`:

- **46/46 gold commands** are valid RouterOS 7.22.1 syntax. The validator earned
  its keep during development by catching a real authoring bug (a route written
  `type=blackhole`; the device only accepts `blackhole=yes`).
- The **deterministic scorer classifies 12/12** canned candidates into the right
  failure mode (perfect / wrong_path / hallucinated / missing_arg / wrong_target
  / incomplete_seq / unsafe).

This validates the *scoring infrastructure* the live-agent harness will depend
on. It is explicitly **not** a measure of any approach's effectiveness.

Note the deliberate split the critique demanded: `/console/inspect` catches
**syntactic** errors (bad path, hallucinated property) but not **semantic** ones
(missing required arg, wrong target address, wrong rule order). The scorer
(gold comparison) owns the semantic categories.

---

## 5. Capability & safety matrix

| Capability | baseline | skills | rosetta | skills+rosetta | mcp | all |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| discover commands | ◐ | ◐ | ● | ● | ◐ | ● |
| explain semantics | ◐ | ● | ● | ● | ✗ | ● |
| validate before run | ✗ | ✗ | ◐ | ◐ | ✗ | ◐ |
| read live state | ✗ | ✗ | ✗ | ✗ | ● | ● |
| dry-run | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| write config | ✗ | ✗ | ✗ | ✗ | ● | ● |
| destructive write | ✗ | ✗ | ✗ | ✗ | ● | ● |
| post-change verify | ✗ | ✗ | ✗ | ✗ | ● | ● |
| version-aware | ✗ | ◐ | ● | ● | ✗ | ● |

`● yes  ◐ partial  ✗ no`

**Safety / blast-radius.** mikrotik-mcp is the only approach that can mutate a
device — and it does so with **27 destructive tools**, **no dry-run**, and a
**plaintext-credential** footprint (it SSHes in with stored creds; the repo
already warns about this in containers). rosetta and skills are read-only by
construction — rosetta's whole trust claim is that it never connects to a router.
**Capability and risk rise together**, and the 166-tool surface couples them
tightly with no validation gate in between.

**Staleness.** skills are hand-written markdown → they drift from RouterOS
versions silently (only `partial` version-awareness). rosetta is version-aware
(tracks 46 versions, command-version checks) but its prose corpus is a March-2026
Confluence export pending migration. mikrotik-mcp encodes command shapes in
Python and can fall behind RouterOS additions.

---

## 6. Pros / cons per approach

**baseline (training only)** — Free, zero context. But no validation, no live
state, weak on weird syntax. Fine for explaining concepts, unreliable for exact
commands.

**skills** — Cheapest augmentation (1,133 always-on, progressive bodies). Best as
*deep reference once the right guide is selected*. Weak as a router (53% signal)
and prone to silent version drift.

**rosetta** — Best cost/coverage for knowledge: 6.3K always-on, 89% retrieval
coverage, 100% path reconstruction, version-aware, read-only/safe. Cannot touch
a device. The standout for *planning and validation*.

**skills+rosetta** — Strongest pure-knowledge config; still fits a 16K budget.
Some topic overlap between the two; marginal skill cost is only +1,133 so the
combination is cheap. Good default for an advisor that won't execute.

**mcp** — The only executor. Uniquely able to read state, apply, and verify. But
28K always-on, heavy tool-selection ambiguity, 27 destructive tools, no dry-run,
credential exposure. Powerful and dangerous; the context/selection cost is real.

**mcp+rosetta+skills** — Most capable on paper (execution + retrieval + guides),
but 35.6K always-on / ~40.1K after one task — does not fit a 32K budget, and stacks
mcp's selection ambiguity on top. Additive in capability, additive in confusion.

---

## 7. Recommendation (the "more optimized path")

For the general problem of *giving AI agents better RouterOS information*:

1. **Default to rosetta (± skills) for anything read-only or planning.** It is
   the efficient frontier here: small always-on cost, high answer-reachability,
   safe, version-aware. This is the cheapest big win and the lowest risk.

2. **Do not expose execution as 166 always-on tools.** The token cost is the
   visible symptom; the **selection ambiguity and destructive-tool proximity**
   are the deeper problem. Prefer a **small, scoped execution surface** (a handful
   of verbs over a canonicalized `{path, verb, args}`) gated by validation.

3. **Adopt an explain → validate → run split.** rosetta/skills plan and the
   `/console/inspect` validator (proven here: catches bad paths and hallucinated
   properties pre-execution) gates a thin runner. This keeps the powerful-but-
   risky execution tier behind a cheap, safe, high-coverage knowledge tier —
   exactly the architecture the tikoci cross-project notes already point at.

4. **Don't stack everything.** `mcp+rosetta+skills` is the worst of the budget
   picture for marginal capability gain over the scoped-execution alternative.

### What this benchmark supports now vs. defers

**Supported now (in this repo's data):** context/token cost and budget limits;
tool-selection burden; retrieval coverage and reconstructability; corpus
validity; scorer trust; capability/safety/staleness tradeoffs.

**Deferred to live-agent runs (harness is scaffolded):** actual end-to-end task
success per approach, hallucination-rate reduction, error-recovery behavior,
semantic-correctness rates. `harness/run_agent.py` already defines the candidate
format and deterministic scorer; a real backend only needs to implement
`produce_candidate(task, approach)`.

---

## Appendix: where the numbers live

| Claim | File |
|---|---|
| Always-on / marginal / activation token costs | `data/token_cost*.csv` |
| 36/166 match, 62% top-3, destructive proximity | `data/tool_ambiguity.csv` |
| 89% hit@5, 100% reconstruct | `data/retrieval.csv` |
| 46/46 gold valid, 12/12 fixtures | `data/command_validity.csv` |
| Routing signal, budget fit | `data/proxy_*.csv` |
| Scorer replay, capability grid | `data/agent_replay.csv`, `data/capability_matrix.csv` |

Reproduce with `./run_all.sh`.
