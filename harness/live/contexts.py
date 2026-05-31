"""Approach-specific prompt construction for live runs.

Each approach becomes a different prompt *prefix* over the same task. This makes
the comparison fair and reproducible: the only thing that varies between
``baseline`` and ``rosetta`` is whether real retrieved documentation is injected
as context. The model is asked for plain-text commands -- no live tool calls --
so the only knowledge difference is the injected text.

For the ``rosetta`` approach we call rosetta's *real* retrieval over MCP stdio
(``routeros_search`` + ``routeros_explain_command``) and inline the returned
text, capped to a token-ish budget. This mirrors "rosetta already retrieved the
relevant docs" rather than reimplementing retrieval.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from lib.rosetta_client import RosettaUnavailable, result_text, rosetta_session

INSTRUCTION = (
    "You are configuring MikroTik RouterOS {version}.\n"
    "Task: {intent}\n\n"
    "Respond with ONLY the RouterOS CLI command(s) needed, one per line, in the "
    "order they must run. No explanation, no markdown, no code fences. If the "
    "request is unsafe or would lock out access, respond with a single line "
    "starting with REFUSE: and a short reason instead of commands."
)

ROSETTA_PREAMBLE = (
    "Reference documentation retrieved for this task (authoritative for syntax "
    "and version):\n"
    "-----8<----- BEGIN DOCS -----8<-----\n{docs}\n"
    "-----8<----- END DOCS -----8<-----\n\n"
)


def base_instruction(task: dict) -> str:
    return INSTRUCTION.format(version=task.get("version", "7.x"),
                              intent=task["intent"])


async def _retrieve(task: dict, char_budget: int) -> str:
    async with rosetta_session() as s:
        chunks: list[str] = []
        search = await s.call_tool(
            "routeros_search", {"query": task["intent"], "limit": 4})
        chunks.append(result_text(search))
        # explain the first relevant_area path if present, to surface properties
        area = next((a for a in task.get("relevant_areas", []) if a.startswith("/")),
                    None)
        if area:
            try:
                ex = await s.call_tool(
                    "routeros_explain_command",
                    {"command": f"{area} add", "ros_version": task.get("version_exact", "7.22.1")},
                )
                chunks.append(result_text(ex))
            except Exception:
                pass
        text = "\n\n".join(c for c in chunks if c)
        return text[:char_budget]


def rosetta_context(task: dict, char_budget: int = 6000) -> tuple[str, int, str]:
    """Return (docs_text, chars, status). status in {ok, unavailable}."""
    try:
        docs = asyncio.run(_retrieve(task, char_budget))
        return docs, len(docs), "ok"
    except RosettaUnavailable as e:
        return "", 0, f"unavailable:{e}"
    except Exception as e:  # pragma: no cover - defensive
        return "", 0, f"error:{e}"


def build_prompt(task: dict, approach: str) -> tuple[str, dict]:
    """Return (prompt, meta). meta records retrieval provenance for auditing."""
    instr = base_instruction(task)
    meta = {"approach": approach, "retrieval_status": "n/a", "retrieval_chars": 0}
    if approach == "baseline":
        return instr, meta
    if approach == "rosetta":
        docs, n, status = rosetta_context(task)
        meta["retrieval_status"] = status
        meta["retrieval_chars"] = n
        if docs:
            return ROSETTA_PREAMBLE.format(docs=docs) + instr, meta
        return instr, meta  # degrade to baseline prompt if retrieval failed
    raise ValueError(f"approach {approach!r} not supported in live pilot")
