"""VIV-35: start/restart deliver the universe visually, best-effort."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tools as T  # noqa: E402
import state as vstate  # noqa: E402
from test_birth import FakeState, make_live  # noqa: E402


class _C:
    def __init__(self, st):
        self.state = st


class TestUniverseView(unittest.TestCase):
    def setUp(self):
        self.s = FakeState()
        make_live(self.s)
        T.vstate._ctx = _C(self.s)

    def test_start_nongraphics_shows_rich_and_path(self):
        out = T._cmd("start")
        self.assertIn("The Vivarium is alive", out)
        self.assertIn("live picture of your universe", out)
        self.assertIn("universe_0.png", out)
        # rich map: block shading characters, not the plain dots/X map
        self.assertIn("░", out) or self.assertIn("▒", out)
        self.assertIn("github.com/r3adaszer0/vivarium", out)
        self.assertIn("/vivarium status", out)

    def test_start_graphics_paints(self):
        import termrender as vterm
        old = vterm.detect_graphics
        vterm.detect_graphics = lambda: "kitty"
        try:
            out = T._cmd("start")
        finally:
            vterm.detect_graphics = old
        # graphics path: NO ascii map, spacer rows instead
        self.assertNotIn("A live picture of your universe is saved", out)

    def test_dormant_start_unchanged(self):
        self.s.set("universe", {"v": 1, "status": "dormant", "era": 2,
                                "key_fp": "ab", "genesis": None})
        out = T._cmd("start")
        self.assertIn("dormant", out)
        self.assertNotIn("live picture", out)


if __name__ == "__main__":
    unittest.main()
