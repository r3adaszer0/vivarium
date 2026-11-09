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

    def test_dormant_turn_injects_nothing(self):
        """VIV-46: dormant is internal state, never conversation."""
        import hooks as vhooks
        out = vhooks._on_pre_llm_call(
            session_id="s", is_first_turn=True, user_message="hey")
        self.assertIsNone(out)
        self.assertIsNone(self.s.get("world"))

    def test_load_world_purges_a_saved_phantom(self):
        """A world file saved by pre-law code on a dormant universe is
        purged on first read (self-healing)."""
        import world as W
        self.s.set("world", W.new_world(seed=7).to_dict())
        self.assertIsNone(vstate.load_world())
        self.assertIsNone(self.s.get("world"))


if __name__ == "__main__":
    unittest.main()
