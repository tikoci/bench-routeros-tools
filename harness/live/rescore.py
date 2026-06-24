"""Offline re-score: re-apply the current scorer to already-captured generations.

When only the *scoring* changes (e.g. route-unreachable became a removed_capability
trap) -- not the model outputs -- there is no need to re-run `claude -p` and pay
for it again. This reads data/live_ladder.jsonl, recomputes label + scorer_sub from
each row's stored `parsed_commands` against the current corpus + lib.scorer, and
rewrites live_ladder.jsonl/.csv/_matrix.csv in run_live_ladder's current schema.

Everything device- or model-derived (syntax_valid, cost_usd, num_turns,
cited_source, raw_result) is preserved verbatim -- only the deterministic scorer
output is refreshed. session-limited rows are passed through untouched. For a
removed_capability task an empty candidate scores trap-avoided (recognized the
removal), matching run_live_ladder's live branch.

Re-scoring is idempotent for unchanged tasks; the run prints any label that moved
so the diff is auditable.

Usage:
  .venv/bin/python harness/live/rescore.py
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import run_live_ladder as rl  # same dir
from lib.scorer import predict_label

DATA = Path(__file__).resolve().parents[2] / "data"


def rescore_row(row: dict, task: dict) -> dict:
    if row.get("label") == "session-limited":
        return row
    cmds = row.get("parsed_commands") or []
    if cmds:
        label, sub = predict_label(task, cmds)
    elif task.get("removed_capability"):
        label, sub = predict_label(task, [])
    else:
        label, sub = "empty", {}
    out = dict(row)
    out["label"], out["scorer_sub"] = label, sub
    return out


def main() -> None:
    tasks = rl.load_tasks()
    rows = [json.loads(l) for l in open(DATA / "live_ladder.jsonl")]
    print(f"[rescore] rows: {len(rows)}")

    moved = 0
    new_rows = []
    for r in rows:
        nr = rescore_row(r, tasks[r["task"]])
        if nr["label"] != r["label"]:
            moved += 1
            print(f"  {r['model']:26} {r['approach']:16} {r['task']:22} "
                  f"rep{r['rep']}: {r['label']} -> {nr['label']}")
        new_rows.append(nr)
    print(f"[rescore] labels moved: {moved}")

    # rewrite jsonl (full records) + csv + matrix, matching run_live_ladder schema
    with open(DATA / "live_ladder.jsonl", "w") as fh:
        for r in new_rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    csv_fields = ["approach", "task", "model", "rep", "label", "syntax_valid",
                  "n_cmds", "n_gold", "exit_code", "cost_usd", "num_turns",
                  "cited_source", "prompt_hash"]
    with open(DATA / "live_ladder.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=csv_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(new_rows)

    cell_keys = sorted({(r["model"], r["approach"], r["task"]) for r in new_rows})
    matrix_rows = []
    for model, ap_name, tid in cell_keys:
        sub = [r for r in new_rows if r["model"] == model
               and r["approach"] == ap_name and r["task"] == tid]
        real = [r for r in sub if r["label"] != "session-limited"]
        labels = [r["label"] for r in real]
        if labels:
            modal, modal_n = Counter(labels).most_common(1)[0]
            agreement = round(modal_n / len(labels), 2)
        else:
            modal, agreement = "session-limited", 0.0
        matrix_rows.append({
            "model": model, "approach": ap_name, "task": tid,
            "n_rep": len(sub), "n_real": len(real),
            "n_perfect": sum(1 for r in real if r["label"] == "perfect"),
            "n_syntax_ok": sum(1 for r in real if r["syntax_valid"] == "ok"),
            "n_cited": sum(1 for r in real if r.get("cited_source")),
            "modal_label": modal, "agreement": agreement,
            "labels": "|".join(labels) if labels else "session-limited",
        })
    with open(DATA / "live_ladder_matrix.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(matrix_rows[0].keys()))
        w.writeheader()
        w.writerows(matrix_rows)
    print(f"  wrote {DATA/'live_ladder.csv'}, live_ladder.jsonl, live_ladder_matrix.csv")


if __name__ == "__main__":
    main()
