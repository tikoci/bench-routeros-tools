# Live-Agent Pilot: Grounded Findings (PILOT EVIDENCE)

> **Status: PILOT, not benchmark-quality.** Single live backend (`copilot -p`),
> `n = 6` tasks × 2 approaches = 12 cached generations, plus a closed-loop CHR
> demo on one disposable RouterOS 7.23 instance. These results are directional
> evidence to guide future work — not statistically meaningful scores. See
> [REPORT.md](../REPORT.md) for the structural benchmark and its caveats.

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
   `clean`) is a far smaller, safer attack/àcontext surface than 166 MCP tools,
   and it is the **only** tier that grounds correctness.

Concretely for this project:
- **`quickchr` as the execution tier** is validated here: boot/reuse a CHR,
  `exec` a candidate, read back state, `clean`. It directly grounded Findings 1–2.
- **`centrs` (not installed in this environment)** is the analogous tier for
  multi-node / container topologies; future work should add a `centrs` adapter
  parallel to the quickchr demo so multi-device intents (routing between nodes,
  bridge/VLAN across hosts) can be device-grounded too.
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
```

`data/live_cache/` is git-ignored (regenerable, and avoids committing model
output verbatim). `data/live_pilot.csv`, `data/live_pilot.jsonl`, and
`data/live_chr_demo.csv` are committed as the reproducible pilot snapshot.
