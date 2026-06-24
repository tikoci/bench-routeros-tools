"""Deterministic task-success proxies that need no model API.

  Proxy B -- always-on routing signal: does each approach's always-on context
             expose an obvious next action for the task?
               mcp    : a tool whose name lexically matches the gold path/verb
               skills : a skill whose frontmatter matches the task domain
               rosetta: retrieval is always reachable (a search tool exists) -> yes
  Proxy F -- context-budget simulation: under a fixed budget, what does each
             approach still afford after one task interaction (always-on +
             one activation: a skill body / a retrieved doc / a tool result)?

Proxy A/D (retrieval covers gold) live in retrieval_eval.py; Proxy E (scorer vs
negative fixtures) lives in run_agent.py. This module writes data/proxy_*.csv.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

from lib import context_builders as cb
from lib.tokenizer import DEFAULT_ENCODING, count_tokens

BENCH = Path(__file__).resolve().parents[1]
DATA = BENCH / "data"
REPO = BENCH
CORPUS = BENCH / "tasks" / "corpus.yaml"

STOP = {"the", "a", "an", "to", "on", "of", "and", "or", "with", "for", "set",
        "add", "all", "show", "list", "create", "make", "name", "named"}


def toks(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", text.lower()) if t and t not in STOP and len(t) > 1}


def gold_path_tokens(task: dict) -> set[str]:
    # removed_capability tasks have no satisfiable gold -- fall back to the v7
    # alternative, else the first relevant_area, so the path tokens are still real.
    golds = task["gold_commands"] or task.get("acceptable_variants") or task.get("relevant_areas") or [""]
    path = golds[0].split()[0] if golds[0] else ""
    return {t for t in re.split(r"[/\s]+", path.lower()) if t and len(t) > 1}


def proxy_b(cfg, tasks) -> list[dict]:
    mcp_tools = json.load(open(REPO / cfg["sources"]["mcp_tools"]))
    tool_tok = [(t["name"], toks(t["name"] + " " + (t.get("description") or ""))) for t in mcp_tools]
    skills = list(cb.iter_skills(cfg))
    skill_tok = [(s["name"], toks(s["description"])) for s in skills]

    rows = []
    for task in tasks:
        gtok = gold_path_tokens(task) | {task["domain"]}
        qtok = toks(task["intent"]) | gtok

        mcp_hit = any(len(gtok & tt) >= 2 for _, tt in tool_tok)
        skill_hit = any(len(qtok & st) >= 2 for _, st in skill_tok)
        # rosetta: a unified search tool is always present -> retrieval reachable
        rosetta_hit = True

        rows.append({
            "task": task["id"],
            "mcp_tool_signal": int(mcp_hit),
            "skill_frontmatter_signal": int(skill_hit),
            "rosetta_retrieval_reachable": int(rosetta_hit),
        })
    return rows


def proxy_f(cfg) -> list[dict]:
    """What fits under fixed context budgets, per approach (always-on + 1 activation)."""
    enc = DEFAULT_ENCODING
    src = {
        "mcp_tools": count_tokens(cb.mcp_tools_text(cfg), enc),
        "rosetta_tools": count_tokens(cb.rosetta_tools_text(cfg), enc),
        "skills_frontmatter": count_tokens(cb.skills_frontmatter_text(cfg), enc),
    }
    # representative activation costs
    bodies = cb.skill_bodies(cfg)
    avg_skill_body = round(sum(count_tokens(b, enc) for b in bodies.values()) / len(bodies))
    retrieved_doc = 1200  # typical rosetta page slice (tokens); documented estimate
    tool_result = 400     # typical mcp tool JSON result

    activation = {
        "skills_frontmatter": ("skill_body", avg_skill_body),
        "rosetta_tools": ("retrieved_doc", retrieved_doc),
        "mcp_tools": ("tool_result", tool_result),
    }

    budgets = [8000, 16000, 32000]
    rows = []
    for ap, spec in cfg["approaches"].items():
        on = spec.get("always_on", [])
        always = sum(src.get(k, 0) for k in on)
        act = sum(activation[k][1] for k in on if k in activation)
        used = always + act
        row = {
            "approach": ap,
            "always_on_tokens": always,
            "one_activation_tokens": act,
            "after_one_task_tokens": used,
        }
        for b in budgets:
            row[f"fits_{b}"] = int(used <= b)
            row[f"headroom_{b}"] = b - used
        rows.append(row)
    return rows, avg_skill_body


def main() -> None:
    cfg = cb.load_config()
    tasks = yaml.safe_load(open(CORPUS))["tasks"]
    DATA.mkdir(exist_ok=True)

    b_rows = proxy_b(cfg, tasks)
    with open(DATA / "proxy_routing_signal.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(b_rows[0].keys()))
        w.writeheader()
        w.writerows(b_rows)

    f_rows, avg_body = proxy_f(cfg)
    with open(DATA / "proxy_context_budget.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(f_rows[0].keys()))
        w.writeheader()
        w.writerows(f_rows)

    n = len(b_rows)
    mcp_sig = sum(r["mcp_tool_signal"] for r in b_rows)
    sk_sig = sum(r["skill_frontmatter_signal"] for r in b_rows)
    print(f"[proxies] routing signal over {n} tasks:")
    print(f"  mcp tool name/desc points at a relevant tool: {mcp_sig}/{n} ({100*mcp_sig/n:.0f}%)")
    print(f"  skill frontmatter points at a relevant skill: {sk_sig}/{n} ({100*sk_sig/n:.0f}%)")
    print(f"  rosetta retrieval always reachable: {n}/{n} (100%)")
    print(f"[proxies] context-budget (always-on + 1 activation), avg skill body={avg_body} tok:")
    for r in f_rows:
        print(f"  {r['approach']:<22} after-task={r['after_one_task_tokens']:>6} tok "
              f"fits8k={r['fits_8000']} fits16k={r['fits_16000']} fits32k={r['fits_32000']}")
    print(f"  wrote {DATA/'proxy_routing_signal.csv'}, {DATA/'proxy_context_budget.csv'}")


if __name__ == "__main__":
    main()
