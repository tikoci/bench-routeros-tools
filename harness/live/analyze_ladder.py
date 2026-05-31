"""Summarize the Claude frontier-boxing ladder for the live-report write-up.

Reads data/live_ladder_matrix.csv (per-cell aggregate) and data/live_ladder.jsonl
(raw per-run) and prints the specific cuts the report argues from:

  1. perfect-rate per model x condition, with the k denominator (the ladder).
  2. the route-blackhole crux cell across all models x conditions: modal label,
     agreement, and the actual commands emitted (does the frontier still write
     the fake `type=blackhole`?).
  3. over-specification watch: nat-dstnat-port-forward, where augmentation made
     Sonnet add a non-gold arg in the pilot -- does that persist up the ladder?
  4. instability: every cell whose repeats disagree (agreement < 1.0).
  5. cost per model.

Usage:
  .venv/bin/python harness/live/analyze_ladder.py
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"
# short labels keep the tables readable
SHORT = {
    "claude-haiku-4-5-20251001": "Haiku 4.5",
    "claude-sonnet-4-6": "Sonnet 4.6",
    "claude-opus-4-7": "Opus 4.7",
    "claude-opus-4-8": "Opus 4.8",
}
MODEL_ORDER = ["claude-haiku-4-5-20251001", "claude-sonnet-4-6",
               "claude-opus-4-7", "claude-opus-4-8"]
COND_ORDER = ["baseline", "rosetta-context", "skills-context"]


def load_matrix() -> list[dict]:
    with open(DATA / "live_ladder_matrix.csv") as fh:
        return list(csv.DictReader(fh))


def load_runs() -> list[dict]:
    rows = []
    with open(DATA / "live_ladder.jsonl") as fh:
        for ln in fh:
            rows.append(json.loads(ln))
    return rows


def models_present(matrix: list[dict]) -> list[str]:
    seen = {m["model"] for m in matrix}
    return [m for m in MODEL_ORDER if m in seen] + sorted(seen - set(MODEL_ORDER))


def sh(m: str) -> str:
    return SHORT.get(m, m)


def perfect_ladder(matrix: list[dict]) -> None:
    print("\n## 1. perfect-rate ladder (perfect cells / tasks, summed over k repeats)\n")
    models = models_present(matrix)
    # denominator: tasks * repeats per (model, condition)
    print(f"{'condition':16} " + " ".join(f"{sh(m):>22}" for m in models))
    for cond in COND_ORDER:
        cells = [m for m in matrix if m["approach"] == cond]
        line = f"{cond:16} "
        for model in models:
            sub = [c for c in cells if c["model"] == model]
            np = sum(int(c["n_perfect"]) for c in sub)
            nr = sum(int(c["n_rep"]) for c in sub)
            sv = sum(int(c["n_syntax_ok"]) for c in sub)
            line += f"{f'{np}/{nr}p {sv}/{nr}s':>22} "
        print(line)
    print("\n(p = perfect generations, s = syntax-valid generations, of tasks*k)")


def crux_task(runs: list[dict], task: str, note: str) -> None:
    print(f"\n## crux: {task} -- {note}\n")
    by = defaultdict(list)
    for r in runs:
        if r["task"] == task:
            by[(r["model"], r["approach"])].append(r)
    models = [m for m in MODEL_ORDER if any(k[0] == m for k in by)]
    for model in models:
        print(f"  {sh(model)}")
        for cond in COND_ORDER:
            rs = sorted(by.get((model, cond), []), key=lambda r: r["rep"])
            if not rs:
                continue
            labels = ",".join(r["label"] for r in rs)
            # show the distinct commands emitted across repeats
            cmds = []
            for r in rs:
                c = " ; ".join(r.get("parsed_commands") or []) or "(empty)"
                if c not in cmds:
                    cmds.append(c)
            print(f"    {cond:16} [{labels}]")
            for c in cmds:
                print(f"        {c[:140]}")


def instability(matrix: list[dict]) -> None:
    print("\n## 4. unstable cells (repeats disagree -> single-shot would be noise)\n")
    bad = [m for m in matrix if float(m["agreement"]) < 1.0]
    if not bad:
        print("  none -- every cell's repeats agreed.")
        return
    for m in sorted(bad, key=lambda x: (x["model"], x["approach"], x["task"])):
        print(f"  {sh(m['model']):11} {m['approach']:15} {m['task']:26} "
              f"labels=[{m['labels']}] agree={m['agreement']}")
    print(f"\n  {len(bad)} / {len(matrix)} cells unstable")


def cost(runs: list[dict]) -> None:
    print("\n## 5. cost per model\n")
    agg = defaultdict(lambda: [0.0, 0])
    for r in runs:
        c = r.get("cost_usd") or 0.0
        agg[r["model"]][0] += c
        agg[r["model"]][1] += 1
    total = 0.0
    for model in models_present_from_runs(runs):
        s, n = agg[model]
        total += s
        print(f"  {sh(model):11} ${s:6.2f}  ({n} calls, ${s/max(n,1):.4f}/call)")
    print(f"  {'TOTAL':11} ${total:6.2f}")


def models_present_from_runs(runs: list[dict]) -> list[str]:
    seen = {r["model"] for r in runs}
    return [m for m in MODEL_ORDER if m in seen] + sorted(seen - set(MODEL_ORDER))


def main() -> None:
    matrix = load_matrix()
    runs = load_runs()
    perfect_ladder(matrix)
    crux_task(runs, "route-blackhole",
              "does the frontier still emit the fake type=blackhole?")
    crux_task(runs, "nat-dstnat-port-forward",
              "does augmentation still invite non-gold over-specification?")
    instability(matrix)
    cost(runs)


if __name__ == "__main__":
    main()
