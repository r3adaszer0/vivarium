"""VIV-36: /vivarium doctor — ground-truth diagnostic."""

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


class TestDoctor(unittest.TestCase):
    def setUp(self):
        self.s = FakeState()
        make_live(self.s)
        T.vstate._ctx = _C(self.s)

    def test_doctor_reports_state_and_build(self):
        out = T._cmd("doctor")
        self.assertIn("vivarium doctor", out)
        self.assertIn("status=live", out)
        self.assertIn("narration queues", out)
        self.assertIn("graphics:", out)
        self.assertIn("build:", out)
        self.assertIn("milestone_queue=True", out)
        self.assertIn("relay_header=True", out)

    def test_doctor_dormant(self):
        self.s.set("universe", {"v": 1, "status": "dormant", "era": 2,
                                "key_fp": "ab", "genesis": None})
        out = T._cmd("doctor")
        self.assertIn("status=dormant", out)
        self.assertIn("status=dormant", out)


if __name__ == "__main__":
    unittest.main()
