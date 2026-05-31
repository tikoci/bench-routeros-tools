"""Build the context each approach injects, so it can be tokenized fairly.

The unit of comparison is *what the model actually sees*:

  - MCP tools  -> the JSON the MCP client serializes into the tool list
                  (name + description + inputSchema + annotations) per tool.
  - skills     -> always-on = YAML frontmatter description per skill;
                  activated = the full SKILL.md body once invoked.
  - rosetta    -> always-on = its 14 tool schemas; activated = retrieved docs
                  (measured live during retrieval_eval, not here).

Everything is loaded from committed artifacts under data/ so the token
numbers are reproducible without a live MCP server or Bun.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_yaml(p: Path) -> dict:
    with open(p) as fh:
        return yaml.safe_load(fh)


def load_config() -> dict:
    return _load_yaml(REPO_ROOT / "approaches.yaml")


def _expand(p: str) -> Path:
    return Path(os.path.expanduser(p))


# --------------------------------------------------------------------------- #
# Tool-schema serialization (MCP wire shape the model is shown)
# --------------------------------------------------------------------------- #
def _serialize_tool(tool: dict) -> str:
    """Serialize one MCP tool the way a client presents it to the model.

    Includes the fields that occupy context: name, description, inputSchema,
    and annotations (risk hints). Output/meta/icons are excluded — clients do
    not put those in the model-facing tool list.
    """
    payload = {
        "name": tool.get("name"),
        "description": tool.get("description"),
        "inputSchema": tool.get("inputSchema"),
    }
    ann = tool.get("annotations")
    if ann:
        payload["annotations"] = ann
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _load_tools(artifact: str) -> list[dict]:
    path = REPO_ROOT / artifact
    with open(path) as fh:
        return json.load(fh)


def mcp_tools_text(cfg: dict) -> str:
    tools = _load_tools(cfg["sources"]["mcp_tools"])
    return "\n".join(_serialize_tool(t) for t in tools)


def rosetta_tools_text(cfg: dict) -> str:
    tools = _load_tools(cfg["sources"]["rosetta_tools"])
    return "\n".join(_serialize_tool(t) for t in tools)


# --------------------------------------------------------------------------- #
# Skills
# --------------------------------------------------------------------------- #
def _split_frontmatter(md: str) -> tuple[str, str]:
    """Return (frontmatter_yaml_text, body) for a SKILL.md file."""
    if md.startswith("---"):
        parts = md.split("---", 2)
        if len(parts) >= 3:
            return parts[1].strip(), parts[2].strip()
    return "", md.strip()


def iter_skills(cfg: dict):
    snapshot = cfg["sources"].get("skills_snapshot")
    if snapshot:
        p = _expand(snapshot)
        if p.exists():
            for item in json.load(open(p)):
                meta = {}
                fm = item.get("frontmatter", "")
                if fm.startswith("---"):
                    fm = fm.strip("-\n")
                try:
                    meta = yaml.safe_load(fm) or {}
                except yaml.YAMLError:
                    meta = {}
                yield {
                    "name": item.get("name") or meta.get("name"),
                    "description": item.get("description") or meta.get("description", ""),
                    "frontmatter": item.get("frontmatter", ""),
                    "body": item.get("body", ""),
                }
            return

    skills_dir = _expand(os.environ.get("ROUTEROS_SKILLS_DIR", cfg["sources"]["skills_dir"]))
    for sub in sorted(skills_dir.glob("routeros-*")):
        skill_md = sub / "SKILL.md"
        if not skill_md.exists():
            continue
        fm, body = _split_frontmatter(skill_md.read_text())
        meta = {}
        try:
            meta = yaml.safe_load(fm) or {}
        except yaml.YAMLError:
            meta = {}
        yield {
            "name": meta.get("name", sub.name),
            "description": meta.get("description", ""),
            "frontmatter": fm,
            "body": body,
        }


def skills_frontmatter_text(cfg: dict) -> str:
    """Always-on skill cost: what a skill-aware client keeps resident.

    Modeled as `name: description` per skill (the discovery surface), which is
    all that stays in context until a skill is invoked.
    """
    return "\n".join(f"{s['name']}: {s['description']}" for s in iter_skills(cfg))


def skill_bodies(cfg: dict) -> dict[str, str]:
    """Activated cost source: full body per skill, keyed by name."""
    return {s["name"]: s["body"] for s in iter_skills(cfg)}


# --------------------------------------------------------------------------- #
# Always-on context assembly per approach
# --------------------------------------------------------------------------- #
_SOURCE_FUNCS = {
    "mcp_tools": mcp_tools_text,
    "rosetta_tools": rosetta_tools_text,
    "skills_frontmatter": skills_frontmatter_text,
}


def always_on_text(cfg: dict, approach: str) -> dict[str, str]:
    """Return {source_key: text} for an approach's always-on context."""
    spec = cfg["approaches"][approach]
    out = {}
    for key in spec.get("always_on", []):
        fn = _SOURCE_FUNCS.get(key)
        out[key] = fn(cfg) if fn else ""
    return out
