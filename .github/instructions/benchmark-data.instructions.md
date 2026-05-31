---
description: "Use when editing benchmark approaches, task corpus, fixture YAML, committed data snapshots, or provenance files."
applyTo: "approaches.yaml,tasks/**/*.yaml,fixtures/**/*.yaml,data/**/*.json,data/**/*.csv,data/PROVENANCE.md"
---

# Benchmark data and corpus

Treat benchmark inputs and result snapshots as reproducible artifacts, not
scratch output.

- `approaches.yaml` is the source of truth for compared configurations.
- `tasks/corpus.yaml` is the RouterOS task corpus; preserve gold commands,
  decoys, version tags, state-dependency tags, and safety labels together.
- `data/*.json` are input snapshots. `data/*.csv` are reproducible result
  snapshots. Inspect diffs carefully before committing regenerated files.
- Update `data/PROVENANCE.md` when the capture method, source checkout, command,
  or external artifact behind a snapshot changes.
- Do not infer live-agent effectiveness from deterministic proxies; keep claims
  aligned with `REPORT.md` until live runs are wired and measured.
- Never include real router credentials, customer hostnames, WinBox CDBs, Dude
  databases, or packet captures in corpus, fixture, prompt, or data files.