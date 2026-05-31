"""Metric G -- tool-selection ambiguity across mikrotik-mcp's 166 tools.

A large executable tool surface fails not only on token cost but on *selection*:
with 166 similarly-named tools, can the model pick the right one? This is a
lexical proxy (token overlap), made explicit. For each task we measure:

  candidate_tools   tools whose lexical match score >= 50% of the top score
  top_tool          best-matching tool name
  correct_in_top3   whether a tool matching the gold command's path+verb is top-3
  ambiguity         candidate_tools count (higher = harder to disambiguate)
  destructive_near  destructive/write tools among the top-5 (unsafe proximity)

Only the `mcp` and `mcp+rosetta+skills` configs expose this surface; the
knowledge-only configs have no tool-selection burden (reported as n/a).

Output: data/tool_ambiguity.csv
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import context_builders as cb

DATA = Path(__file__).resolve().parents[1] / "data"
REPO = Path(__file__).resolve().parents[1]

STOP = {
    "the", "a", "an", "to", "on", "of", "and", "or", "with", "for", "in", "at",
    "by", "set", "add", "all", "show", "list", "create", "make", "give", "named",
    "name", "device", "router", "router's", "using", "use", "this", "that",
}


def tokenize(text: str) -> set[str]:
    toks = re.split(r"[^a-z0-9]+", text.lower())
    return {t for t in toks if t and t not in STOP and len(t) > 1}


def gold_keywords(task: dict) -> set[str]:
    """Keywords that identify the *correct* tool: command path tokens + verb."""
    kw: set[str] = set()
    for cmd in task["gold_commands"]:
        head = cmd.strip().split()
        path = head[0] if head else ""
        kw |= {t for t in re.split(r"[/\s]+", path.lower()) if t}
        for verb in ("add", "set", "remove", "print", "disable", "enable", "save", "export"):
            if f" {verb}" in f" {cmd} " or path.endswith(verb):
                kw.add(verb)
    return {t for t in kw if t and len(t) > 1}


def main() -> None:
    cfg = cb.load_config()
    tools = json.load(open(REPO / cfg["sources"]["mcp_tools"]))
    tool_index = []
    for t in tools:
        name = t.get("name", "")
        desc = t.get("description", "") or ""
        ann = (t.get("annotations") or {})
        risk = ""
        # annotations carry destructiveHint / readOnlyHint
        if ann.get("destructiveHint"):
            risk = "destructive"
        elif ann.get("readOnlyHint"):
            risk = "read"
        else:
            risk = "write"
        tool_index.append(
            {"name": name, "tokens": tokenize(name + " " + desc), "risk": risk}
        )

    tasks = yaml_tasks()
    rows = []
    for task in tasks:
        q = tokenize(task["intent"]) | set(
            tok for area in task["relevant_areas"] for tok in tokenize(area)
        ) | {task["domain"]}
        scored = []
        for ti in tool_index:
            overlap = len(q & ti["tokens"])
            if overlap:
                scored.append((overlap, ti))
        scored.sort(key=lambda x: x[0], reverse=True)

        top_score = scored[0][0] if scored else 0
        candidates = [s for s in scored if top_score and s[0] >= 0.5 * top_score]
        top5 = scored[:5]

        gkw = gold_keywords(task)
        correct_in_top3 = any(
            len(gkw & s[1]["tokens"]) >= max(2, len(gkw) // 2) for s in scored[:3]
        )
        destructive_near = sum(1 for _, ti in top5 if ti["risk"] == "destructive")

        rows.append(
            {
                "task": task["id"],
                "domain": task["domain"],
                "matched_tools": len(scored),
                "candidate_tools": len(candidates),
                "top_tool": scored[0][1]["name"] if scored else "(none)",
                "top_score": top_score,
                "correct_in_top3": int(correct_in_top3),
                "destructive_in_top5": destructive_near,
            }
        )

    DATA.mkdir(exist_ok=True)
    with open(DATA / "tool_ambiguity.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    n = len(rows)
    avg_cand = sum(r["candidate_tools"] for r in rows) / n
    avg_match = sum(r["matched_tools"] for r in rows) / n
    hit = sum(r["correct_in_top3"] for r in rows)
    print(f"[tool_ambiguity] tasks={n} over 166 mcp tools")
    print(f"  avg tools lexically matching a task: {avg_match:.1f}")
    print(f"  avg close-call candidates (>=50% top): {avg_cand:.1f}")
    print(f"  correct tool in top-3 (lexical proxy): {hit}/{n} ({100*hit/n:.0f}%)")
    print(f"  wrote {DATA/'tool_ambiguity.csv'}")


def yaml_tasks():
    import yaml

    d = yaml.safe_load(open(Path(__file__).resolve().parents[1] / "tasks" / "corpus.yaml"))
    return d["tasks"]


if __name__ == "__main__":
    main()
