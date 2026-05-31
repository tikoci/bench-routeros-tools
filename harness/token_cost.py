"""Metric A -- Token / context cost, normalized so the comparison is honest.

Reported facets (never one flat table):
  A1 always-on discovery cost  -- what's resident before any task work.
  A2 per-task activation cost   -- a representative skill body / retrieved doc.
  A3 capability tier            -- knowledge vs execution (keeps it apples-to-apples).
  A4 marginal cost              -- the extra always-on tokens each added component buys.

Outputs:
  data/token_cost.csv          -- one row per approach (always-on breakdown + tier).
  data/token_cost_marginal.csv -- marginal always-on cost of adding each component.
  data/token_activation.csv    -- activation cost of skill bodies (per skill).
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import context_builders as cb
from lib.tokenizer import DEFAULT_ENCODING, count_tokens

DATA = Path(__file__).resolve().parents[1] / "data"


def main() -> None:
    cfg = cb.load_config()
    enc = DEFAULT_ENCODING

    # Per-source always-on token cost (computed once, reused).
    source_tokens = {
        "mcp_tools": count_tokens(cb.mcp_tools_text(cfg), enc),
        "rosetta_tools": count_tokens(cb.rosetta_tools_text(cfg), enc),
        "skills_frontmatter": count_tokens(cb.skills_frontmatter_text(cfg), enc),
    }

    # ---- A1 + A3: per-approach always-on cost -------------------------------
    rows = []
    for name, spec in cfg["approaches"].items():
        on = spec.get("always_on", [])
        breakdown = {k: source_tokens.get(k, 0) for k in on}
        rows.append(
            {
                "approach": name,
                "label": spec["label"],
                "tier": cfg["tiers"][name],
                "always_on_sources": "|".join(on) if on else "(none)",
                "mcp_tools_tokens": breakdown.get("mcp_tools", 0),
                "rosetta_tools_tokens": breakdown.get("rosetta_tools", 0),
                "skills_frontmatter_tokens": breakdown.get("skills_frontmatter", 0),
                "always_on_total_tokens": sum(breakdown.values()),
                "encoding": enc,
            }
        )

    DATA.mkdir(exist_ok=True)
    with open(DATA / "token_cost.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # ---- A4: marginal cost of adding each component -------------------------
    marginal = [
        ("baseline -> skills", "skills_frontmatter", source_tokens["skills_frontmatter"]),
        ("baseline -> rosetta", "rosetta_tools", source_tokens["rosetta_tools"]),
        ("baseline -> mcp", "mcp_tools", source_tokens["mcp_tools"]),
        ("rosetta -> rosetta+skills", "skills_frontmatter", source_tokens["skills_frontmatter"]),
        ("mcp -> mcp+rosetta+skills", "rosetta_tools+skills_frontmatter",
         source_tokens["rosetta_tools"] + source_tokens["skills_frontmatter"]),
    ]
    with open(DATA / "token_cost_marginal.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["transition", "component_added", "marginal_always_on_tokens", "encoding"])
        for trans, comp, tok in marginal:
            w.writerow([trans, comp, tok, enc])

    # ---- A2: activation cost (skill bodies) ---------------------------------
    bodies = cb.skill_bodies(cfg)
    with open(DATA / "token_activation.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["source", "item", "activation_tokens", "encoding"])
        for sname, body in sorted(bodies.items()):
            w.writerow(["skill_body", sname, count_tokens(body, enc), enc])

    # ---- console summary ----------------------------------------------------
    print(f"[token_cost] encoding={enc}")
    print(f"  always-on per source: "
          f"mcp_tools={source_tokens['mcp_tools']}, "
          f"rosetta_tools={source_tokens['rosetta_tools']}, "
          f"skills_frontmatter={source_tokens['skills_frontmatter']}")
    for r in rows:
        print(f"  {r['approach']:<22} tier={r['tier']:<9} "
              f"always_on={r['always_on_total_tokens']:>7} tok")
    print(f"  wrote {DATA/'token_cost.csv'}, token_cost_marginal.csv, token_activation.csv")


if __name__ == "__main__":
    main()
