"""Cross-model / cross-backend live matrix (GPT side, via Copilot CLI).

This is the GPT-family companion to the Claude live mini-matrix in REPORT §8.
It reuses the *same* prompt builder, scorer, syntax validator, and prompt-hash
cache as ``run_live.py`` -- the only new thing is sweeping several models and
writing to a **separate** artifact so it never clobbers ``live_pilot.*`` (the
copilot-default pilot) or the parallel Claude ``live_matrix.*``.

Why a separate runner: the interesting axis here is *backend/vendor*, not just
context. Copilot CLI (GPT family) vs Claude Code (Claude family) on the exact
same RouterOS tasks is itself a finding -- especially on the ``route-blackhole``
crux, where both Claude models hallucinated the fake ``type=blackhole`` property.

Cost control (measured 2026-05-31, Copilot premium-request multipliers):
  * gpt-4.1     -> 0    premium/call  (full grid, free)
  * gpt-5-mini  -> 0    premium/call  (full grid, free)
  * gpt-5.5     -> ~7.5 premium/call  (DIAGNOSTIC SUBSET ONLY)
So the expensive frontier model is spent only on the two sharpest axes
(training-knowledge gap + version-new feature), while the free models cover the
full task set for breadth.

Usage:
  python harness/live/run_gpt_matrix.py            # cache-first; spends premium only for uncached gpt-5.5 cells
  python harness/live/run_gpt_matrix.py --dry-run  # print the planned cells + costs, no calls
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import yaml

from harness.live.backends import get_backend, looks_like_refusal
from harness.live.contexts import build_prompt
from harness.live.run_live import (
    CACHE, DATA, prompt_hash, validate_syntax, _explicit_refuse, load_tasks,
)
from lib.scorer import predict_label

# Full diagnostic task set (same 6 as the copilot-default pilot).
FULL_TASKS = [
    "vlan-create-basic",
    "vlan-bridge-untagged-pvid",
    "route-blackhole",
    "wifi-set-ssid",
    "wg-create-interface",
    "fw-default-drop-input-last",
]
# The two sharpest axes for the expensive frontier model:
#   route-blackhole -> training-knowledge gap (the type=blackhole crux)
#   wifi-set-ssid   -> 7.22+ version-new menu
CRUX_TASKS = ["route-blackhole", "wifi-set-ssid"]
APPROACHES = ["baseline", "rosetta"]

# model -> (tasks, approx premium-request multiplier per call)
PLAN = {
    "gpt-4.1":    (FULL_TASKS, 0.0),
    "gpt-5-mini": (FULL_TASKS, 0.0),
    "gpt-5.5":    (CRUX_TASKS, 7.5),
}

OUT_CSV = DATA / "live_gpt_matrix.csv"
OUT_JSONL = DATA / "live_gpt_matrix.jsonl"

FIELDS = ["backend", "model", "premium_mult", "approach", "task", "domain",
          "version", "safety_class", "score_label", "n_commands", "refused",
          "syntax_valid_frac", "first_command", "retrieval_status",
          "prompt_hash", "cached", "exit_code", "evidence_class"]


def _score_record(rec: dict, task: dict) -> tuple[str, int, str]:
    cmds = rec.get("commands", [])
    refused = looks_like_refusal(rec.get("stdout", "")) or \
        _explicit_refuse(rec.get("stdout", ""))
    if refused and not cmds:
        expected_refuse = task.get("safety_class") == "destructive" or \
            bool(task.get("forbidden_commands"))
        label = "refused_safe" if expected_refuse else "refused_unhelpful"
    else:
        label, _ = predict_label(task, cmds)
    val = validate_syntax(cmds, task.get("version_exact", "7.22.1"))
    valid_vals = [v["valid"] for v in val if v["valid"] is not None]
    valid_frac = (round(sum(1 for v in valid_vals if v) / len(valid_vals), 3)
                  if valid_vals else "")
    rec["score_label"] = label
    rec["validation"] = val
    rec["refused"] = int(bool(refused))
    return label, int(bool(refused)), valid_frac


def run(dry_run: bool, budget_premium: float, force: bool, timeout: int) -> None:
    tasks = load_tasks()
    CACHE.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    transcripts: list[dict] = []
    spent_premium = 0.0
    live_calls = 0

    for model, (task_ids, mult) in PLAN.items():
        backend = get_backend("copilot", model)
        for approach in APPROACHES:
            for tid in task_ids:
                task = tasks[tid]
                prompt, pmeta = build_prompt(task, approach)
                phash = prompt_hash("copilot", model, prompt)
                cache_file = CACHE / f"{phash}.json"
                cached = cache_file.exists() and not force

                if dry_run:
                    tag = "cache" if cached else f"LIVE ~{mult}prem"
                    print(f"  {model:11} {approach:8} {tid:28} [{tag}]")
                    continue

                if cached:
                    rec = json.loads(cache_file.read_text())
                else:
                    if spent_premium + mult > budget_premium:
                        print(f"[budget] premium cap {budget_premium} would be "
                              f"exceeded by {model}/{approach}/{tid} "
                              f"(+{mult}); skipping.")
                        continue
                    res = backend.generate(prompt, timeout=timeout)
                    live_calls += 1
                    spent_premium += mult
                    rec = {
                        "backend": res.backend, "model": res.model,
                        "argv": res.argv, "approach": approach, "task": tid,
                        "prompt_hash": phash, "prompt_chars": len(prompt),
                        "retrieval_status": pmeta["retrieval_status"],
                        "retrieval_chars": pmeta["retrieval_chars"],
                        "available": res.available, "error": res.error,
                        "exit_code": res.exit_code,
                        "stdout": res.stdout, "stderr": res.stderr,
                        "commands": res.commands,
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "evidence_class": "pilot",
                    }
                    if res.available:
                        cache_file.write_text(json.dumps(rec, indent=2))

                if not rec.get("available", True):
                    print(f"  {model:11} {approach:8} {tid:28} UNAVAILABLE "
                          f"({rec.get('error','')[:40]})")
                    continue

                label, refused, valid_frac = _score_record(rec, task)
                cmds = rec.get("commands", [])
                rows.append({
                    "backend": "copilot", "model": model, "premium_mult": mult,
                    "approach": approach, "task": tid,
                    "domain": task.get("domain", ""),
                    "version": task.get("version", ""),
                    "safety_class": task.get("safety_class", ""),
                    "score_label": label, "n_commands": len(cmds),
                    "refused": refused, "syntax_valid_frac": valid_frac,
                    "first_command": (cmds[0] if cmds else ""),
                    "retrieval_status": rec.get("retrieval_status", ""),
                    "prompt_hash": phash, "cached": int(cached),
                    "exit_code": rec.get("exit_code", ""),
                    "evidence_class": "pilot",
                })
                transcripts.append(rec)
                print(f"  {model:11} {approach:8} {tid:28} "
                      f"{'cache' if cached else 'LIVE ':5} -> {label:18} "
                      f"valid={valid_frac} :: {(cmds[0] if cmds else '(none)')[:60]}")

    if dry_run:
        total = sum(mult * len(t) * len(APPROACHES) for t, mult in PLAN.values())
        print(f"\n[dry-run] worst-case premium if nothing cached: ~{total}")
        return

    _write(rows, transcripts)
    print(f"\n[done] live calls this run: {live_calls}, "
          f"premium spent (uncached only): ~{round(spent_premium, 2)}")
    _summary(rows)


def _write(rows: list[dict], transcripts: list[dict]) -> None:
    DATA.mkdir(exist_ok=True)
    with open(OUT_CSV, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    with open(OUT_JSONL, "w") as fh:
        for t in transcripts:
            fh.write(json.dumps(t) + "\n")
    print(f"\n  wrote {OUT_CSV} ({len(rows)} rows)")
    print(f"  wrote {OUT_JSONL}")


def _summary(rows: list[dict]) -> None:
    print("\n=== GPT cross-model matrix (PILOT evidence, copilot backend) ===")
    good = {"perfect", "refused_safe"}
    by_mc: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        by_mc.setdefault((r["model"], r["approach"]), []).append(r)
    for (model, ap), rs in by_mc.items():
        ok = sum(1 for r in rs if r["score_label"] in good)
        print(f"  {model:11} {ap:8} good={ok}/{len(rs)}")
    # crux spotlight
    print("\n  route-blackhole crux (does the model write the fake type=blackhole?):")
    for r in rows:
        if r["task"] == "route-blackhole":
            print(f"    {r['model']:11} {r['approach']:8} {r['score_label']:14} "
                  f":: {r['first_command']}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--budget-premium", type=float, default=35.0,
                    help="max premium requests to spend on UNCACHED calls")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    run(args.dry_run, args.budget_premium, args.force, args.timeout)


if __name__ == "__main__":
    main()
