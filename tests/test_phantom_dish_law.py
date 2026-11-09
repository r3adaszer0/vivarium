import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tools as T  # noqa: E402
import state as vstate  # noqa: E402
import universe as U  # noqa: E402
from test_birth import FakeState  # noqa: E402


class _C:
    def __init__(self, st):
        self.state = st


class TestPhantomDishLaw(unittest.TestCase):
    """Era-9 incident: a restart left the universe dormant, yet a full
    dish image painted under the dormant status text and the agent
    quoted stale era-9 numbers. Law: a DORMANT universe has NO world —
    no code path may materialize one, and every turn must say so."""

    def setUp(self):
        self.s = FakeState()
        U.universe_record(self.s)  # creates the dormant record
        T.vstate._ctx = _C(self.s)

    def test_load_world_never_materializes_on_dormant(self):
        self.assertIsNone(vstate.load_world())
        self.assertIsNone(self.s.get("world"))  # nothing was saved

    def test_slash_status_dormant_has_no_dish(self):
        out = T._cmd("status")
        self.assertIn("dormant", out)
        self.assertNotIn("X = creatures", out)
        self.assertIsNone(self.s.get("world"))  # no phantom world born

    def test_pre_llm_dormant_warns_against_stale_numbers(self):
        import hooks as vhooks
        out = vhooks._on_pre_llm_call(session_id="s", is_first_turn=True)
        self.assertIn("STALE", out["context"])
        self.assertIn("sleeps", out["context"])


if __name__ == "__main__":
    unittest.main()
