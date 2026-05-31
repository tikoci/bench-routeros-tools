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

`data/live_cache/` (raw cached model output, keyed by prompt hash) is
**git-ignored**: it is regenerable and avoids committing model output verbatim.
Reruns of `run_live.py` are free when the cache is present.

> **Known corpus discrepancy surfaced by the device:** `route-blackhole` gold is
> `blackhole=yes`, but RouterOS 7.23 rejects it and accepts the bare `blackhole`
> flag (rosetta docs, aligned ~7.22, also describe it as a flag). The gold was
> left unchanged pending 7.22.x device confirmation; see `live_chr_demo.csv` and
> `docs/REPORT_LIVE.md` Finding 1. This is a corpus item to device-validate.

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
