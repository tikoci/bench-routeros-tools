"""Live-agent harness (scaffold) + capability matrix.

Today there is no model API wired in, so this runs in RECORD/REPLAY mode: it
feeds canned candidate transcripts (the scorer fixtures, treated as if a model
emitted them) through the deterministic scorer and reports per-label accuracy.
This proves the scoring path end-to-end. A real backend later only needs to
implement `produce_candidate(task, approach) -> list[str]`.

Also emits the capability matrix (metric B/E/F) -- a granular, honest map of what
each approach can actually do, which is the qualitative backbone of the report.

Outputs:
  data/agent_replay.csv       per-fixture predicted vs expected label
  data/capability_matrix.csv  approach x capability grid
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

from lib.scorer import predict_label

BENCH = Path(__file__).resolve().parents[1]
DATA = BENCH / "data"
CORPUS = BENCH / "tasks" / "corpus.yaml"
FIXTURES = BENCH / "fixtures" / "candidates" / "scorer_fixtures.yaml"


# --------------------------------------------------------------------------- #
# Capability matrix -- granular per critique (read/validate/dry-run/write/...)
# --------------------------------------------------------------------------- #
# values: yes | no | partial
CAPABILITIES = [
    "discover_commands",   # find the right path/property
    "explain_semantics",   # describe what a command does
    "validate_before_run", # check a command is real before executing
    "read_live_state",     # read current device config
    "dry_run",             # preview without applying
    "write_config",        # apply a change
    "destructive_write",   # delete/replace config
    "post_change_verify",  # confirm result on device
    "version_aware",       # knows 7.x version differences
]

MATRIX = {
    "baseline": {
        "discover_commands": "partial", "explain_semantics": "partial",
        "validate_before_run": "no", "read_live_state": "no", "dry_run": "no",
        "write_config": "no", "destructive_write": "no", "post_change_verify": "no",
        "version_aware": "no",
    },
    "skills": {
        "discover_commands": "partial", "explain_semantics": "yes",
        "validate_before_run": "no", "read_live_state": "no", "dry_run": "no",
        "write_config": "no", "destructive_write": "no", "post_change_verify": "no",
        "version_aware": "partial",
    },
    "rosetta": {
        "discover_commands": "yes", "explain_semantics": "yes",
        "validate_before_run": "partial", "read_live_state": "no", "dry_run": "no",
        "write_config": "no", "destructive_write": "no", "post_change_verify": "no",
        "version_aware": "yes",
    },
    "skills+rosetta": {
        "discover_commands": "yes", "explain_semantics": "yes",
        "validate_before_run": "partial", "read_live_state": "no", "dry_run": "no",
        "write_config": "no", "destructive_write": "no", "post_change_verify": "no",
        "version_aware": "yes",
    },
    "mcp": {
        "discover_commands": "partial", "explain_semantics": "no",
        "validate_before_run": "no", "read_live_state": "yes", "dry_run": "no",
        "write_config": "yes", "destructive_write": "yes", "post_change_verify": "yes",
        "version_aware": "no",
    },
    "mcp+rosetta+skills": {
        "discover_commands": "yes", "explain_semantics": "yes",
        "validate_before_run": "partial", "read_live_state": "yes", "dry_run": "no",
        "write_config": "yes", "destructive_write": "yes", "post_change_verify": "yes",
        "version_aware": "yes",
    },
}


def write_capability_matrix() -> None:
    DATA.mkdir(exist_ok=True)
    with open(DATA / "capability_matrix.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["approach"] + CAPABILITIES)
        for ap, caps in MATRIX.items():
            w.writerow([ap] + [caps[c] for c in CAPABILITIES])


# --------------------------------------------------------------------------- #
# Record/replay scoring
# --------------------------------------------------------------------------- #
def produce_candidate(task: dict, approach: str, replay: dict) -> list[str]:
    """Replay backend: return the canned candidate for (task, ...).

    A real backend would call a model configured with `approach`'s context and
    return the commands it emits. The interface is intentionally this simple.
    """
    return replay.get(task["id"])


def run_replay() -> list[dict]:
    tasks = {t["id"]: t for t in yaml.safe_load(open(CORPUS))["tasks"]}
    fixtures = yaml.safe_load(open(FIXTURES))["fixtures"]
    rows = []
    for f in fixtures:
        task = tasks[f["task"]]
        predicted, sub = predict_label(task, f["candidate"])
        rows.append(
            {
                "task": f["task"],
                "expected_label": f["expected_label"],
                "predicted_label": predicted,
                "correct": int(predicted == f["expected_label"]),
                "missing_keys": "|".join(sub.get("missing_keys", [])),
                "extra_keys": "|".join(sub.get("extra_keys", [])),
            }
        )
    return rows


def main() -> None:
    write_capability_matrix()
    rows = run_replay()
    fields = ["task", "expected_label", "predicted_label", "correct",
              "missing_keys", "extra_keys"]
    with open(DATA / "agent_replay.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    correct = sum(r["correct"] for r in rows)
    n = len(rows)
    print(f"[agent_harness] capability matrix -> data/capability_matrix.csv")
    print(f"[agent_harness] replay scorer accuracy: {correct}/{n} "
          f"({100*correct/n:.0f}%) of canned candidates labeled correctly")
    for r in rows:
        if not r["correct"]:
            print(f"  MISS {r['task']}: expected {r['expected_label']} "
                  f"got {r['predicted_label']}")
    print(f"  wrote {DATA/'agent_replay.csv'}")


if __name__ == "__main__":
    main()
