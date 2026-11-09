import io
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hooks as vhooks  # noqa: E402
import state as vstate  # noqa: E402
import termrender as vterm  # noqa: E402
from test_birth import FakeState, make_live  # noqa: E402


class _C:
    def __init__(self, st):
        self.state = st


class _Tty(io.StringIO):
    def isatty(self):
        return True


class TestPrinterIntegration(unittest.TestCase):
    """The whole beat path, headless: queue -> arm -> flush -> print.

    This is the test that would have caught every layout bug of the last
    day without a terminal in front of us: it asserts the ORDER the user
    sees (headline, spacer, explanation) and the exact paint arguments.
    """

    def setUp(self):
        self.s = FakeState()
        make_live(self.s)
        vstate._ctx = _C(self.s)

    def test_beat_prints_headline_then_picture_then_explanation(self):
        import acts as vacts
        painted = []
        old_paint = vterm.paint_over
        old_can = vhooks._can_paint
        old_out = sys.stdout
        buf = _Tty()
        vhooks._can_paint = lambda: True
        vterm.paint_over = lambda path, rows, trail, delay=0.35, extra_climb=0: painted.append(
            {"rows": rows, "trail": trail})
        sys.stdout = buf
        try:
            vhooks._deliver_beat(
                "HEADLINE here" + vacts.DISH_MARKER + "EXPLANATION here")
            # skip the quiet clock
            vhooks._PICTURE_PENDING["quiet_at"] = time.time() - 1
            for _ in range(60):
                if painted:
                    break
                time.sleep(0.05)
        finally:
            sys.stdout = old_out
            vterm.paint_over = old_paint
            vhooks._can_paint = old_can
        out = buf.getvalue()
        self.assertIn("HEADLINE here", out)
        self.assertIn("EXPLANATION here", out)
        self.assertLess(out.index("HEADLINE here"), out.index("EXPLANATION here"))
        self.assertEqual(len(painted), 1, "exactly one dish")
        self.assertGreater(painted[0]["rows"], 0)
        self.assertEqual(painted[0]["trail"], 2)   # blank line + one explanation line
        # the queue is drained: nothing left for a later turn
        self.assertEqual(vstate.pop_all_narrations(), [])

    def test_silent_voice_prints_nothing(self):
        vstate.set_voice_mode("off")
        painted = []
        old_paint = vterm.paint_over
        old_can = vhooks._can_paint
        old_out = sys.stdout
        buf = _Tty()
        vhooks._can_paint = lambda: True
        vterm.paint_over = lambda *a, **k: painted.append(a)
        sys.stdout = buf
        try:
            vhooks._deliver_beat("should not appear")
            vhooks._PICTURE_PENDING["quiet_at"] = time.time() - 1
            time.sleep(0.5)
        finally:
            sys.stdout = old_out
            vterm.paint_over = old_paint
            vhooks._can_paint = old_can
        self.assertEqual(painted, [])
        self.assertNotIn("should not appear", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
