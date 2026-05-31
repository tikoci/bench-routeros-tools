"""Metric C + proxies A/D -- rosetta retrieval quality on task-intent queries.

For each task we run rosetta's real `routeros_search` with the natural-language
intent (NOT a doc title) and ask: does the result surface the gold command's
path? This is the deterministic proxy closest to "would retrieval help the agent
build the right command."

  hit@k   : gold command path appears in the top-k search result text
  MRR     : 1/rank of the first result that surfaces the path
  proxy D : does `routeros_explain_command` on the gold command return a
            recognized path (reconstructability / validation signal)

Degrades gracefully: if rosetta/Bun is unavailable, writes a stub row set with
status=skipped so the suite still completes.

Output: data/retrieval.csv
"""
from __future__ import annotations

import asyncio
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

from lib.rosetta_client import RosettaUnavailable, result_text, rosetta_session

DATA = Path(__file__).resolve().parents[1] / "data"
CORPUS = Path(__file__).resolve().parents[1] / "tasks" / "corpus.yaml"
TOPK = 5


def gold_path(task: dict) -> str:
    cmd = task["gold_commands"][0].strip()
    path = cmd.split()[0]
    # normalize: keep the menu path, drop a trailing verb like add/set/print
    segs = [s for s in path.split("/") if s]
    if segs and segs[-1] in {"add", "set", "print", "remove", "save", "disable", "enable"}:
        segs = segs[:-1]
    return "/" + "/".join(segs)


def path_hit(text: str, path: str) -> bool:
    segs = [s for s in path.split("/") if s]
    if not segs:
        return False
    text_l = text.lower()
    # hit if the full slash path OR its last two segments both appear
    if path.lower() in text_l:
        return True
    tail = segs[-2:]
    return all(re.search(rf"\b{re.escape(s)}\b", text_l) for s in tail)


async def run() -> list[dict]:
    tasks = yaml.safe_load(open(CORPUS))["tasks"]
    rows = []
    async with rosetta_session() as s:
        for task in tasks:
            gp = gold_path(task)
            res = await s.call_tool("routeros_search", {"query": task["intent"], "limit": TOPK})
            text = result_text(res)
            # Approximate per-rank hit by splitting the result into blocks.
            blocks = re.split(r"\n(?=\d+\.|#{1,3}\s|---)", text) or [text]
            rank = 0
            for i, b in enumerate(blocks[:TOPK], start=1):
                if path_hit(b, gp):
                    rank = i
                    break
            hit_any = path_hit(text, gp)

            # proxy D: explain the gold command
            recon = 0
            try:
                ex = await s.call_tool(
                    "routeros_explain_command",
                    {"command": task["gold_commands"][0], "ros_version": "7.22.1"},
                )
                extext = result_text(ex)
                recon = int(path_hit(extext, gp))
            except Exception:
                recon = 0

            rows.append(
                {
                    "task": task["id"],
                    "domain": task["domain"],
                    "gold_path": gp,
                    "hit_at_1": int(rank == 1),
                    "hit_at_3": int(1 <= rank <= 3),
                    "hit_at_5": int(hit_any),
                    "first_rank": rank,
                    "mrr": round(1.0 / rank, 3) if rank else 0.0,
                    "explain_reconstructs": recon,
                    "status": "ok",
                }
            )
    return rows


def write(rows: list[dict]) -> None:
    DATA.mkdir(exist_ok=True)
    fields = [
        "task", "domain", "gold_path", "hit_at_1", "hit_at_3", "hit_at_5",
        "first_rank", "mrr", "explain_reconstructs", "status",
    ]
    with open(DATA / "retrieval.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    try:
        rows = asyncio.run(run())
    except RosettaUnavailable as e:
        print(f"[retrieval] SKIPPED (rosetta unavailable: {e})")
        tasks = yaml.safe_load(open(CORPUS))["tasks"]
        rows = [
            {"task": t["id"], "domain": t["domain"], "gold_path": gold_path(t),
             "hit_at_1": "", "hit_at_3": "", "hit_at_5": "", "first_rank": "",
             "mrr": "", "explain_reconstructs": "", "status": "skipped"}
            for t in tasks
        ]
        write(rows)
        return

    write(rows)
    n = len(rows)
    h1 = sum(r["hit_at_1"] for r in rows)
    h3 = sum(r["hit_at_3"] for r in rows)
    h5 = sum(r["hit_at_5"] for r in rows)
    mrr = sum(r["mrr"] for r in rows) / n
    recon = sum(r["explain_reconstructs"] for r in rows)
    print(f"[retrieval] tasks={n} (rosetta routeros_search, top-{TOPK})")
    print(f"  hit@1={h1}/{n} ({100*h1/n:.0f}%)  hit@3={h3}/{n} ({100*h3/n:.0f}%)  "
          f"hit@5={h5}/{n} ({100*h5/n:.0f}%)  MRR={mrr:.3f}")
    print(f"  explain reconstructs gold path: {recon}/{n} ({100*recon/n:.0f}%)")
    print(f"  wrote {DATA/'retrieval.csv'}")


if __name__ == "__main__":
    main()
