"""Anchor tests for parse_commands menu-context folding.

The live steer agent emits the RouterOS console two-step form (a bare menu path
line that changes context, then a verb line applied there). parse_commands folds
that back into one command per operation; these lock that behavior and the
single-line passthrough so the scorer sees well-formed commands.

Run: .venv/bin/python -m unittest harness.live.test_parse_commands
"""
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness.live.run_live_ladder import parse_commands  # noqa: E402


class TestParseCommands(unittest.TestCase):
    def test_single_line_passthrough(self):
        # the common case is unchanged: one full command in, one out
        self.assertEqual(
            parse_commands("/ip route add dst-address=10.10.10.0/24 blackhole"),
            ["/ip route add dst-address=10.10.10.0/24 blackhole"],
        )

    def test_menu_context_fold(self):
        # bare path then verb -> one joined command (was scored missing_arg)
        out = parse_commands("/interface/vlan\nadd name=vlan100 vlan-id=100 interface=ether2")
        self.assertEqual(out, ["/interface/vlan add name=vlan100 vlan-id=100 interface=ether2"])

    def test_two_menu_two_verbs(self):
        # each verb folds into the path most recently navigated to
        txt = ("/interface/bridge/port\n"
               "add bridge=bridge1 interface=ether4 pvid=30\n"
               "/interface/bridge/vlan\n"
               "add bridge=bridge1 untagged=ether4 vlan-ids=30")
        self.assertEqual(parse_commands(txt), [
            "/interface/bridge/port add bridge=bridge1 interface=ether4 pvid=30",
            "/interface/bridge/vlan add bridge=bridge1 untagged=ether4 vlan-ids=30",
        ])

    def test_space_form_navigation(self):
        # space-form menu path is also recognized as navigation
        out = parse_commands("/ip firewall filter\nadd chain=input action=accept")
        self.assertEqual(out, ["/ip/firewall/filter add chain=input action=accept"])

    def test_fences_and_numbering_stripped(self):
        out = parse_commands("```routeros\n1. /interface/vlan\nadd name=v1 vlan-id=5 interface=e2\n```")
        self.assertEqual(out, ["/interface/vlan add name=v1 vlan-id=5 interface=e2"])


if __name__ == "__main__":
    unittest.main()
