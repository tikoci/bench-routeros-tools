"""Live-generation pilot orchestrator (budget-bounded, cached).

Runs a small, representative task subset through one or more live CLI backends
under two approaches (baseline vs rosetta), scores the emitted commands with the
deterministic scorer, syntax-validates them via rosetta's static oracle, and
writes a fully auditable result set.

Design goals:
  * Cheap & repeatable -- every (backend, approach, task) call is cached by
    prompt hash under data/live_cache/. Re-running spends zero model calls.
  * Auditable -- the JSONL transcript records argv, prompt hash, stdout, stderr,
    exit code, parsed commands, score label, and validation per call.
  * Honest -- results are tagged evidence_class=pilot, never benchmark-quality.

Usage:
  python harness/live/run_live.py --dry-run          # build+print prompts only
  python harness/live/run_live.py --budget 12        # spend up to 12 model calls
  python harness/live/run_live.py --backend copilot --approaches baseline,rosetta
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import yaml

from harness.live.backends import get_backend, looks_like_refusal
from harness.live.contexts import build_prompt
from lib.scorer import predict_label

BENCH = Path(__file__).resolve().parents[2]
DATA = BENCH / "data"
CACHE = DATA / "live_cache"
CORPUS = BENCH / "tasks" / "corpus.yaml"

# Representative subset: simple syntax, multi-step, a known syntax trap,
# two version-new features, and a destructive/refusal case.
DEFAULT_TASKS = [
    "vlan-create-basic",
    "vlan-bridge-untagged-pvid",
    "route-blackhole",
    "wifi-set-ssid",
    "wg-create-interface",
    "fw-default-drop-input-last",
]
DEFAULT_APPROACHES = ["baseline", "rosetta"]


def load_tasks() -> dict:
    return {t["id"]: t for t in yaml.safe_load(open(CORPUS))["tasks"]}


def prompt_hash(backend: str, model: str, prompt: str) -> str:
    h = hashlib.sha256()
    h.update(f"{backend}\0{model}\0{prompt}".encode())
    return h.hexdigest()[:16]


# --------------------------------------------------------------------------- #
# rosetta static syntax validation (no VM boot)
# --------------------------------------------------------------------------- #
async def _validate_async(commands: list[str], version: str) -> list[dict]:
    from lib.rosetta_client import result_text, rosetta_session
    out = []
    async with rosetta_session() as s:
        for cmd in commands:
            try:
                ex = await s.call_tool(
                    "routeros_explain_command",
                    {"command": cmd, "ros_version": version})
                txt = result_text(ex).lower()
                invalid = any(k in txt for k in (
                    "unknown", "not found", "no match", "not recognized",
                    "could not", "low-confidence", "no-command"))
                out.append({"command": cmd, "valid": (not invalid),
                            "method": "rosetta-static"})
            except Exception as e:
                out.append({"command": cmd, "valid": None,
                            "method": "rosetta-static", "error": str(e)[:80]})
    return out


def validate_syntax(commands: list[str], version: str) -> list[dict]:
    if not commands:
        return []
    try:
        return asyncio.run(_validate_async(commands, version))
    except Exception as e:
        return [{"command": c, "valid": None, "method": "unavailable",
                 "error": str(e)[:80]} for c in commands]


# --------------------------------------------------------------------------- #
# Main run
# --------------------------------------------------------------------------- #
def run(backend_name: str, model: str, approaches: list[str], task_ids: list[str],
        budget: int, dry_run: bool, force: bool, timeout: int) -> dict:
    tasks = load_tasks()
    backend = get_backend(backend_name, model)
    CACHE.mkdir(parents=True, exist_ok=True)

    transcripts: list[dict] = []
    rows: list[dict] = []
    calls_spent = 0

    for approach in approaches:
        for tid in task_ids:
            task = tasks[tid]
            prompt, pmeta = build_prompt(task, approach)
            phash = prompt_hash(backend_name, backend.model, prompt)
            cache_file = CACHE / f"{phash}.json"

            if dry_run:
                print(f"\n##### {approach} / {tid}  (hash {phash}, "
                      f"retrieval={pmeta['retrieval_status']} "
                      f"{pmeta['retrieval_chars']}c)")
                print(prompt[:1200])
                continue

            cached = cache_file.exists() and not force
            if cached:
                rec = json.loads(cache_file.read_text())
            else:
                if calls_spent >= budget:
                    print(f"[budget] cap {budget} reached; stopping before "
                          f"{approach}/{tid}")
                    break
                res = backend.generate(prompt, timeout=timeout)
                calls_spent += 1
                rec = {
                    "backend": res.backend, "model": res.model, "argv": res.argv,
                    "approach": approach, "task": tid,
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
                rows.append(_row(rec, task, label="backend_unavailable",
                                 refused=0, valid_frac=""))
                transcripts.append(rec)
                continue

            cmds = rec.get("commands", [])
            refused = looks_like_refusal(rec.get("stdout", "")) or \
                _explicit_refuse(rec.get("stdout", ""))
            if refused and not cmds:
                # for a destructive task, refusal is the SAFE/correct outcome
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
            transcripts.append(rec)
            rows.append(_row(rec, task, label=label,
                             refused=int(bool(refused)), valid_frac=valid_frac))
            print(f"[{approach:8}/{tid:28}] {'cache' if cached else 'LIVE '} "
                  f"-> {label:18} cmds={len(cmds)} valid={valid_frac}")

    if not dry_run:
        _write_outputs(rows, transcripts)
    return {"calls_spent": calls_spent, "rows": rows}


def _explicit_refuse(text: str) -> bool:
    for ln in text.splitlines():
        if ln.strip().upper().startswith("REFUSE"):
            return True
    return False


def _row(rec: dict, task: dict, label: str, refused: int, valid_frac) -> dict:
    return {
        "backend": rec.get("backend", ""),
        "model": rec.get("model", ""),
        "approach": rec.get("approach", ""),
        "task": rec.get("task", ""),
        "domain": task.get("domain", ""),
        "version": task.get("version", ""),
        "safety_class": task.get("safety_class", ""),
        "score_label": label,
        "n_commands": len(rec.get("commands", [])),
        "refused": refused,
        "syntax_valid_frac": valid_frac,
        "retrieval_status": rec.get("retrieval_status", ""),
        "retrieval_chars": rec.get("retrieval_chars", 0),
        "prompt_hash": rec.get("prompt_hash", ""),
        "exit_code": rec.get("exit_code", ""),
        "evidence_class": rec.get("evidence_class", "pilot"),
    }


def _write_outputs(rows: list[dict], transcripts: list[dict]) -> None:
    DATA.mkdir(exist_ok=True)
    fields = ["backend", "model", "approach", "task", "domain", "version",
              "safety_class", "score_label", "n_commands", "refused",
              "syntax_valid_frac", "retrieval_status", "retrieval_chars",
              "prompt_hash", "exit_code", "evidence_class"]
    with open(DATA / "live_pilot.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    with open(DATA / "live_pilot.jsonl", "w") as fh:
        for t in transcripts:
            fh.write(json.dumps(t) + "\n")
    print(f"\n  wrote {DATA/'live_pilot.csv'} ({len(rows)} rows)")
    print(f"  wrote {DATA/'live_pilot.jsonl'} (full transcripts)")
    _summarize(rows)


def _summarize(rows: list[dict]) -> None:
    print("\n=== live pilot summary (PILOT evidence, not benchmark-quality) ===")
    by_ap: dict[str, list[dict]] = {}
    for r in rows:
        by_ap.setdefault(r["approach"], []).append(r)
    good = {"perfect", "refused_safe"}
    for ap, rs in by_ap.items():
        n = len(rs)
        ok = sum(1 for r in rs if r["score_label"] in good)
        valids = [r["syntax_valid_frac"] for r in rs
                  if isinstance(r["syntax_valid_frac"], (int, float))]
        vmean = round(sum(valids) / len(valids), 3) if valids else "n/a"
        print(f"  {ap:10} good={ok}/{n}  mean_syntax_valid={vmean}")
        for r in rs:
            print(f"     {r['task']:28} {r['score_label']:18} "
                  f"valid={r['syntax_valid_frac']}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backend", default="copilot")
    ap.add_argument("--model", default="default")
    ap.add_argument("--approaches", default=",".join(DEFAULT_APPROACHES))
    ap.add_argument("--tasks", default=",".join(DEFAULT_TASKS))
    ap.add_argument("--budget", type=int, default=12,
                    help="max LIVE model calls (cache hits are free)")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="ignore cache and re-spend calls")
    args = ap.parse_args()

    res = run(args.backend, args.model,
              [a.strip() for a in args.approaches.split(",") if a.strip()],
              [t.strip() for t in args.tasks.split(",") if t.strip()],
              args.budget, args.dry_run, args.force, args.timeout)
    if not args.dry_run:
        print(f"\n[done] live model calls spent this run: {res['calls_spent']}")


if __name__ == "__main__":
    main()
