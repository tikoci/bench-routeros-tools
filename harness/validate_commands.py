"""Metric D -- command syntax validity (corpus + scorer-oracle validation).

Runs every gold command (expect: ok) and every decoy/forbidden command
(expect: error) through the CHR /console/inspect validator. Falls back to the
static-schema oracle (rosetta explain) when no CHR is available.

IMPORTANT framing: this validates that (a) the corpus gold commands are real
RouterOS 7.22.1 syntax and (b) the validator/oracle can tell good from bad. It
is NOT a measure of any approach's effectiveness -- it validates the scoring
infrastructure the live-agent harness will later depend on.

Output: data/command_validity.csv
"""
from __future__ import annotations

import asyncio
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

from lib.chr import Chr, ChrUnavailable

BENCH = Path(__file__).resolve().parents[1]
DATA = BENCH / "data"
CORPUS = BENCH / "tasks" / "corpus.yaml"
FIXTURES = BENCH / "fixtures" / "candidates" / "scorer_fixtures.yaml"

# decoy labels the /console/inspect syntax check can catch (path + arg-name).
# NOTE: missing_arg, wrong_target, incomplete_seq and unsafe are SEMANTIC errors
# -- the command is still valid RouterOS syntax -- so they are detected by the
# scorer (gold comparison), not by the syntax oracle. Keeping them out here is
# deliberate, not a gap.
SYNTAX_INVALID_LABELS = {"wrong_path", "hallucinated"}


def collect_cases() -> list[dict]:
    corpus = yaml.safe_load(open(CORPUS))["tasks"]
    cases = []
    for t in corpus:
        for cmd in t["gold_commands"]:
            cases.append({"source": "gold", "task": t["id"], "command": cmd, "expected": "ok"})
        for cmd in t.get("forbidden_commands", []) or []:
            # forbidden = unsafe/wrong intent; usually still valid SYNTAX, so we
            # only record it -- semantic wrongness is scored elsewhere.
            cases.append({"source": "forbidden", "task": t["id"], "command": cmd, "expected": "n/a"})
    fixtures = yaml.safe_load(open(FIXTURES))["fixtures"]
    for f in fixtures:
        label = f["expected_label"]
        exp = "error" if label in SYNTAX_INVALID_LABELS else "ok"
        for cmd in f["candidate"]:
            cases.append({"source": f"fixture:{label}", "task": f["task"],
                          "command": cmd, "expected": exp})
    return cases


# --------------------------------------------------------------------------- #
# Static fallback oracle (rosetta explain)
# --------------------------------------------------------------------------- #
async def static_validate(cases: list[dict]) -> None:
    from lib.rosetta_client import RosettaUnavailable, result_text, rosetta_session

    async with rosetta_session() as s:
        for c in cases:
            try:
                res = await s.call_tool(
                    "routeros_explain_command",
                    {"command": c["command"], "ros_version": "7.22.1"},
                )
                txt = result_text(res).lower()
                # rosetta flags unknown paths/props in prose; treat explicit
                # "unknown"/"not found"/"no match" as invalid.
                invalid = any(k in txt for k in ("unknown", "not found", "no match",
                                                 "not recognized", "could not"))
                c["actual"] = "error" if invalid else "ok"
            except Exception as e:
                c["actual"] = "error?"
                c["detail"] = str(e)[:80]
            c["method"] = "static:rosetta"
            c.setdefault("detail", "")


def chr_validate(cases: list[dict]) -> bool:
    try:
        chr_ = Chr().start()
    except ChrUnavailable as e:
        print(f"[validate] CHR unavailable ({e}); using static fallback")
        return False
    try:
        for c in cases:
            valid, detail = chr_.validate(c["command"])
            c["actual"] = "ok" if valid else "error"
            c["method"] = "chr:inspect"
            c["detail"] = detail
    finally:
        # leave a pre-existing externally-managed VM running; only stop if we own it
        if chr_.proc is not None:
            chr_.stop()
    return True


def main() -> None:
    cases = collect_cases()
    used_chr = chr_validate(cases)
    if not used_chr:
        try:
            asyncio.run(static_validate(cases))
        except Exception as e:
            print(f"[validate] static fallback also unavailable: {e}")
            for c in cases:
                c.setdefault("actual", "skipped")
                c.setdefault("method", "none")
                c.setdefault("detail", "")

    DATA.mkdir(exist_ok=True)
    fields = ["source", "task", "command", "expected", "actual", "method", "detail"]
    with open(DATA / "command_validity.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for c in cases:
            c.setdefault("detail", "")
            w.writerows([c])

    gold = [c for c in cases if c["source"] == "gold"]
    gold_ok = sum(1 for c in gold if c.get("actual") == "ok")
    fix = [c for c in cases if c["source"].startswith("fixture:") and c["expected"] in ("ok", "error")]
    fix_correct = sum(1 for c in fix if c.get("actual") == c["expected"])
    method = cases[0].get("method", "none") if cases else "none"
    print(f"[validate] method={method}")
    print(f"  gold commands valid: {gold_ok}/{len(gold)} "
          f"({100*gold_ok/max(len(gold),1):.0f}%) -- corpus sanity")
    print(f"  scorer fixtures classified correctly: {fix_correct}/{len(fix)} "
          f"-- oracle distinguishes good/bad")
    print(f"  wrote {DATA/'command_validity.csv'}")


if __name__ == "__main__":
    main()
