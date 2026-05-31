# §8 addendum: closed-loop CHR device grounding (PILOT)

> **Status: pilot evidence, not benchmark-quality.** This is the next rung
> [REPORT.md §8](../REPORT.md#8-live-generation-mini-matrix-preliminary)
> explicitly named — "add a closed-loop CHR readback condition." It runs a
> handful of the live-matrix commands against a **real, disposable RouterOS
> 7.23 CHR** via `quickchr exec` and records the device's verdict. n is tiny
> (one instance, a few commands); read it for the *mechanism*, not rates.
> Raw verdicts: [`../data/live_chr_demo.csv`](../data/live_chr_demo.csv).

## Why this rung exists

§8 grounds *generation* (does the model emit the right command?) but still scores
against the **static** corpus gold and the `/console/inspect` schema validator.
Neither actually executes a command. This rung closes that last gap: it boots a
throwaway CHR and runs the command, so the **device console parser** — the real
oracle — gets the final say. It immediately found something the static tiers
could not.

## Finding A — the device contradicts the corpus gold (and §8's claim) on blackhole

§8 item #1 states the corpus author's fix was `blackhole=yes` ("RouterOS wants
`blackhole=yes`"). On a live RouterOS 7.23 device, **that is rejected**:

| Source | Command | Static (`/console/inspect`) | Device 7.23 verdict |
|---|---|:--:|---|
| both models, baseline | `…/ip/route/add … type=blackhole` | error | **REJECTED** — `bad parameter type` |
| Sonnet + rosetta-context | `…/ip/route add … blackhole` (bare flag) | ok | **ACCEPTED** — route created (Active, static) |
| **corpus gold** | `…/ip/route add … blackhole=yes` | **ok** | **REJECTED** — `expected end of command` (at the `=`) |

So `blackhole` is a **bare flag**: the parser takes the flag and rejects `=yes`.
rosetta's own property docs (aligned ~7.22) call it *"a flag indicates whether it
is a blackhole route."* This means:

- The **rosetta-context output §8 scored as `missing_arg`** (bare `blackhole`,
  "wrote the flag without `=yes`") was in fact the **only device-valid form** —
  the model was right and the gold/scorer were wrong.
- The **static `/console/inspect` validator accepted `blackhole=yes`** as
  schema-valid (it knows the `blackhole` arg exists), which is exactly why
  `46/46 gold valid` passed and the bug survived to here. Schema-presence ≠
  parser-acceptance. Only execution caught it.

> The committed gold was **not** silently rewritten (it would change a committed
> corpus snapshot across a 7.22→7.23 boundary on single-device evidence). It is
> flagged here and in [`data/PROVENANCE.md`](../data/PROVENANCE.md) as a corpus
> item to device-validate on 7.22.x. This reinforces §8's caveat #4 (scorer
> strictness) with a sharper one: **the gold itself can be wrong, and only a
> device tier reveals it.**

## Finding B — gold commands carry hidden device-state dependencies

`vlan-create-basic` gold uses `interface=ether2`; a vanilla CHR exposes only
`ether1` + `lo`, so the gold command is **rejected** (`input does not match any
value of interface`) until the port is one that exists. The command *shape* is
correct; the *referenced state* is not. Agents that build config from intent
alone — without first reading interfaces/bridges — emit shapes that fail on
contact with a device. Fixtures should declare their assumed topology, and the
execution tier should pair `exec` with a cheap **readback/introspect**.

## What this says for direction (complements §8, not replaces it)

§8 already shows grounding earns its keep on the generation side. This rung adds
the tier above it:

1. **Explain (offline retrieval)** — rosetta-style shape/version lookup.
2. **Validate (static)** — `lib.scorer` + `/console/inspect`. Cheap, but **blind
   to parser-level and state-level truth** (Findings A, B).
3. **Run (scoped device)** — a small agent-facing CLI against a *disposable*
   instance: `quickchr exec <name> "<cmd>"` (used here), or `centrs` for
   container/multi-node topologies. This is the only tier that caught the gold
   bug. A 3–5 verb CLI (`exec`, `snapshot`, `readback`, `clean`) is a far
   smaller, safer surface than the 166-tool MCP firehose — and it is where
   correctness is actually decided.

Concretely: `quickchr` is validated here as that execution tier (boot/reuse CHR,
`exec`, readback, `clean`); a parallel `centrs` adapter (not installed in this
env) is the natural follow-up for multi-device intents. And the right tier
**varies by task** — stateless syntax needs none of this; version-new menus and
flag-shape need retrieval; anything stateful/destructive needs
device-validate-before-apply.

## Reproduce

```bash
quickchr start <chr-instance>
quickchr exec <chr-instance> "/ip/route/add dst-address=10.99.0.0/24 blackhole"   # accepted
quickchr exec <chr-instance> "/ip/route/add dst-address=10.99.0.0/24 blackhole=yes" # rejected
quickchr exec <chr-instance> "/ip/route/remove [find dst-address~\"10.99\"]"
quickchr stop <chr-instance>
```

Device verdicts captured in [`../data/live_chr_demo.csv`](../data/live_chr_demo.csv).
