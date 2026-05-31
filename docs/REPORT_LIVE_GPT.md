# Cross-vendor live pilot: GPT (Copilot CLI) vs Claude (Claude Code)

**Status: PILOT evidence.** Small n, one backend per vendor, single run per cell
(GPT side) or 3 reps per cell (Claude side). This is directional grounding to
steer future work, **not** benchmark-quality scoring. See [`REPORT.md`](../REPORT.md)
for the structural benchmark, [`REPORT_LIVE.md`](REPORT_LIVE.md) for the
copilot-default pilot + Claude scale ladder, and
[`AGENTIC_FUTURES.md`](AGENTIC_FUTURES.md) for forward recommendations.

## What this adds

The structural benchmark scores *tool snapshots* (rosetta retrieval, mikrotik-mcp
tool surface, SKILL.md files). This pilot instead asks live models to **emit the
actual RouterOS command** for the same tasks, across two vendors and several model
tiers, so we can see where grounding actually changes model output — and
cross-reference against **device truth** captured on a disposable CHR 7.23 via
`quickchr` (`data/live_chr_demo.csv`).

- **GPT side** (`data/live_gpt_matrix.csv`, this branch): `copilot -p` with
  `--model gpt-4.1`, `gpt-5-mini`, `gpt-5.4`, `gpt-5.5`. Approaches: `baseline`
  (no context) vs `rosetta` (real retrieved docs injected as text). The two free
  models (gpt-4.1, gpt-5-mini) cover the full 6-task grid; the paid 1× (gpt-5.4)
  and 7.5× (gpt-5.5) models run only the 2 crux tasks to cap premium spend.
- **Claude side** (`data/live_matrix.csv`, parallel Claude Code session, cited
  read-only): `claude-haiku-4-5`, `claude-sonnet-4-6`, `claude-opus-4-7`, 3 reps,
  approaches `baseline` / `rosetta-context` / `skills-context`.
  - `claude-opus-4-8` cells are **excluded**: that run hit a usage limit mid-flight
    and its cells are empty/0. It is in-progress, not a real 0.

## Perfect-rate summary (GOOD = perfect | equivalent | refused_safe)

GPT side (this branch, 1 rep/cell; gpt-5.4 & gpt-5.5 ran only the 2 crux tasks to
cap cost):

| model | premium/call | baseline | rosetta |
|---|---|---|---|
| gpt-4.1 | 0× | 3/6 | **5/6** |
| gpt-5-mini | 0× | 2/6 | 1/6 |
| gpt-5.4 | 1× | 0/2 | 0/2 |
| gpt-5.5 | 7.5× | 0/2 | 0/2 |

Claude side (parallel, 3 reps/cell → /18; opus-4-8 excluded):

| model | baseline | rosetta-context | skills-context |
|---|---|---|---|
| claude-haiku-4-5 | 8/18 | **14/18** | 8/18 |
| claude-sonnet-4-6 | 15/18 | 15/18 | 12/18 |
| claude-opus-4-7 | 12/18 | 11/18 | 9/18 |

## Findings

### 1. `route-blackhole` fails for **everyone** — and the corpus gold is wrong too

This is the headline. Across **both vendors, every model tier, and every
augmentation approach**, not a single cell produced the device-valid blackhole
route:

- Every GPT cell emitted `type=blackhole` (gpt-4.1, gpt-5-mini, gpt-5.4,
  gpt-5.5, both approaches), except gpt-5-mini+rosetta which produced
  `gateway=blackhole`.
- Every Claude cell was `hallucinated` (baseline/skills) or `wrong_path`
  (Haiku+rosetta). Sonnet+rosetta **stayed `hallucinated`** — retrieval did not
  rescue it.

Cross-referenced against CHR 7.23 device truth (`data/live_chr_demo.csv`):

| form | who emitted it | device verdict |
|---|---|---|
| `type=blackhole` | all GPT cells, Claude (as hallucination) | **rejected** — `bad parameter type` |
| `gateway=blackhole` | gpt-5-mini+rosetta | rejected |
| `blackhole=yes` | **the benchmark gold** | **rejected** — `expected end of command` |
| `blackhole` (bare flag) | **only** copilot-*default*+rosetta (`REPORT_LIVE.md` Finding 1) | **accepted** — route created Active+static |

So among the **explicitly versioned** models tested here — gpt-4.1, gpt-5-mini,
gpt-5.4, gpt-5.5 (both approaches) and Claude Haiku/Sonnet/Opus-4-7 (all three
approaches) — **none** reached the device-valid form. The only cell that did,
across *every* run in the project, was the earlier pilot's **copilot-default
model with rosetta context** (1 of ~30+ cells), and only with retrieval. And the
corpus **gold itself was device-invalid** on 7.23. This is the strongest argument
in the whole project for (a) **device-in-the-loop validation** (quickchr/CHR), and
(b) **correcting the corpus gold** to the bare-flag form. A purely textual
benchmark would have scored everyone against a wrong answer.

