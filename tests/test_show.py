"""VIV-32: /vivarium show — meet one species up close."""

from __future__ import annotations

import os
import sys
import unittest
import re as _re


def _plain(s):
    return _re.sub(r'\x1b\[[0-9;]*m', '', s)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tools as T  # noqa: E402
import world as W  # noqa: E402
import universe as U  # noqa: E402
import birth as vbirth  # noqa: E402
from test_birth import FakeState, make_live  # noqa: E402


class _C:
    def __init__(self, st):
        self.state = st


class TestShow(unittest.TestCase):
    def setUp(self):
        self.s = FakeState()
        make_live(self.s)
        T.vstate._ctx = _C(self.s)
        self.res = vbirth.birth_species(
            self.s, "proof-skill",
            "# proof-skill\\n\\nCompletely unique body content xyzzy.\\n",
            save_world=lambda w_: self.s.set("world", w_.to_dict()),
            load_world=lambda: W.World.from_dict(
                self.s.d["world"], seed=self.s.get("seed", 0)))
        self.eidos = self.res["eidos"]

    def test_show_by_eidos_id(self):
        text = T._cmd(f"show {self.eidos}")
        self.assertIn(self.eidos, text)
        self.assertIn("Venefica", text) or self.assertIn("the", text)
        self.assertIn("hatched    tick", _plain(text))
        self.assertIn("alive      ", _plain(text))

    def test_show_by_name_fragment(self):
        text = T._cmd("show proof")
        self.assertIn(self.eidos, text)

    def test_show_unknown_and_ambiguous(self):
        text = T._cmd("show nope")
        self.assertIn("Unknown species", text)
        self.assertIn("/vivarium show", text)

    def test_show_bare_lists_species(self):
        text = T._cmd("show")
        self.assertIn(self.eidos, text)
        self.assertIn("proof-skill", text)

    def test_show_empty_universe(self):
        self.s.set("births", {})
        text = T._cmd("show")
        self.assertIn("No species have been born", text)


if __name__ == "__main__":
    unittest.main()
