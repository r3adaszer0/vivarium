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

    def test_births_voice_allows_births_and_codex(self):
        """VIV-75: a Codex discovery is a birth — a pattern being born into
        the dish — so the default dial announces it like a birth. Only
        deaths and the daily report stay behind the dial."""
        self.assertTrue(vstate.voice_allows("birth"))
        self.assertTrue(vstate.voice_allows("codex"))
        self.assertFalse(vstate.voice_allows("death"))
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


class TestCodexIsABirth(unittest.TestCase):
    """VIV-75: a Codex discovery is the dish speaking a birth — the default
    "births" dial must not mute it, and it rides the MILESTONE queue so
    routine reports cannot clobber it. Era 9 ran 7290 ticks with the Pulse
    confirmed at tick 6980 and never announced: the narration was dropped
    at queue time, before any card, relay or trace existed."""

    def setUp(self):
        self.s = FakeState()
        vstate._ctx = _C(self.s)

    def test_codex_announces_in_default_voice_and_rides_milestones(self):
        import world as W
        make_live(self.s)
        w = W.World.from_dict(self.s.d["world"],
                              seed=self.s.get("seed", 0))
        import codex as vcodex_mod
        original = vcodex_mod.observe
        vcodex_mod.observe = lambda *a, **k: [
            "📖 Codex entry: Pulse confirmed — period 120 ticks."]
        try:
            vstate.advance(w, ticks=1, nutrients=0.0)
        finally:
            vcodex_mod.observe = original
        # the discovery must sit in the milestone queue, first out even
        # when routine reports pile up behind it
        self.assertIn("Codex entry",
                      (self.s.d.get("pending_narration_milestones") or [""])[-1])
        for i in range(6):
            vstate.queue_narration(f"routine report {i}")
        got = vstate.pop_narration()
        self.assertIsNotNone(got)
        self.assertIn("Codex entry", got)
        self.assertNotIn("routine report", got)

    def test_off_still_silences_the_codex(self):
        vstate.set_voice_mode("off")
        self.assertFalse(vstate.voice_allows("codex"))


if __name__ == "__main__":
    unittest.main()
