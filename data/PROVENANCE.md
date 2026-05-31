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

The current snapshots were first captured while the benchmark lived under
`/Users/amm0/Lab/mikrotik-mcp/benchmark` and were migrated into this standalone
repo on 2026-05-31.

Refresh with:

```bash
MIKROTIK_MCP_PATH=~/Lab/mikrotik-mcp ROSETTA_BIN=~/GitHub/rosetta/bin/rosetta.js ./run_all.sh --refresh-tools
```

That command updates `data/mcp_tools.json`, `data/rosetta_tools.json`,
`data/skills.json`, and `data/provenance.json`.
