"""Targeted backfill / spot-check for the live matrix.

The full-matrix run (run_live.py) can lose cells to a `claude` session limit
mid-run. This script re-runs a specific list of (model, approach, task) cells
k times, scores + CHR-validates them exactly like run_live, then merges into the
existing data/live_pilot.jsonl -- dropping any superseded rows for those cells
and any session-limit casualties -- and rebuilds live_pilot.csv + live_matrix.csv.

It is intentionally explicit about which cells it touches so the merge is
auditable. Edit TARGETS below (or pass nothing and use the defaults, which cover
the 2026-05-31 session-limit gap: Opus 4.7 wg-add-peer + an Opus 4.8 spot-check).

Usage:
  .venv/bin/python harness/live/backfill_cells.py
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import run_live as rl  # same dir; provides call_claude/build_prompt/etc.
from lib.scorer import predict_label

DATA = Path(__file__).resolve().parents[2] / "data"

# (model, approach, task, repeats). Defaults fill the 2026-05-31 limit gap.
TARGETS = [
    # Opus 4.7: wg-add-peer cells lost to the session limit -> clean full task.
    ("claude-opus-4-7", "baseline", "wg-add-peer", 3),
    ("claude-opus-4-7", "rosetta-context", "wg-add-peer", 3),
    ("claude-opus-4-7", "skills-context", "wg-add-peer", 3),
    # Opus 4.8 spot-check: the route-blackhole crux across conditions ...
    ("claude-opus-4-8", "baseline", "route-blackhole", 3),
    ("claude-opus-4-8", "rosetta-context", "route-blackhole", 3),
    ("claude-opus-4-8", "skills-context", "route-blackhole", 3),
    # ... plus an easy-task sanity that the model is functioning at all.
    ("claude-opus-4-8", "baseline", "vlan-create-basic", 2),
]


def is_limited(r: dict) -> bool:
    return (r.get("exit_code") == 1) or ("session limit" in (r.get("raw_result") or ""))


def run_cells(targets) -> list[dict]:
    tasks = rl.load_tasks()
    chr_ = rl.chr_validator()
    new_records = []
    try:
        for model, ap_name, tid, reps in targets:
            task = tasks[tid]
            prompt = rl.build_prompt(task, ap_name)
            phash = hashlib.sha256(prompt.encode()).hexdigest()[:12]
            for rep in range(reps):
                rec = rl.call_claude(prompt, model)
                cmds = rl.parse_commands(rec.get("result", ""))
                if "session limit" in (rec.get("result") or ""):
                    print(f"  !! session limit again on {model} {tid}; stopping early")
                    return new_records
                label, sub = predict_label(task, cmds) if cmds else ("empty", {})
                validity = "n/a"
                if chr_ is not None and cmds:
                    verdicts = [chr_.validate(c) for c in cmds]
                    validity = "ok" if all(v[0] for v in verdicts) else "error"
                row = {
                    "approach": ap_name, "task": tid, "model": model, "rep": rep,
                    "label": label, "syntax_valid": validity, "n_cmds": len(cmds),
                    "n_gold": len(task["gold_commands"]), "exit_code": rec["exit_code"],
                    "cost_usd": rec.get("cost_usd"), "prompt_hash": phash,
                }
                new_records.append({
                    **row, "prompt": prompt, "raw_result": rec.get("result", ""),
                    "parsed_commands": cmds, "scorer_sub": sub,
                    "num_turns": rec.get("num_turns"), "wall_s": rec.get("wall_s"),
                })
                print(f"  {model:24} {ap_name:16} {tid:20} rep{rep} -> "
                      f"{label:13} syntax={validity:5} ${rec.get('cost_usd') or 0:.3f}")
    finally:
        if chr_ is not None and getattr(chr_, "proc", None) is not None:
            chr_.stop()
    return new_records


def rebuild(merged: list[dict]) -> None:
    fields = ["approach", "task", "model", "rep", "label", "syntax_valid",
              "n_cmds", "n_gold", "exit_code", "cost_usd", "prompt_hash"]
    with open(DATA / "live_ladder.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(merged)
    cell_keys = sorted({(r["model"], r["approach"], r["task"]) for r in merged})
    matrix_rows = []
    for model, ap_name, tid in cell_keys:
        sub = [r for r in merged if r["model"] == model
               and r["approach"] == ap_name and r["task"] == tid]
        labels = [r["label"] for r in sub]
        modal, modal_n = Counter(labels).most_common(1)[0]
        matrix_rows.append({
            "model": model, "approach": ap_name, "task": tid, "n_rep": len(sub),
            "n_perfect": sum(1 for r in sub if r["label"] == "perfect"),
            "n_syntax_ok": sum(1 for r in sub if r["syntax_valid"] == "ok"),
            "modal_label": modal, "agreement": round(modal_n / len(sub), 2),
            "labels": "|".join(labels),
        })
    with open(DATA / "live_ladder_matrix.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(matrix_rows[0].keys()))
        w.writeheader()
        w.writerows(matrix_rows)
    with open(DATA / "live_ladder.jsonl", "w") as fh:
        for r in merged:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> None:
    existing = [json.loads(l) for l in open(DATA / "live_ladder.jsonl")]
    print(f"[backfill] existing rows: {len(existing)}")
    new = run_cells(TARGETS)
    print(f"[backfill] new rows: {len(new)}")

    touched = {(m, a, t) for m, a, t, _ in TARGETS}
    # keep rows that are (a) not a session-limit casualty and (b) not a cell we
    # just re-ran (those are superseded by `new`).
    kept = [r for r in existing
            if not is_limited(r) and (r["model"], r["approach"], r["task"]) not in touched]
    dropped = len(existing) - len(kept)
    merged = kept + new
    print(f"[backfill] dropped {dropped} (limited or superseded); merged total: {len(merged)}")
    rebuild(merged)

    by_model = Counter(r["model"] for r in merged)
    print("[backfill] rows per model:")
    for m, n in sorted(by_model.items()):
        print(f"    {m:30} {n}")
    print(f"  wrote {DATA/'live_ladder.csv'}, live_ladder.jsonl, live_ladder_matrix.csv")


if __name__ == "__main__":
    main()
