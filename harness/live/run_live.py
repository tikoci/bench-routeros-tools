"""Live-generation pilot: ask a real `claude -p` agent for RouterOS commands.

This is the first *live* (non-structural) metric. It is deliberately small and
labeled "pilot evidence", not benchmark-quality data. It implements rung 2 of the
ladder in docs/LIVE_AGENT_HARNESS.md: one backend, a few tasks, no router
mutation, final commands scored by lib.scorer and syntax-validated by the CHR
/console/inspect validator.

Conditions are compared so the result is a *delta* that is robust to whatever
constant RouterOS knowledge the local Claude install carries:

  baseline        : task intent only.
  rosetta-context : same intent, with rosetta's live `routeros_search` result
                    text injected into the prompt (what a rosetta-augmented agent
                    would see). No MCP wiring needed in the subprocess -- we paste
                    the retrieved doc text in, which is faithful to "what the
                    model sees".
  skills-context  : same intent, with the always-on routeros-* skill frontmatter
                    (the router) plus the single best-matching SKILL.md body
                    pasted in (progressive disclosure: the body a skills-aware
                    agent would load for this intent).

Rung 3 (mini-matrix) runs this across more than one model (default: Haiku 4.5 +
Sonnet 4.6) so a gap can be attributed to "model size" vs "missing context".

Isolation: every `claude -p` call runs from a scratch /tmp cwd with
`--disable-slash-commands` (no routeros-* skills), `--strict-mcp-config` (no
rosetta MCP), and `--setting-sources ''` (no user/project settings), so the only
deliberate difference between conditions is the injected text. Residual local
context (e.g. ~/.claude memory) is a documented caveat; the delta cancels it.

Outputs:
  data/live_pilot.csv    one row per (approach, task) run + scorer/validity verdict
  data/live_pilot.jsonl  full per-run record (prompt, prompt hash, raw stdout,
                         exit code, cost, parsed commands) for replay/audit

Rung 3b (frontier-boxing + stability): pass `--repeats k` to run each cell k
times for a stability band (modal label + agreement, written to
data/live_matrix.csv), and `--models` to add frontier models (e.g.
claude-opus-4-7,claude-opus-4-8) so the "would a bigger model fix it from
training alone?" question is answered, not assumed.

Usage:
  .venv/bin/python harness/live/run_live.py            # run the pilot
  .venv/bin/python harness/live/run_live.py --dry-run  # build prompts, no model calls
  .venv/bin/python harness/live/run_live.py --models claude-haiku-4-5-20251001,claude-sonnet-4-6,claude-opus-4-7,claude-opus-4-8 --repeats 3
  LIVE_MODELS=... LIVE_TASKS=... LIVE_REPEATS=3 ...    # env overrides
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import yaml

from lib import context_builders as cb
from lib.scorer import predict_label

BENCH = Path(__file__).resolve().parents[2]
DATA = BENCH / "data"
CORPUS = BENCH / "tasks" / "corpus.yaml"

# A small, balanced subset that stresses different failure modes:
#   easy single-line / multi-step sequence / arg-completeness / "weird syntax"
#   trap (blackhole=yes, not type=blackhole) / connection-state / wireguard.
DEFAULT_TASKS = [
    "vlan-create-basic",
    "vlan-bridge-untagged-pvid",
    "nat-dstnat-port-forward",
    "route-blackhole",
    "fw-allow-established-related",
    "wg-add-peer",
]
# Rung 3 mini-matrix: a small + a larger model so a gap can be attributed to
# model size vs missing context. Override with LIVE_MODELS=a,b.
DEFAULT_MODELS = ["claude-haiku-4-5-20251001", "claude-sonnet-4-6"]
APPROACHES = ["baseline", "rosetta-context", "skills-context"]

OUTPUT_RULE = (
    "Return ONLY the RouterOS CLI command(s) needed, one per line. "
    "No prose, no explanation, no code fences, no comments."
)


def load_tasks() -> dict:
    return {t["id"]: t for t in yaml.safe_load(open(CORPUS))["tasks"]}


def rosetta_context(intent: str) -> str:
    """Pull rosetta's live search result for an intent (the rosetta-augmented
    agent's view). Empty string if rosetta is unavailable."""
    from lib.rosetta_client import RosettaUnavailable, result_text, rosetta_session

    async def _go() -> str:
        async with rosetta_session() as s:
            res = await s.call_tool("routeros_search", {"query": intent})
            return result_text(res)

    try:
        txt = asyncio.run(_go())
    except Exception:
        return ""
    # keep the prompt bounded; the head of the result carries the page + path.
    return txt.strip()[:4000]


def _tok(text: str) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9]+", text.lower()) if len(w) > 2}


