"""Refresh external MCP tool-schema snapshots.

The benchmark is intentionally standalone, so committed tool-schema snapshots are
the default input. This script regenerates those snapshots when the external
projects are available:

  - mikrotik-mcp: set MIKROTIK_MCP_PATH=/path/to/mikrotik-mcp, or install it in
    the benchmark venv.
  - rosetta: set ROSETTA_BIN=/path/to/rosetta/bin/rosetta.js, or keep the
    default ~/GitHub/rosetta/bin/rosetta.js.

Outputs:
  data/mcp_tools.json
  data/rosetta_tools.json
  data/skills.json
  data/provenance.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.rosetta_client import RosettaUnavailable, rosetta_session

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def git_rev(path: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


def external_path(env_name: str, default: str | None = None) -> Path | None:
    raw = os.environ.get(env_name, default or "")
    return Path(os.path.expanduser(raw)).resolve() if raw else None


async def refresh_mcp_tools() -> dict:
    mcp_path = external_path("MIKROTIK_MCP_PATH")
    if mcp_path:
        # Support both src-layout and flat-layout checkouts.
        sys.path.insert(0, str(mcp_path / "src"))
        sys.path.insert(0, str(mcp_path))

    try:
        from mcp_mikrotik.app import mcp
    except Exception as e:
        hint = "set MIKROTIK_MCP_PATH=/path/to/mikrotik-mcp or install mcp_mikrotik"
        raise RuntimeError(f"cannot import mcp_mikrotik.app ({e}); {hint}") from e

    tools = await mcp.list_tools()
    out = DATA / "mcp_tools.json"
    with open(out, "w") as fh:
        json.dump([t.model_dump() for t in tools], fh, indent=2, default=str)
        fh.write("\n")
    print(f"[refresh] mcp tools: {len(tools)} -> {out}")
    return {
        "tool_count": len(tools),
        "source_path": str(mcp_path) if mcp_path else "python import path",
        "source_revision": git_rev(mcp_path) if mcp_path else None,
    }


async def refresh_rosetta_tools() -> dict:
    async with rosetta_session() as session:
        tools = await session.list_tools()
    out = DATA / "rosetta_tools.json"
    with open(out, "w") as fh:
        json.dump([t.model_dump() for t in tools.tools], fh, indent=2, default=str)
        fh.write("\n")
    rosetta_bin = external_path("ROSETTA_BIN", "~/GitHub/rosetta/bin/rosetta.js")
    rosetta_root = rosetta_bin.parents[1] if rosetta_bin and len(rosetta_bin.parents) > 1 else None
    print(f"[refresh] rosetta tools: {len(tools.tools)} -> {out}")
    return {
        "tool_count": len(tools.tools),
        "source_path": str(rosetta_bin),
        "source_revision": git_rev(rosetta_root) if rosetta_root else None,
    }


def refresh_skills() -> dict:
    skills_dir = external_path("ROUTEROS_SKILLS_DIR", "~/GitHub/routeros-skills")
    if not skills_dir or not skills_dir.exists():
        raise RuntimeError(f"routeros-skills not found at {skills_dir} (set ROUTEROS_SKILLS_DIR)")

    import yaml

    items = []
    for path in sorted(skills_dir.glob("routeros-*/SKILL.md")):
        text = path.read_text()
        name = path.parent.name
        frontmatter = ""
        body = text
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                frontmatter = "---" + parts[1] + "---\n"
                body = parts[2].lstrip("\n")
                meta = yaml.safe_load(parts[1]) or {}
                name = meta.get("name", name)
        items.append({
            "name": name,
            "description": meta.get("description", ""),
            "path": str(path),
            "frontmatter": frontmatter,
            "body": body,
        })

    out = DATA / "skills.json"
    with open(out, "w") as fh:
        json.dump(items, fh, indent=2)
        fh.write("\n")
    print(f"[refresh] routeros skills: {len(items)} -> {out}")
    return {
        "skill_count": len(items),
        "source_path": str(skills_dir),
        "source_revision": git_rev(skills_dir),
    }


def write_provenance(meta: dict) -> None:
    path = DATA / "provenance.json"
    existing = {}
    if path.exists():
        try:
            existing = json.load(open(path))
        except json.JSONDecodeError:
            existing = {}
    existing.update(meta)
    existing["captured_at"] = datetime.now(timezone.utc).isoformat()
    with open(path, "w") as fh:
        json.dump(existing, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"[refresh] provenance -> {path}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mcp-only", action="store_true", help="refresh only mikrotik-mcp tools")
    parser.add_argument("--rosetta-only", action="store_true", help="refresh only rosetta tools")
    args = parser.parse_args()

    DATA.mkdir(exist_ok=True)
    meta: dict = {}
    if not args.rosetta_only:
        meta["mikrotik_mcp"] = await refresh_mcp_tools()
    if not args.mcp_only:
        try:
            meta["rosetta"] = await refresh_rosetta_tools()
        except RosettaUnavailable as e:
            raise RuntimeError(f"cannot refresh rosetta tools: {e}") from e
    meta["routeros_skills"] = refresh_skills()
    write_provenance(meta)


if __name__ == "__main__":
    asyncio.run(main())