> **Static validation is necessary but not sufficient.** Regenerating the
> benchmark (`./run_all.sh`, `method=chr:inspect`) shows `/console/inspect`
> accepts **both** `blackhole=yes` and bare `blackhole` as "path ok" — i.e. the
> static schema check *did not* catch the flag-vs-value error. Only **runtime
> exec** on a live CHR (`quickchr exec`) rejected `blackhole=yes`. This sharpens
> the validation-tier thesis: inspect/schema validation is a cheap first gate, but
> a scoped **runtime** execution tier (quickchr/centrs) catches parser-level
> errors that schema introspection misses.
>
> **Done in this change:** `route-blackhole` gold was corrected from
> `blackhole=yes` to the bare `blackhole` flag in `tasks/corpus.yaml`, with an
> inline CHR-validated note. Structural result CSVs predate the fix and should be
> regenerated on the next `./run_all.sh` (noted in `data/PROVENANCE.md`).

### 2. Augmentation lifts the **weak** model — consistently, cross-vendor

- gpt-4.1: 3/6 → **5/6** with rosetta.
- claude-haiku-4-5: 8/18 → **14/18** with rosetta-context.

Same shape on both sides: retrieved RouterOS docs help most where base knowledge
is weakest. This is the benchmark's core claim, now observed live on two vendors.

### 3. Augmentation is **neutral or negative** for strong/noisy models

- claude-sonnet-4-6: 15/18 baseline = 15/18 rosetta (already strong; no lift) and
  skills-context **dropped** it to 12/18.
- claude-opus-4-7: rosetta and skills both **below** baseline (11, 9 vs 12).
- gpt-5-mini: 2/6 → **1/6** — rosetta made the noisy small model worse (it
  over-applied context: used `/interface wireless` for the wifi task and mangled
  paths like `/ ip route`).

"More context" is not monotonically good. Injection that helps a weak model can
distract a strong one or overwhelm a noisy one — which argues for **task- and
model-aware** retrieval, not always-on dumping.

### 4. Raw retrieved docs beat SKILL-framing in this pilot (Claude side)

For both Claude models, `rosetta-context` outscored `skills-context`
(Haiku 14 vs 8; Sonnet 15 vs 12). Pilot-only, but it suggests the *packaging* of
grounding matters: distilled retrieved passages were more useful here than the
skill-file framing. Worth a dedicated comparison in future live runs.

### 5. Cost did not buy correctness on the hard tasks

Both paid tiers — gpt-5.4 (1×) and gpt-5.5 (7.5×) — scored **0/2** on the two
crux tasks, while **free** gpt-4.1 (0×) hit 5/6 overall and was the only model to
get the version-new wifi task right (`/interface/wifi set [find …] ssid=…`). Both
gpt-5.4 and gpt-5.5 instead used the deprecated nested `configuration.ssid=` form
— so the newer "5.x" family **regressed** on this specific version-new syntax
relative to the older gpt-4.1's flat `ssid=`. This is a **non-monotonic** result
where the cheaper, older model out-performed *both* paid newer ones on
version-specific syntax, and paying 7.5× over the 1× tier bought **no** crux
improvement. For *grounding research*, the free GPT models delivered the most
signal per dollar.

### 6. Refusal behavior — small models refuse more

gpt-5-mini **refused** the destructive `fw-default-drop-input-last` task at
baseline (`refused_safe`), mirroring Claude Haiku's tendency to refuse risky
tasks. Useful floor behavior, but inconsistent: with rosetta context gpt-5-mini
stopped refusing and emitted the command.

## Caveats (read before quoting)

- **PILOT, small n.** GPT cells are single-run; Claude cells are 3-rep. Treat
  rates as directional.
- **Copilot skill auto-load.** `copilot -p` auto-invoked the user's
  `routeros-fundamentals` skill on **all 4 gpt-5.5 calls and 3 of 4 gpt-5.4
  calls** despite `--available-tools ""` (the more-agentic newer models reached
  for it; gpt-4.1, gpt-5-mini, and the earlier copilot-default pilot did **not**
  load any skill). This means gpt-5.4/gpt-5.5 had *extra* RouterOS help the others
  lacked — yet still failed both crux tasks, so the comparison is **conservative**
  against the paid models, not inflated. The Claude matrix isolated skills
  explicitly via a separate `skills-context` approach.
- **One backend per vendor.** "GPT" = Copilot CLI's harness (~28k fixed input
  tokens/call); "Claude" = Claude Code. Vendor and harness are confounded; don't
  read these as pure model comparisons.
- **opus-4-8 excluded** (incomplete run).
- **Device truth is CHR-vanilla.** `vlan-create-basic` gold assumes `ether2`,
  which vanilla CHR lacks; the command succeeds once an existing port is named
  (`ether1`). Device-state dependence, not a model error.

## Reproduce

```bash
# GPT cross-model matrix (free models full grid; gpt-5.5 only the 2 crux tasks)
.venv/bin/python harness/live/run_gpt_matrix.py --dry-run        # preview + budget
.venv/bin/python harness/live/run_gpt_matrix.py --budget-premium 35
# Results: data/live_gpt_matrix.csv (+ .jsonl transcripts). Cache makes reruns free.
```

## Follow-ups this pilot motivates

1. **Audit the rest of the corpus for device-rejected golds** the same way the
   `route-blackhole` gold was just corrected (CHR exec + readback). Other
   flag-vs-`=yes` and version-specific golds are prime suspects.
2. **Distillation vs raw injection, and rosetta-vs-skills**, as first-class live
   approaches — finding #4 suggests packaging matters.
3. **Task/model-aware retrieval** — finding #3 shows always-on context can hurt.
4. **Keep device-in-the-loop** (quickchr/CHR, and centrs as a scoped-execution
   surface) in the loop: it caught a wrong gold that no textual check would.
