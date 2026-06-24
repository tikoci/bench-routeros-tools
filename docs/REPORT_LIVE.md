# Live-Agent Pilot: Grounded Findings (PILOT EVIDENCE)

> **Status: PILOT, not benchmark-quality.** Single live backend (`copilot -p`),
> `n = 6` tasks × 2 approaches = 12 cached generations, plus a closed-loop CHR
> demo on one disposable RouterOS 7.23 instance. These results are directional
> evidence to guide future work — not statistically meaningful scores. See
> [REPORT.md](../REPORT.md) for the structural benchmark and its caveats.
>
> **Companions:** [`REPORT_LIVE_GPT.md`](REPORT_LIVE_GPT.md) extends this to a
> **cross-vendor** pilot (GPT via Copilot CLI vs Claude via Claude Code) and
> shows `route-blackhole` fails for *every* model/approach on *both* vendors —
> which is why the corpus gold was corrected to the device-valid bare flag.
> **Finding 6** below adds a **4-rung Claude scale ladder** (Haiku 4.5 → Opus 4.8)
> with `k=3` stability bands, showing the same trap is invariant to **model
> scale** up to the frontier. **Findings 7–8** add two further device-verified
> traps: `route-unreachable` (a *removed-capability* trap — the v6 form has **no**
> v7 equivalent, so even retrieval can't rescue it) and `dhcp-server-on-bridge`
> (a silent `disabled=yes` default that only rosetta fills in). And
> [`AGENTIC_FUTURES.md`](AGENTIC_FUTURES.md) turns all of this into forward
> recommendations for RouterOS agentic tooling.

## What this adds over the structural benchmark

The structural benchmark (`run_all.sh`) measures *proxies* — retrieval coverage,
context size, deterministic label prediction. It never asks a live model to build
a command, and never runs anything against a real RouterOS. This pilot closes two
gaps:

1. **Generation grounding** — does a real model, given each approach's context,
   emit the right command? (`harness/live/run_live.py` → `data/live_pilot.csv`)
2. **Execution grounding** — does the emitted command actually work on a real
   RouterOS device? (`quickchr exec` → `data/live_chr_demo.csv`)

## Method

- **Backend:** `copilot -p` is the only live backend available in this
  environment (claude CLI is not logged in; no API keys, no local model). It is
  invoked clean (`--no-custom-instructions --disable-builtin-mcps
  --available-tools "" --disable-mcp-server …`) so the harness, not the CLI's
  ambient tooling, controls context. Calls are **cached by prompt hash**
  (`data/live_cache/`), so reruns cost nothing and results are reproducible.
- **Approaches contrasted:** `baseline` (task only, no context) vs `rosetta`
  (the same task plus *real* retrieved RouterOS docs injected as text, via
  `routeros_search` + `routeros_explain_command`, capped at 6000 chars).
- **Tasks (6):** `vlan-create-basic`, `vlan-bridge-untagged-pvid` (multi-step),
  `route-blackhole` (syntax trap), `wifi-set-ssid` (7.22+ new menu),
  `wg-create-interface` (7.21+), `fw-default-drop-input-last` (destructive /
  refusal-expected).
- **Scoring:** the existing static scorer (`lib/scorer.py` `predict_label`) plus
  rosetta-static syntax validation, plus — for the CHR demo — the device verdict.

## Pilot results

| Task | baseline | rosetta |
|---|---|---|
| vlan-create-basic | perfect | perfect |
| vlan-bridge-untagged-pvid | perfect | perfect |
| route-blackhole | hallucinated | missing_arg |
| wifi-set-ssid (7.22+) | missing_arg | missing_arg |
| wg-create-interface (7.21+) | perfect | perfect |
| fw-default-drop-input-last (destructive) | hallucinated | hallucinated |

Strict "good" (perfect/refused_safe): **baseline 3/6, rosetta 3/6.** On the raw
score, retrieval did not move the headline number on this tiny set. The
*interesting* signal is underneath the labels.

## Finding 1 (centerpiece): the device disagreed with the gold, and rosetta was right

`route-blackhole` produced a three-way disagreement that only **device
execution** could resolve:

| Source | Command | Static scorer | RouterOS 7.23 device |
|---|---|---|---|
| baseline model | `…/ip/route/add … type=blackhole` | hallucinated | **REJECTED** — `bad parameter type` |
| **rosetta model** | `…/ip/route add … blackhole` (bare flag) | missing_arg | **ACCEPTED** — route created (Active, static) |
| **corpus gold** | `…/ip/route add … blackhole=yes` | perfect (by definition) | **REJECTED** — `expected end of command` |

Read that carefully: the **rosetta-guided model emitted the only form that
actually works**, yet the static scorer *penalized* it (`missing_arg`) because
the corpus gold (`blackhole=yes`) is itself **device-invalid** on 7.23.
`blackhole` is a bare flag (rosetta's own property docs say *"A flag indicates
whether it is a blackhole route"*); the device's console parser accepts the flag
but rejects `=yes` at the `=` (column 49). No changelog between 7.19–7.23 shows a
syntax change to this flag, and the rosetta corpus (aligned ~7.22) documents it
as a flag — so this is very likely a latent error in the gold, not a 7.22→7.23
regression.

> **Independently re-verified on both versions** (`data/blackhole_device_verify.csv`,
> via `quickchr exec` — real CLI parser, not `/console/inspect`). On **7.22.1**
> (the benchmark's exact scope) *and* **7.23**: `type=blackhole` and
> `blackhole=yes` are both **rejected** (no route created); only the bare
> `blackhole` flag creates an Active/static route. The only cross-version
> difference is the error string for `type=blackhole` (7.22.1: `expected end of
> command`; 7.23: `bad parameter type`) — the rejection is identical. The
> corrected gold is device-confirmed on the version the corpus targets.

**Implication:** static gold/oracles silently encode human syntax assumptions
that can be wrong. A scoped **device-grounded validation tier** is not a luxury —
it is the only thing that caught both the model's win *and* the oracle's bug.
This is the strongest single argument in the whole project for the
explain → validate → **run** loop (REPORT.md recommendation #2).

> Action taken: the gold was **not** silently rewritten (it would change a
> committed corpus snapshot across a version boundary on n=1 device evidence).
> The discrepancy is recorded in `data/live_chr_demo.csv` and flagged here and in
> `data/PROVENANCE.md` as a corpus item to device-validate on 7.22.x.

## Finding 2: gold commands carry hidden device-state dependencies

`vlan-create-basic` gold uses `interface=ether2`; a vanilla CHR has only
`ether1` + `lo`, so the gold command is **rejected** (`input does not match any
value of interface`) until rewritten to `ether1`. The command shape is correct;
the *referenced state* does not exist. Agents that build config from intent alone
— without reading current interfaces/bridges — will emit shapes that fail on
contact with a real device. This argues for giving agents a cheap **read/introspect**
surface (and for fixtures that declare their assumed topology).

## Finding 3: a strong base model already nails common, stateless syntax

`vlan`, `wireguard`, and basic firewall syntax were correct with **no
augmentation**. Retrieval's marginal value concentrates on (a) version-new menus
(`wifi-set-ssid`, 7.22+: both approaches used `configuration.ssid=`/`ssid=`
variants that rosetta-static rejected — neither fully succeeded) and (b)
boolean/flag property syntax (Finding 1). Spending retrieval budget where the
base model is already competent is largely wasted; spend it on version-new and
property-shape uncertainty.

## Finding 4: raw-JSON injection helps vocabulary, not formatting discipline

Injecting rosetta retrieval as raw JSON text nudged the model onto correct
*vocabulary* (the `blackhole` property; the `[find name=wifi1]` selector where
baseline used a bare `wifi1`) but also sometimes shifted it to space-form paths
and did not fix boolean/version gaps. This suggests retrieval **distillation /
formatting** matters as much as coverage — a context builder that hands the model
a clean property/flag table may beat dumping search hits.

## Finding 5: the live data hardened the scorer (and exposed remaining limits)

Inspecting real emitted commands drove concrete oracle fixes:

- **Fixed — path equivalence:** RouterOS treats `…/interface/bridge/port/set`
  and `/interface bridge port set` identically; the scorer now normalizes
  space-form paths (`lib/scorer.py` `_split`). This flipped
  `rosetta/vlan-bridge-untagged-pvid` from a false `wrong_path` to `perfect`.
- **Fixed — identity args:** added `bridge` to `IDENTITY_ARGS` so a
  `bridge=bridge` typo can be caught.
- **Remaining caveat — single-command scoring:** `predict_label` scores only the
  first emitted command, so multi-step ordering and second-command typos are
  invisible (baseline's reversed two-command bridge sequence still scored
  `perfect`).
- **Remaining caveat — harmless extras penalized:** an added `comment=` is scored
  `hallucinated` even when behavior is correct.
- **Remaining caveat — refusal vs safe-construction:** on the destructive
  ordering task neither model refused, but both **avoided** the forbidden
  `place-before=0` and appended at the end (the safe outcome). The label
  (`hallucinated`, for an added `comment=`) overstates the failure; the *safety
  behavior* was actually correct. A safety-aware scorer should separate
  "did something forbidden" from "added a harmless arg".

## Finding 6: scale does not fix the trap — a 4-rung Claude ladder confirms it

Findings 1 and 4 show `route-blackhole` is a trap on the `copilot` backend. The
obvious objection is *"a bigger/better base model would just know the right
syntax."* A separate Claude run boxes that in. It sweeps a **4-rung model ladder**
— Haiku 4.5 → Sonnet 4.6 → Opus 4.7 → **Opus 4.8 (frontier)** — across three
context conditions (`baseline` / `rosetta-context` / `skills-context`), over the
same 6-task subset, with **each cell repeated `k=3`** — the **full 4×3×6 grid,
216 generations**. Artifacts: `data/live_ladder*.{csv,jsonl}`, analysis via
`harness/live/analyze_ladder.py`. (The `syntax_valid` column was re-validated with
`harness/live/revalidate_ladder_syntax.py` after a `lib/chr.py` fix: the merged
validator briefly skipped argument checks on multi-segment **space-form** paths
like `/ip route add …`, falsely passing `type=blackhole`; corrected here.)

**The crux is invariant to scale.** Of **36** `route-blackhole` generations across
the whole ladder, only **2** reached the device-valid bare `blackhole` flag — and
both were 1-of-3 within their cell (a coin-flip, not a capability). **30 of 36**
emitted the device-invalid `type=blackhole`:

| Model | device-valid (bare `blackhole`) | emitted `type=blackhole` | other wrong |
|---|:--:|:--:|:--:|
| Haiku 4.5 | 0 / 9 | 5 | 4 (`/routing/route`) |
| Sonnet 4.6 | 1 / 9 | 8 | — |
| Opus 4.7 | 1 / 9 | 8 | — |
| **Opus 4.8 (frontier)** | **0 / 9** | 8 | 1 (`/routing/route`) |

The frontier model fails this task **as reliably as the smallest one**. Moving up
two model generations does not buy the device-valid form — it is a genuine,
flat gap in trained RouterOS knowledge, exactly where Finding 1 said the
device-grounded tier earns its keep. Combined with the **cross-vendor** result in
[`REPORT_LIVE_GPT.md`](REPORT_LIVE_GPT.md) (every GPT model/approach also fails
`route-blackhole`), the trap is invariant to **both vendor and scale** — the
strongest possible case that no amount of base-model improvement on the visible
trend line closes it. A `validate → run` tier does.

**The `k=3` band also corrected a single-shot over-claim.** An earlier one-shot
read suggested `rosetta-context` "moved Sonnet to drop `type=blackhole`"; at
`k=3` that cell is **3/3 `type=blackhole`** — the earlier flip was noise. Live
single-shot cells are unreliable; report **column shapes and stability bands**,
not individual cells. (**16 of 72** ladder cells disagreed across their 3 repeats —
concentrated in Haiku and at the `route-blackhole` boundary where models
occasionally slip between `type=blackhole`, `/routing/route`, and the bare flag.)

**Secondary — augmentation value is model-dependent, not a constant.**
`rosetta-context` lifted Haiku's syntax-valid fraction to **17/18** (it eliminated
nearly all *fabrication*, even when not gold-perfect) and its perfect rate 8→14/18;
for Sonnet and Opus the same context was net-neutral. `skills-context` was
neutral-to-negative across the board: the skill body's worked examples induced
**over-specification** (e.g. adding `in-interface-list=WAN` to a dst-nat rule),
which the strict scorer marks `hallucinated`. Practical rule: spend augmentation
budget on the **weak** model and on version-new / flag-shape uncertainty; for a
strong model on common syntax, extra context mostly adds over-specification risk
(echoing Finding 3).

## Finding 7: a *removed-capability* trap — the v6 prior has no v7 form at all

`route-blackhole` is a **form-change** trap: the v6 `type=blackhole` became the
bare `blackhole` flag, so a grounded tier (rosetta) can supply the right form.
`route-unreachable` is the harder cousin — a **removed-capability** trap. Device
verification on CHR 7.23.1 (`data/route_unreachable_device_verify.csv`,
`quickchr exec`) shows the v6 `unreachable`/`prohibit` route types have **no
creatable v7 form** at `/ip/route`:

| form (intent: "unreachable route for 172.16.0.0/12") | device verdict |
|---|---|
| `… type=unreachable` (v6 prior) | **REJECTED** — `bad parameter type` |
| `… unreachable=yes` | **REJECTED** — `bad parameter unreachable` |
| `… unreachable` (bare flag, by analogy to blackhole) | **REJECTED** — `bad parameter unreachable` |
| `… type=prohibit` / `… prohibit` | **REJECTED** |
| `… blackhole` (control) | **ACCEPTED** — stores `blackhole=true`, no `type` field |

`/ip/route add` accepts only 13 args (inspect `syntax`), and `blackhole` is the
**lone** surviving discard flag; the print legend still lists `U - unreachable,
P - prohibit`, but those are for protocol-injected/legacy routes, not manual
creation. So the task has **no satisfiable gold**. Leaving the old
`type=unreachable` gold in place made the scorer report a *false* `perfect`
(candidates matched a device-invalid gold while `syntax_valid=error` on every
rep) — the same gold-vs-device lie as Finding 1, now caught structurally.

The fix reframes it as a `removed_capability` task (`tasks/corpus.yaml`,
`lib/scorer.py`, anchor tests in `harness/live/test_removed_capability.py`):
`trap-fell` = emitted any removed v6 form (`type=…` / bare `unreachable`/`prohibit`),
`trap-avoided` = emitted the v7 `blackhole` alternative **or** no command at all
(recognized the removal). Re-scored over the Haiku `k=3` grid
(`harness/live/rescore.py`, no new model calls):

| approach | route-unreachable (k=3) |
|---|---|
| baseline | `trap-fell` 3/3 |
| rosetta-context | `trap-fell` 3/3 |
| skills-context | `trap-fell` 3/3 |
| vendordoc-steer | `trap-fell` / `trap-avoided` / `hallucinated` (1 each) |

The sharpest contrast with Finding 1: **rosetta does not rescue this one** — for
blackhole it could retrieve the bare-flag form, but for unreachable there is
*nothing correct to retrieve*, so it falls for the v6 prior 3/3 like baseline.
The only reps that escaped were under `vendordoc-steer`: one fetched and then
emitted *no* command (correctly recognizing the capability is gone), and one
reached for `blackhole` — but as the device-invalid `blackhole=yes`, falling into
route-blackhole's *own* trap (scored `hallucinated`, honestly). This is the
inspect-vs-runtime + v6-prior story at its limit: when a capability is **deleted**
rather than **renamed**, retrieval-of-the-right-form cannot help; only "recognize
it's impossible, or run it and see it rejected" does.

## Finding 8: `dhcp-server-on-bridge` — the cleanest *disabled-by-default* trap

`/ip/dhcp-server add` defaults to `disabled=yes`, so omitting `disabled=no` yields
a **syntactically valid, functionally dead** server — a `missing_arg` no syntax
validator can catch (the purest extension of Finding 1's inspect-vs-runtime gap).
On the Haiku `k=3` grid only **rosetta-context** supplied `disabled=no` (perfect
3/3); `baseline`, `skills-context`, and `vendordoc-steer` all omitted it
(`missing_arg` 3/3, `syntax_valid=ok` throughout). Notably, *steering to the
vendor page did not help* — the agent fetched `dhcp-server.md` (cited 3/3) and
still left the server disabled. This is the inverse lesson to Finding 7: where the
failure is a **silent default** rather than a rejected token, the device's syntax
check is blind to it, and only retrieval that surfaces the *default* (rosetta) or
an actual functional read-back closes the gap.

## Future directions: scoped execution CLIs as a validation tier

The MCP path exposes ~166 tools — a firehose that costs context and invites
mis-selection. The grounded findings above point at a leaner architecture for
agent ↔ RouterOS work, organized as **tiers** rather than one giant tool surface:

1. **Explain (offline):** rosetta-style retrieval for command/property/flag
   shape and version scope. Cheap, no device. Best when *distilled* (Finding 4).
2. **Validate (static):** rosetta-static / `/console/inspect` schema checks.
   Catches obvious shape errors without a device — but **cannot** catch
   gold/oracle bugs (Finding 1) or state dependencies (Finding 2).
3. **Run (scoped device):** a small, agent-friendly CLI against a **disposable**
   instance — `quickchr exec <name> "<cmd>"` (used for this pilot's CHR demo),
   or `centrs` for container-hosted topologies. This tier is where the gold-vs-
   device disagreement surfaced. A 3–5 verb CLI (`exec`, `snapshot`, `readback`,
   `clean`) is a far smaller, safer attack/context surface than 166 MCP tools,
   and it is the **only** tier that grounds correctness.

Concretely for this project:

- **`quickchr` as the execution tier** is validated here: boot/reuse a CHR,
  `exec` a candidate, read back state, `clean`. It directly grounded Findings 1–2.
- **`centrs` (not installed in this environment)** now realizes this tier as a
  product: a scoped-verb stdio MCP (`centrs_explain`/`validate`/`retrieve`/
  `execute`/`devices`) over a canonicalize → validate → run core, in-progress and
  CHR-tested on its own side — the direct alternative to the 166-tool MCP, citing
  this report as its rationale. Follow-up is to wire it into this harness as a
  measured approach and to add a multi-node/container adapter (routing between
  nodes, bridge/VLAN across hosts). See `docs/AGENTIC_FUTURES.md`.
- **Right approach varies by task** (the user's framing): stateless syntax →
  base model alone (Finding 3); version-new menus / flag shape → distilled
  retrieval (Findings 1, 4); anything stateful or destructive → mandatory
  device-validate-before-apply (Findings 1–2, 5). A one-size tool surface is the
  wrong default.

## How to reproduce

```bash
uv venv && uv pip install -e .          # or: python3 -m venv .venv && .venv/bin/pip install -e .
# Cached pilot (no live calls if cache present):
.venv/bin/python harness/live/run_live.py --dry-run   # prints prompts only
.venv/bin/python harness/live/run_live.py             # uses data/live_cache/, writes data/live_pilot.*
# Closed-loop device demo (needs quickchr + a CHR instance):
quickchr start <instance> && quickchr exec <instance> "<command>"
# Claude model-scale ladder (Finding 6); needs the claude CLI + a CHR validator:
.venv/bin/python harness/live/run_live_ladder.py \
  --models claude-haiku-4-5-20251001,claude-sonnet-4-6,claude-opus-4-7 --repeats 3
.venv/bin/python harness/live/analyze_ladder.py    # summarize data/live_ladder*
# Removed-capability device-verify (Finding 7) + offline re-score after a scorer
# or gold change (no new model calls):
quickchr exec <instance> "/ip/route add dst-address=172.16.0.0/12 type=unreachable"  # -> bad parameter type
.venv/bin/python harness/live/rescore.py           # re-apply current scorer to captured runs
```

`data/live_cache/` is git-ignored (regenerable, and avoids committing model
output verbatim). `data/live_pilot.csv`, `data/live_pilot.jsonl`, and
`data/live_chr_demo.csv` are committed as the reproducible pilot snapshot.
