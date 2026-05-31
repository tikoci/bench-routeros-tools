# Data Provenance

The benchmark commits tool-schema and result snapshots so structural metrics
reproduce without live MCP servers.

## Captured artifacts

| Artifact | Source |
| --- | --- |
| `mcp_tools.json` | `mcp_mikrotik.app` FastMCP tool list from `jeff-nasseri/mikrotik-mcp` |
| `rosetta_tools.json` | rosetta MCP stdio `list_tools` |
| `skills.json` | `routeros-*` skill frontmatter and bodies from `tikoci/routeros-skills` |
| `*.csv` | `./run_all.sh` outputs generated from the committed corpus and tool snapshots |

## Live-pilot artifacts (PILOT evidence)

These are committed as a reproducible snapshot of the first grounded live-agent
pilot. They are **pilot evidence, not benchmark-quality** (single backend
`copilot -p`, n=6 tasks). See [`docs/REPORT_LIVE.md`](../docs/REPORT_LIVE.md).

| Artifact | Source |
| --- | --- |
| `live_pilot.csv` | `harness/live/run_live.py` — per-(approach,task) score row |
| `live_pilot.jsonl` | full transcripts (prompt, emitted commands, label) for each call |
| `live_chr_demo.csv` | `quickchr exec` device verdicts on RouterOS 7.23 (closed-loop demo) |
| `live_gpt_matrix.csv` | `harness/live/run_gpt_matrix.py` — cross-model GPT pilot (gpt-4.1, gpt-5-mini, gpt-5.4, gpt-5.5) via `copilot -p --model` |
| `live_gpt_matrix.jsonl` | full transcripts for the GPT matrix |

The GPT matrix is a cross-vendor companion to the Claude Code live matrix; see
[`docs/REPORT_LIVE_GPT.md`](../docs/REPORT_LIVE_GPT.md). Copilot premium cost is
recorded per row (`premium_mult`): gpt-4.1/gpt-5-mini = 0×, gpt-5.4 = 1×,
gpt-5.5 = 7.5×; the two paid models ran only the two crux tasks to cap spend.

`data/live_cache/` (raw cached model output, keyed by prompt hash) is
**git-ignored**: it is regenerable and avoids committing model output verbatim.
Reruns of `run_live.py` are free when the cache is present.

> **Corpus correction surfaced by the device:** `route-blackhole` gold was
> `blackhole=yes`, but RouterOS 7.23 (CHR) rejects it (`expected end of command`)
> and `type=blackhole` (`bad parameter type`); only the bare `blackhole` flag
> creates the route. The gold was **corrected to the bare flag** on the
> `agents/grounded-data-collection-agents` branch; see `live_chr_demo.csv`,
> `docs/REPORT_LIVE_GPT.md` Finding 1, and the inline note in
> `tasks/corpus.yaml`. Structural result CSVs (`data/results*.csv`, etc.) predate
> this fix and should be regenerated with `./run_all.sh` on the next full run so
> their `route-blackhole` labels reflect the corrected gold.

The structural snapshots above were first captured while the benchmark lived
under
`/Users/amm0/Lab/mikrotik-mcp/benchmark` and were migrated into this standalone
repo on 2026-05-31.

Refresh with:

```bash
MIKROTIK_MCP_PATH=~/Lab/mikrotik-mcp ROSETTA_BIN=~/GitHub/rosetta/bin/rosetta.js ./run_all.sh --refresh-tools
```

That command updates `data/mcp_tools.json`, `data/rosetta_tools.json`,
`data/skills.json`, and `data/provenance.json`.
