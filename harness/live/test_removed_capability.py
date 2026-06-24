"""Anchor tests for removed_capability scoring (route-unreachable trap).

RouterOS v7 removed the v6 `unreachable`/`prohibit` route types from /ip/route --
no creatable form exists (device-verified, data/route_unreachable_device_verify.csv),
only `blackhole` survives. The route-unreachable task is therefore marked
`removed_capability` with no satisfiable gold. These lock the scorer's two outcomes:
trap-fell (emitted a removed v6 form) vs trap-avoided (emitted the v7 blackhole
alternative, or no command). Loads the real task from the corpus so the trap_tokens
and acceptable_variants stay in sync.

Run: .venv/bin/python -m unittest harness.live.test_removed_capability
"""
import unittest
from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from lib.scorer import predict_label  # noqa: E402

CORPUS = Path(__file__).resolve().parents[2] / "tasks" / "corpus.yaml"


def _task(tid: str) -> dict:
    with open(CORPUS) as fh:
        return {t["id"]: t for t in yaml.safe_load(fh)["tasks"]}[tid]


class TestRemovedCapability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.task = _task("route-unreachable")

    def label(self, cmds):
        return predict_label(self.task, cmds)[0]

    # --- trap-fell: the removed v6 forms (all device-rejected) ----------- #
    def test_v6_type_unreachable_fell(self):
        self.assertEqual(
            self.label(["/ip/route add dst-address=172.16.0.0/12 type=unreachable"]),
            "trap-fell")

    def test_bare_unreachable_fell(self):
        self.assertEqual(
            self.label(["/ip/route add dst-address=172.16.0.0/12 unreachable"]),
            "trap-fell")

    def test_unreachable_eq_yes_fell(self):
        self.assertEqual(
            self.label(["/ip/route add dst-address=172.16.0.0/12 unreachable=yes"]),
            "trap-fell")

    def test_type_prohibit_fell(self):
        self.assertEqual(
            self.label(["/ip/route add dst-address=172.16.0.0/12 type=prohibit"]),
            "trap-fell")

    # --- trap-avoided: v7 alternative or recognized removal -------------- #
    def test_blackhole_alternative_avoided(self):
        self.assertEqual(
            self.label(["/ip/route add dst-address=172.16.0.0/12 blackhole"]),
            "trap-avoided")

    def test_blackhole_space_form_avoided(self):
        # space-form menu path is equivalent and must still be recognized
        self.assertEqual(
            self.label(["/ip route add dst-address=172.16.0.0/12 blackhole"]),
            "trap-avoided")

    def test_empty_recognizes_removal(self):
        self.assertEqual(self.label([]), "trap-avoided")

    # --- fall through: an unrelated mistake still surfaces --------------- #
    def test_wrong_path_falls_through(self):
        # /routing/route is read-only and has no trap token -> not trap-fell,
        # scored by the normal path (wrong_path against the /ip/route alternative)
        self.assertEqual(
            self.label(["/routing/route add dst-address=172.16.0.0/12 gateway=1.1.1.1"]),
            "wrong_path")


if __name__ == "__main__":
    unittest.main()
