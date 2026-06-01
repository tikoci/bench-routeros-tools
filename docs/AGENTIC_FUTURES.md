# Agentic AI Futures for RouterOS

> **What this is.** A forward-looking companion to [`REPORT.md`](../REPORT.md)
> (the structural benchmark) and the grounded live pilots
> ([`REPORT_LIVE.md`](REPORT_LIVE.md), [`REPORT_LIVE_GPT.md`](REPORT_LIVE_GPT.md)).
> REPORT.md answers *"which way of helping an agent is most efficient today?"*
> This document answers the next question the user posed: *"given what we now
> measured, where should RouterOS agentic-AI tooling go — extend what exists, or
> build something new?"* Every claim here is anchored to a finding in those
> reports; this is a synthesis, not new data.

## TL;DR — five things the measurements changed our mind about

1. **The RouterOS knowledge gap is structural, not a small-model symptom.** The
   `route-blackhole` syntax trap (`type=blackhole`, which the device rejects)
   persists across a **4-rung Claude scale ladder up to the frontier (Opus 4.8:
   0/9 correct)** *and* across **every GPT tier** — invariant to both vendor and
   scale. *Don't architect on the assumption that the next base model fixes it.*
   (REPORT_LIVE.md Finding 6; REPORT_LIVE_GPT.md Finding 1.)
2. **Static validation is necessary but not sufficient.** `/console/inspect`
   schema checks accepted a gold command (`blackhole=yes`) the real device
   rejects — an *inspect-vs-runtime gap*. Only device execution caught both the
   model's win and the oracle's bug. (REPORT_LIVE.md Finding 1.)
3. **Execution should be a small, scoped surface — not 166 always-on tools.** The
   token cost is the visible symptom; selection ambiguity and destructive-tool
   proximity are the deeper hazard. (REPORT.md §2, §5.)
4. **Augmentation is model- and task-dependent, not a constant win.** Retrieval
   lifts weak models and erases their fabrication; for strong models on common
   syntax it is net-neutral and sometimes *induces over-specification*. (REPORT.md
   §8; REPORT_LIVE.md Finding 6; REPORT_LIVE_GPT.md Findings 2–3.)
5. **Retrieval quality beats quantity.** Raw doc/JSON injection nudged vocabulary
   but also misdirected paths and copied example args; distilled property/flag
   tables likely beat dumping search hits. (REPORT_LIVE.md Finding 4;
   REPORT_LIVE_GPT.md Finding 4.)

## The central evidence: scale and vendor do not close the gap

| Probe | Result | Source |
|---|---|---|
| `route-blackhole`, Claude ladder (Haiku→Opus 4.8), k=3 | **2 / 36** generations device-valid; 30/36 emit the invalid `type=blackhole`; **frontier Opus 4.8 = 0/9** | REPORT_LIVE.md F6 |
| `route-blackhole`, GPT tiers (gpt-4.1 → gpt-5.5) | fails for **every** model × approach | REPORT_LIVE_GPT.md F1 |
| The corpus *gold itself* (`blackhole=yes`) | **device-rejected**; static `/console/inspect` accepted it anyway | REPORT_LIVE.md F1 |
| Paying 7.5× (gpt-5.5 over gpt-5.4) | **0/2** on crux tasks — cost bought no correctness | REPORT_LIVE_GPT.md F5 |

The single most important consequence: **a device-grounded validate/run tier is
not a crutch for today's weak models that better models will obsolete — it is a
permanent correctness floor.** RouterOS's sparse training representation and its
parser quirks (bare flags, space/slash menus, version-shifted menus) are exactly
the failure surface that improves slowly with scale and fast with grounding.

## Recommended architecture: explain → validate → run, as tiers

This sharpens REPORT.md recommendation #3 with the live evidence. Build the agent
↔ RouterOS surface as **three cheap-to-expensive tiers**, each gating the next —
*not* one monolithic tool list.

| Tier | What | Cost / risk | Catches | Misses |
|---|---|---|---|---|
| **0 · Explain** | rosetta-style retrieval (command/property/flag shape, version scope), **distilled** | ~6K always-on tokens, read-only | vocabulary, version scope | nothing it isn't asked; formatting discipline |
| **1 · Validate (static)** | `/console/inspect` / rosetta-static schema check | cheap, no device | bad paths, hallucinated properties | parser-level errors, state dependencies, oracle bugs |
| **2 · Run (scoped device)** | 3–5 verb CLI (`exec`/`snapshot`/`readback`/`clean`) on a **disposable** CHR (`quickchr`) or container topology (`centrs`) | a VM/boot, but isolated & reversible | *everything* — the only correctness ground truth | (it is the ground truth) |