def skills_context(intent: str) -> str:
    """The skills-augmented agent's view: always-on frontmatter (the router) plus
    the single best-matching SKILL.md body (progressive disclosure)."""
    cfg = cb.load_config()
    skills = list(cb.iter_skills(cfg))
    roster = "\n".join(f"- {s['name']}: {s['description']}" for s in skills)
    q = _tok(intent)
    best, best_score = None, 0
    for s in skills:
        score = len(q & _tok(f"{s['name']} {s['description']}"))
        if score > best_score:
            best, best_score = s, score
    block = (
        "You have these RouterOS skills available (name: when-to-use):\n"
        f"{roster}\n"
    )
    if best and best_score >= 2:
        block += (
            f"\nThe most relevant skill body (<{best['name']}>):\n"
            f"<skill>\n{best['body'][:4000]}\n</skill>\n"
        )
    return block


def build_prompt(task: dict, approach: str) -> str:
    ver = task.get("version", "7.x")
    head = f"RouterOS {ver}. Task: {task['intent']}"
    if approach == "rosetta-context":
        ctx = rosetta_context(task["intent"])
        if ctx:
            head = (
                "You have the following RouterOS documentation search results:\n"
                f"<docs>\n{ctx}\n</docs>\n\n" + head
            )
    elif approach == "skills-context":
        head = skills_context(task["intent"]) + "\n" + head
    return f"{head}\n\n{OUTPUT_RULE}"


def parse_commands(text: str) -> list[str]:
    """Extract RouterOS command lines from a model's free-text answer."""
    text = re.sub(r"```[a-zA-Z]*", "", text).replace("```", "")
    cmds = []
    for line in text.splitlines():
        line = line.strip().lstrip("$").strip()
        if not line:
            continue
        # a command either starts at a menu path or has a verb token
        if line.startswith("/") or re.search(
            r"\b(add|set|remove|print|enable|disable|save|export)\b", line
        ):
            # drop leading numbering like "1. " or "- "
            line = re.sub(r"^(\d+[.)]\s*|[-*]\s*)", "", line)
            cmds.append(line)
    return cmds


def call_claude(prompt: str, model: str) -> dict:
    """One isolated, non-interactive `claude -p` generation. Returns a record."""
    with tempfile.TemporaryDirectory(prefix="ros-live-", dir="/tmp") as cwd:
        cmd = [
            "claude", "-p", prompt,
            "--model", model,
            "--setting-sources", "",
            "--strict-mcp-config",
            "--disable-slash-commands",
            "--output-format", "json",
        ]
        t0 = time.time()
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=180
        )
        dt = time.time() - t0
    rec = {"exit_code": proc.returncode, "wall_s": round(dt, 1)}
    try:
        j = json.loads(proc.stdout)
        rec["result"] = j.get("result", "")
        rec["num_turns"] = j.get("num_turns")
        rec["cost_usd"] = j.get("total_cost_usd")
        rec["is_error"] = j.get("is_error")
    except json.JSONDecodeError:
        rec["result"] = proc.stdout
        rec["stderr"] = proc.stderr[:500]
        rec["is_error"] = True
    return rec


