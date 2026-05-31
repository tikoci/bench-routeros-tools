"""Minimal MCP stdio client helpers for talking to rosetta from Python.

rosetta is a Bun MCP server; we drive it over stdio with the official mcp client
so we exercise its *real* retrieval (FTS5/BM25), not a reimplementation.

Falls back cleanly: callers should catch RosettaUnavailable and degrade.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager


class RosettaUnavailable(RuntimeError):
    pass


ROSETTA_BIN = os.path.expanduser(os.environ.get("ROSETTA_BIN", "~/GitHub/rosetta/bin/rosetta.js"))


@asynccontextmanager
async def rosetta_session():
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except Exception as e:  # pragma: no cover
        raise RosettaUnavailable(f"mcp client import failed: {e}")

    if not os.path.exists(ROSETTA_BIN):
        raise RosettaUnavailable(f"rosetta not found at {ROSETTA_BIN} (set ROSETTA_BIN)")

    params = StdioServerParameters(command="bun", args=[ROSETTA_BIN], env=os.environ.copy())
    try:
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                yield s
    except Exception as e:
        raise RosettaUnavailable(str(e))


def result_text(call_result) -> str:
    """Flatten an MCP tool call result into searchable text."""
    parts = []
    for block in getattr(call_result, "content", []) or []:
        t = getattr(block, "text", None)
        if t:
            parts.append(t)
    return "\n".join(parts)
