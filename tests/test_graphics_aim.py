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
        self.assertIn("image=true", out["summary"])

    def test_tool_render_image_carries_paint_directive(self):
        import termrender as vterm
        old = vterm.detect_graphics
        vterm.detect_graphics = lambda: "kitty"
        try:
            out = json.loads(T._tool_render({"image": True}))
        finally:
            vterm.detect_graphics = old
        self.assertIn("image=true", out["summary"])
        self.assertTrue(out.get("media"))


    def test_tool_render_image_paints_inline_on_tty(self):
        """VIV-38: render image=true on a graphics-capable TTY paints the
        dish via emit_image_raw — no ASCII map, no attach."""
        import json as _json
        import termrender as vterm
        painted = []
        old_detect = vterm.detect_graphics
        old_emit = vterm.emit_image_raw
        vterm.detect_graphics = lambda env=None: "kitty"
        vterm.emit_image_raw = (lambda path, env=None, force=None:
                                (painted.append(path), "kitty graphics emitted")[1])
        real = sys.stdout

        class _FakeTty:
            def isatty(self): return True
            def write(self, b): return len(b)
            def flush(self): pass

        sys.stdout = _FakeTty()
        try:
            out = _json.loads(T._tool_render({"image": True}))
        finally:
            sys.stdout = real
            vterm.detect_graphics = old_detect
            vterm.emit_image_raw = old_emit
        self.assertEqual(len(painted), 1)
        self.assertIn("painted inline", out.get("graphics", ""))
        self.assertEqual(out.get("map"), "")

    def test_slash_status_hides_the_agent_directive(self):
        """The slash path paints the dish itself, so the visible text
        must not carry the agent-facing 'call vivarium_render' line
        (user saw it appended under /vivarium status)."""
        import termrender as vterm
        old = vterm.detect_graphics
        vterm.detect_graphics = lambda: "kitty"
        try:
            out = T._cmd("status")
        finally:
            vterm.detect_graphics = old
        self.assertNotIn("this terminal paints images", out)

    def test_tool_status_keeps_the_agent_directive(self):
        import termrender as vterm
        old = vterm.detect_graphics
        vterm.detect_graphics = lambda: "kitty"
        try:
            out = json.loads(T._tool_status({}))
        finally:
            vterm.detect_graphics = old
        self.assertIn("this terminal paints images", out["summary"])

    def test_status_leaves_an_empty_line_before_the_picture(self):
        import termrender as vterm
        old = vterm.detect_graphics
        vterm.detect_graphics = lambda: "kitty"
        try:
            out = T._cmd("status")
        finally:
            vterm.detect_graphics = old
        self.assertIn("\n\n\n", out)

    def test_restart_does_not_print_the_graphics_offer(self):
        """The farewell picture is painted by restart itself; the
        'Graphics-capable terminal detected' line would be noise."""
        import termrender as vterm
        old = vterm.detect_graphics
        vterm.detect_graphics = lambda: "kitty"
        try:
            out = T._do_restart()
        finally:
            vterm.detect_graphics = old
        self.assertNotIn("Graphics-capable terminal detected", out)


if __name__ == "__main__":
    unittest.main()
