import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tools as T  # noqa: E402
import json  # noqa: E402
from test_birth import FakeState, make_live  # noqa: E402


class _C:
    def __init__(self, st):
        self.state = st


class TestGraphicsAim(unittest.TestCase):
    """VIV-37: always aim for the graphics image when the terminal
    can paint."""

    def setUp(self):
        self.s = FakeState()
        make_live(self.s)
        T.vstate._ctx = _C(self.s)

    def test_slash_status_plain_terminal_keeps_ascii(self):
        import termrender as vterm
        old = vterm.detect_graphics
        vterm.detect_graphics = lambda: "none"
        try:
            out = T._cmd("status")
        finally:
            vterm.detect_graphics = old
        self.assertIn("X = creatures", out)

    def test_slash_status_graphics_no_ascii_map(self):
        import termrender as vterm
        old = vterm.detect_graphics
        vterm.detect_graphics = lambda: "kitty"
        try:
            out = T._cmd("status")
        finally:
            vterm.detect_graphics = old
        self.assertNotIn("X = creatures", out)
        # reserved spacer rows exist (blank lines painted over)

    def test_tool_status_carries_paint_directive(self):
        import termrender as vterm
        old = vterm.detect_graphics
        vterm.detect_graphics = lambda: "kitty"
        try:
            out = json.loads(T._tool_status({}))
        finally:
            vterm.detect_graphics = old
        self.assertIn("render --image", out["summary"])

    def test_tool_render_image_carries_paint_directive(self):
        import termrender as vterm
        old = vterm.detect_graphics
        vterm.detect_graphics = lambda: "kitty"
        try:
            out = json.loads(T._tool_render({"image": True}))
        finally:
            vterm.detect_graphics = old
        self.assertIn("render --image", out["summary"])
        self.assertTrue(out.get("media"))


if __name__ == "__main__":
    unittest.main()