**Orchestration policy** (route by task class, the user's "right approach varies"):

- **Stateless common syntax** → base model alone. Tier 0+ is wasted budget and can
  *add* over-specification. (REPORT_LIVE.md F3, F6.)
- **Version-new menus / flag-shape uncertainty** → distilled Tier 0 retrieval.
  This is where augmentation's marginal value concentrates. (F1, F3, F4.)
- **Anything stateful, destructive, or mutating** → **mandatory Tier 2
  validate-before-apply.** Static validation alone is not enough (F1, F2).

This keeps the powerful-but-risky execution tier behind cheap, safe, high-coverage
knowledge — and replaces the 166-tool firehose with a canonicalized
`{path, verb, args}` runner small enough to audit.

## What to build or change next (concrete, tikoci-mapped)

1. **Stand up the scoped-execution tier as a first-class thing.** `quickchr exec`
   already grounded Findings 1–2; promote it from demo to a stable 3–5 verb
   contract (`exec`, `snapshot`, `readback`, `clean`) an agent can drive against a
   disposable CHR.
   - **This is now being realized in [`centrs`](https://github.com/tikoci/centrs).**
     Its `mcp` surface (`commands/mcp/`, `src/mcp/`; in-progress, Phase 1
     CHR-tested against CHR 7.23) is a direct, grounded implementation of the
     architecture this report recommends — and it cites this benchmark
     (`REPORT.md`, `REPORT_LIVE_CHR.md`) as its design rationale. It exposes a
     handful of **verb** tools — `centrs_explain` (offline canonicalize →
     `{path, verb, args}`), `centrs_validate` (dry-run `:parse` **+**
     `/console/inspect`, never mutates), `centrs_retrieve`, `centrs_execute`,
     `centrs_devices` — over the same canonicalize → validate → run core the CLI
     uses, **not one tool per RouterOS command.** That is the explicit answer to
     the 166-tool `mikrotik-mcp` firehose (REPORT.md §2/§5): ~5 tools + 2
     resources instead of 166 always-on schemas, near-zero tool-selection
     ambiguity, and a CDB-as-allowlist safety model (per-device `mcp=ro|rw` +
     `confirm:true`) that closes the destructive-proximity and plaintext-credential
     hazards the bench flagged. `centrs_validate` is the bench's gold-bug catcher
     promoted to a first-class **dry-run tool**. A multi-node/container adapter
     (inter-node routing, cross-host VLANs) remains the natural follow-on.
2. **Build a distilled-retrieval context builder and measure it against raw-doc
   injection.** Hand the model a clean property/flag/version table, not a dump of
   search hits. REPORT_LIVE.md F4 and the GPT F4 both predict this beats the
   current approach; it deserves a dedicated live A/B. (rosetta owns the data;
   restraml owns the enum/attribute schema that would feed the table.)
3. **Make pre-apply device validation a default gate, not an option.** Any agent
   that mutates RouterOS should be required to round-trip a candidate through Tier
   1+2 before applying. The blackhole case shows even the *gold author* was wrong;
   agents will be too.
4. **Turn the benchmark into a standing regression eval.** Freeze a "known-trap"
   set (blackhole bare-flag, dst-nat over-specification, wifi 7.22 menu shift,
   wireguard underspecified refusal) and re-run it as base models ship — with
   **k≥3 repeats and stability bands** (single-shot live cells are noise; F6
   corrected a prior single-shot over-claim). This converts a one-time pilot into
   a tracking signal for "did the gap actually close?" When the scoped-MCP tier
   exists as a product (it now does, in `centrs` — see #1), add it as a measured
   *approach* alongside `mikrotik-mcp`; the plan is below.
5. **Add adaptive augmentation.** Detect *when* to inject context — weak model or
   version-new task → inject; strong model on common syntax → withhold (it mostly
   adds over-specification risk). A static "always paste rosetta" policy is
   provably suboptimal for strong models (F6 secondary; GPT F3).

## Plan: benchmark `centrs` as the realized scoped-execution tier

`centrs` is the first concrete artifact this benchmark can test *as the
recommended architecture*, head-to-head against the 166-tool `mikrotik-mcp`. The
goal is not to re-prove the model-side trap findings — it is to **measure whether
the scoped-verb MCP actually delivers the cost/ambiguity/safety wins this report
predicts, and whether its `centrs_validate` tier catches the traps generation
misses.** Sequenced so it tracks centrs' own maturity (its `docs/MATRIX.md` is
the readiness signal):

1. **Gate on maturity, not calendar.** Start when centrs' `mcp` surface is
   `CHR-passed` for Phase 1 reads/validate **and** `execute` over a second
   transport (native-api) is stable — i.e. the validate→run path is real on a
   device, not just `rest-api`. Until then this is design review only.
2. **Add `centrs-mcp` as a 7th approach** next to `mcp` (mikrotik-mcp) in
   `approaches.yaml`, and re-run the **structural** metrics unchanged so the
   comparison is apples-to-apples:
   - **token/context cost** (`data/token_cost.csv`): 5 tool schemas, 2 resources,
     and server instructions vs. mikrotik-mcp's ~28.2K always-on tokens. Predict
     an order-of-magnitude drop.
   - **tool-selection ambiguity** (`data/tool_ambiguity.csv`): with 5 verbs the
     "36/166 match, 62% top-3" hazard should collapse toward unambiguous. Confirm.
   - **capability/safety matrix** (`data/capability_matrix.csv`): centrs is the
     *only* executor with a dry-run (`centrs_validate`), a declarative allowlist
     (CDB), a per-device write gate (`mcp=rw`), and no-plaintext-credentials —
     vs. mikrotik-mcp's 27 destructive tools with no dry-run. This row is where
     centrs should dominate, and it is the bench's sharpest argument.
3. **Drive the known-trap set *through the tier*, not just the model.** For each
   frozen trap (blackhole bare-flag, dst-nat over-spec, wifi 7.22 shift, wireguard
   underspecified), run `centrs_explain → centrs_validate → centrs_execute` against
   a disposable CHR and assert the **validate tier rejects the bad form before any
   write** even when the generating model emitted it. This measures the *floor the
   tier provides*, independent of model quality — the load-bearing claim of this
   whole document.
4. **Reuse centrs' own harness shape.** centrs ships `test/integration/mcp.test.ts`
   (boots CHR via `@tikoci/quickchr`, registers a throwaway CDB, drives an
   in-process MCP client over stdio). The bench's live harness can either spawn
   `bunx @tikoci/centrs mcp` over stdio or reuse that in-process client pattern —
   no new transport code needed. Pin RouterOS **7.22.1** (this bench's scope) plus
   a 7.23 cross-check, since centrs' own examples already run on 7.23.
5. **Report the delta, with bands.** Same discipline as everywhere else: k≥3,
   stability bands, column shapes. The expected headline is "centrs-mcp matches
   mikrotik-mcp's *executor* capability at a fraction of the token/ambiguity cost
   **and** adds a validate gate mikrotik-mcp structurally cannot" — but that is a
   prediction to be measured, not asserted.

## Methodology notes for whoever benchmarks this next

- **Device-in-the-loop is non-negotiable** for correctness claims; schema oracles
  silently encode human assumptions that can be wrong (F1).
- **Report column shapes and stability bands, not single cells.** k=3 already
  flipped a headline; k=5+ for anything quoted as a rate.
- **Box findings on two axes — vendor and scale.** A gap that survives both (as
  `route-blackhole` does) is structural; one that closes on either is a model
  artifact. This pairing is what makes the grounding argument load-bearing.
- **Cost is not a correctness proxy.** The most expensive tier bought zero crux
  correctness (GPT F5); spend on grounding, not bigger models.

---

*Anchors:* structural cost/selection/coverage → [`REPORT.md`](../REPORT.md);
device-grounded findings + the tier proposal → [`REPORT_LIVE.md`](REPORT_LIVE.md);
cross-vendor confirmation → [`REPORT_LIVE_GPT.md`](REPORT_LIVE_GPT.md); raw data →
`data/live_ladder*`, `data/live_gpt_matrix*`, `data/live_chr_demo.csv`.