def chr_validator():
    """Return a validate(cmd)->(ok,detail) callable, or None if no CHR."""
    try:
        from lib.chr import Chr, ChrUnavailable

        chr_ = Chr().start()
        return chr_
    except Exception as e:  # noqa: BLE001
        print(f"[live] CHR validator unavailable ({e}); skipping syntax validation")
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="build/print prompts without calling the model")
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS),
                    help="comma-separated model ids (mini-matrix)")
    ap.add_argument("--repeats", type=int,
                    default=int(os.environ.get("LIVE_REPEATS", "1")),
                    help="generations per cell (k); >1 gives a stability band")
    args = ap.parse_args()

    tasks = load_tasks()
    task_ids = os.environ.get("LIVE_TASKS")
    task_ids = task_ids.split(",") if task_ids else DEFAULT_TASKS
    models = os.environ.get("LIVE_MODELS", args.models).split(",")
    approaches = APPROACHES
    repeats = max(1, args.repeats)

    if args.dry_run:
        for tid in task_ids:
            for ap_name in approaches:
                p = build_prompt(tasks[tid], ap_name)
                print(f"\n===== {ap_name} / {tid} =====\n{p}")
        return

    DATA.mkdir(exist_ok=True)
    n_cells = len(models) * len(task_ids) * len(approaches) * repeats
    print(f"[live] matrix: {len(models)} models x {len(approaches)} conditions "
          f"x {len(task_ids)} tasks x {repeats} repeats = {n_cells} generations")

    chr_ = chr_validator()
    rows, records = [], []
    total_cost = 0.0
    # checkpoint per-run records to jsonl as we go, so a long/expensive run is
    # not lost if it crashes mid-matrix.
    jsonl_fh = open(DATA / "live_pilot.jsonl", "w")
    try:
        for model in models:
            print(f"\n--- model={model} ---")
            for tid in task_ids:
                task = tasks[tid]
                for ap_name in approaches:
                    prompt = build_prompt(task, ap_name)
                    phash = hashlib.sha256(prompt.encode()).hexdigest()[:12]
                    for rep in range(repeats):
                        rec = call_claude(prompt, model)
                        cmds = parse_commands(rec.get("result", ""))
                        label, sub = predict_label(task, cmds) if cmds else ("empty", {})
                        # syntax-validate each emitted command on CHR
                        validity = "n/a"
                        if chr_ is not None and cmds:
                            verdicts = [chr_.validate(c) for c in cmds]
                            validity = "ok" if all(v[0] for v in verdicts) else "error"
                        total_cost += rec.get("cost_usd") or 0.0
                        rows.append({
                            "approach": ap_name, "task": tid, "model": model,
                            "rep": rep, "label": label, "syntax_valid": validity,
                            "n_cmds": len(cmds), "n_gold": len(task["gold_commands"]),
                            "exit_code": rec["exit_code"], "cost_usd": rec.get("cost_usd"),
                            "prompt_hash": phash,
                        })
                        record = {
                            **rows[-1], "prompt": prompt, "raw_result": rec.get("result", ""),
                            "parsed_commands": cmds, "scorer_sub": sub,
                            "num_turns": rec.get("num_turns"), "wall_s": rec.get("wall_s"),
                        }
                        records.append(record)
                        jsonl_fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                        jsonl_fh.flush()
                        rtag = f" rep={rep}" if repeats > 1 else ""
                        print(f"  {ap_name:16} {tid:28}{rtag} -> {label:14} "
                              f"syntax={validity:5} cmds={len(cmds)} "
                              f"${rec.get('cost_usd') or 0:.3f}")
    finally:
        jsonl_fh.close()
        if chr_ is not None and getattr(chr_, "proc", None) is not None:
            chr_.stop()

    fields = ["approach", "task", "model", "rep", "label", "syntax_valid",
              "n_cmds", "n_gold", "exit_code", "cost_usd", "prompt_hash"]
    with open(DATA / "live_pilot.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    # per-cell aggregation (model x approach x task across repeats) -- the
    # stability band the single-shot pilot lacked. modal_label + agreement tells
    # whether a cell is stable or a coin-flip; perfect/syntax counts are k-of-N.
    from collections import Counter
    cell_keys = sorted({(r["model"], r["approach"], r["task"]) for r in rows})
    matrix_rows = []
    for model, ap_name, tid in cell_keys:
        sub = [r for r in rows if r["model"] == model
               and r["approach"] == ap_name and r["task"] == tid]
        labels = [r["label"] for r in sub]
        modal, modal_n = Counter(labels).most_common(1)[0]
        matrix_rows.append({
            "model": model, "approach": ap_name, "task": tid,
            "n_rep": len(sub),
            "n_perfect": sum(1 for r in sub if r["label"] == "perfect"),
            "n_syntax_ok": sum(1 for r in sub if r["syntax_valid"] == "ok"),
            "modal_label": modal,
            "agreement": round(modal_n / len(sub), 2),
            "labels": "|".join(labels),
        })
    with open(DATA / "live_matrix.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(matrix_rows[0].keys()))
        w.writeheader()
        w.writerows(matrix_rows)

    # summary -- per model x approach, stability-aware
    def rate(model, ap_name, pred):
        sub = [r for r in rows if r["model"] == model and r["approach"] == ap_name]
        good = sum(1 for r in sub if pred(r))
        return good, len(sub)

    print(f"\n[live] models={','.join(models)}  repeats={repeats}  "
          f"total_cost=${total_cost:.2f}")
    for model in models:
        print(f"  {model}")
        for ap_name in approaches:
            g, n = rate(model, ap_name, lambda r: r["label"] == "perfect")
            gv, _ = rate(model, ap_name, lambda r: r["syntax_valid"] == "ok")
            # cells that are unstable (modal agreement < 1.0) under this condition
            cells = [m for m in matrix_rows
                     if m["model"] == model and m["approach"] == ap_name]
            unstable = sum(1 for m in cells if m["agreement"] < 1.0)
            print(f"    {ap_name:16} perfect={g}/{n}  syntax_valid={gv}/{n}  "
                  f"unstable_cells={unstable}/{len(cells)}")
    print(f"  wrote {DATA/'live_pilot.csv'}, live_pilot.jsonl, live_matrix.csv")


if __name__ == "__main__":
    main()
