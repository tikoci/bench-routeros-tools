"""Re-validate the syntax_valid column of the live ladder against CHR.

The merged lib/chr.py briefly mis-detected the verb in multi-segment *space-form*
paths (`/ip route add ...`), so it skipped argument validation and returned a
false `ok` (e.g. `type=blackhole` in space form). After fixing chr.py, this
re-runs the CHR `/console/inspect` validator over the already-emitted commands in
data/live_ladder.jsonl (no model calls), updates `syntax_valid`, and rebuilds
live_ladder.{csv,jsonl} + live_ladder_matrix.csv.

Usage:
  .venv/bin/python harness/live/revalidate_ladder_syntax.py
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

DATA = Path(__file__).resolve().parents[2] / "data"


def main() -> None:
    from lib.chr import Chr

    rows = [json.loads(l) for l in open(DATA / "live_ladder.jsonl")]
    chr_ = Chr().start()
    cache: dict[str, bool] = {}

    def cmd_ok(cmd: str) -> bool:
        if cmd not in cache:
            cache[cmd] = chr_.validate(cmd)[0]
        return cache[cmd]

    changed = 0
    try:
        for r in rows:
            cmds = r.get("parsed_commands") or []
            new = "n/a" if not cmds else ("ok" if all(cmd_ok(c) for c in cmds) else "error")
            if new != r.get("syntax_valid"):
                changed += 1
            r["syntax_valid"] = new
    finally:
        if getattr(chr_, "proc", None) is not None:
            chr_.stop()

    print(f"re-validated {len(rows)} rows; {changed} syntax_valid changed; "
          f"{len(cache)} unique commands")

    with open(DATA / "live_ladder.jsonl", "w") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    fields = ["approach", "task", "model", "rep", "label", "syntax_valid",
              "n_cmds", "n_gold", "exit_code", "cost_usd", "prompt_hash"]
    with open(DATA / "live_ladder.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    keys = sorted({(r["model"], r["approach"], r["task"]) for r in rows})
    mrows = []
    for m, a, t in keys:
        sub = [r for r in rows if r["model"] == m and r["approach"] == a and r["task"] == t]
        labs = [r["label"] for r in sub]
        modal, mn = Counter(labs).most_common(1)[0]
        mrows.append({"model": m, "approach": a, "task": t, "n_rep": len(sub),
                      "n_perfect": sum(1 for r in sub if r["label"] == "perfect"),
                      "n_syntax_ok": sum(1 for r in sub if r["syntax_valid"] == "ok"),
                      "modal_label": modal, "agreement": round(mn / len(sub), 2),
                      "labels": "|".join(labs)})
    with open(DATA / "live_ladder_matrix.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(mrows[0].keys()))
        w.writeheader()
        w.writerows(mrows)
    print("rebuilt live_ladder.{csv,jsonl} + live_ladder_matrix.csv")


if __name__ == "__main__":
    main()
