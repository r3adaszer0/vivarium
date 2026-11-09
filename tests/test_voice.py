import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import state as vstate  # noqa: E402
import universe as U  # noqa: E402
from test_birth import FakeState, make_live  # noqa: E402


class _C:
    def __init__(self, st):
        self.state = st


class TestVoiceDial(unittest.TestCase):
    """VIV-46: one dial for how much the dish says, quiet by default."""

    def setUp(self):
        self.s = FakeState()
        vstate._ctx = _C(self.s)

    def test_default_is_births(self):
        self.assertEqual(vstate.voice_mode(), "births")

    def test_births_voice_allows_only_births(self):
        self.assertTrue(vstate.voice_allows("birth"))
        self.assertFalse(vstate.voice_allows("death"))
        self.assertFalse(vstate.voice_allows("codex"))
        self.assertFalse(vstate.voice_allows("report"))

    def test_milestones_adds_deaths_and_discoveries(self):
        vstate.set_voice_mode("milestones")
        self.assertTrue(vstate.voice_allows("birth"))
        self.assertTrue(vstate.voice_allows("death"))
        self.assertTrue(vstate.voice_allows("codex"))
        self.assertFalse(vstate.voice_allows("report"))

    def test_daily_adds_the_report(self):
        vstate.set_voice_mode("daily")
        self.assertTrue(vstate.voice_allows("report"))

    def test_off_is_silent(self):
        vstate.set_voice_mode("off")
        for kind in ("birth", "death", "codex", "report"):
            self.assertFalse(vstate.voice_allows(kind))

    def test_legacy_on_maps_to_milestones(self):
        self.s.set("voice_mode", "on")
        self.assertEqual(vstate.voice_mode(), "milestones")

    def test_invalid_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            vstate.set_voice_mode("loud")


class TestContentIdentity(unittest.TestCase):
    """VIV-46: the species is the CONTENT. Re-learning the same thing
    under a new name must not spawn a twin."""

    def test_same_content_under_two_names_births_once(self):
        import birth as B
        import world as W
        s = FakeState()
        make_live(s)
        vstate._ctx = _C(s)
        r1 = B.birth_species(s, "skill-one", "identical body",
                             save_world=vstate.save_world,
                             load_world=vstate.load_world)
        r2 = B.birth_species(s, "skill-two", "identical body",
                             save_world=vstate.save_world,
                             load_world=vstate.load_world)
        self.assertIsNotNone(r1)
        self.assertIsNone(r2)


if __name__ == "__main__":
    unittest.main()
