"""VIV-31: the walkthrough acts — gating, once-ness, narration-off."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import acts as A  # noqa: E402
import world as W  # noqa: E402
import state as vstate  # noqa: E402
import hooks  # noqa: E402
from test_birth import FakeState, make_live  # noqa: E402


class _C:
    def __init__(self, st):
        self.state = st


class TestActs(unittest.TestCase):
    def setUp(self):
        self.s = FakeState()

    def test_act2_rides_first_big_bang_only(self):
        base = "🌌 Universe born (era 1)."
        out = A.birth_narration(self.s, base, {}, is_big_bang=True)
        self.assertIn("This dish is your Vivarium universe", out)
        self.assertIn("DNA taken from your skills", out)
        out2 = A.birth_narration(self.s, base, {}, is_big_bang=True)
        self.assertEqual(out2, base, "act 2 must fire once")

    def test_act3_on_second_birth_act4_on_third(self):
        r = {"eidos": "Eidos_1", "name": "a", "pod": 4, "tick": 10}
        A.birth_narration(self.s, "BASE", r, is_big_bang=True)  # the Bang
        out = A.birth_narration(self.s, "BASE", r, is_big_bang=False)
        self.assertIn("Remember the promise?", out)
        self.assertIn("/vivarium show Eidos_1", out)
        self.assertIn("/vivarium clip", out)
        out2 = A.birth_narration(self.s, "BASE", r, is_big_bang=False)
        self.assertIn("/vivarium export", out2)
        self.assertIn("/vivarium race", out2)
        out3 = A.birth_narration(self.s, "BASE", r, is_big_bang=False)
        self.assertEqual(out3, "BASE", "fourth birth is plain")

    def test_act3_honesty_about_not_first(self):
        r = {"eidos": "Eidos_1", "name": "a", "pod": 4, "tick": 10}
        A.birth_narration(self.s, "BASE", r, is_big_bang=True)  # the Bang
        out = A.birth_narration(self.s, "BASE", r, is_big_bang=False)
        self.assertIn("it is not your first", out)

    def test_narration_off_bare_lines(self):
        r = {"eidos": "Eidos_1", "name": "a", "pod": 4, "tick": 10}
        A.set_narration(self.s, "off")
        out = A.birth_narration(self.s, "BASE", r, is_big_bang=False)
        self.assertIn("New species: Eidos_1", out)
        self.assertNotIn("Remember the promise", out)
        # big bang in off mode: base only, act marked seen
        out2 = A.birth_narration(self.s, "BASE", r, is_big_bang=True)
        self.assertEqual(out2, "BASE")
        self.assertTrue(A._seen(self.s, A.ACT2))
        # dormant brief survives off
        self.assertEqual(A.dormant_line("BRIEF"), "BRIEF")

    def test_codex_act_fires_once(self):
        line = "📖 Codex entry: Still Life confirmed — population 199 held 1500 ticks."
        out = A.codex_narration(self.s, line, "Still Life")
        self.assertIn("/vivarium codex", out)
        out2 = A.codex_narration(self.s, line, "Still Life")
        self.assertEqual(out2, line)

    def test_death_act_fires_once(self):
        line = "🪦 The Eidos_9 lineage has died out (last seen tick 500)."
        out = A.death_narration(self.s, line, "Eidos_9")
        self.assertIn("how this world selects", out)
        out2 = A.death_narration(self.s, line, "Eidos_9")
        self.assertEqual(out2, line)

    def test_no_em_dashes_in_act_copy(self):
        for text in (A.ACT2_TEXT, A.act3_for({}), A.act4_text(),
                     A.act_codex_text("Still Life"), A.act_death_text("Eidos_x"),
                     A.bare_birth_line({})):
            self.assertNotIn("—", text)

    def test_extinction_detection_in_advance(self):
        ctx = _C(self.s)
        vstate.bind(ctx)
        make_live(self.s)
        w = W.World.from_dict(self.s.d["world"], seed=self.s.get("seed", 0))
        genome = W.genome_from_bytes(bytes(range(24)))
        w.creatures = [W.Creature(gid=1, genome=dict(genome),
                                  x=5, y=5, energy=0.01, lineage="Eidos_doom")]
        w.next_gid = 2
        self.s.set("world", w.to_dict())
        vstate.set_voice_mode("milestones")   # deaths are a milestone event
        vstate.advance(w, ticks=3, nutrients=0.0)
        pend = vstate.narration_text()
        self.assertIn("Eidos_doom", pend)
        self.assertIn("how this world selects", pend)

    def test_extinction_is_silent_in_births_voice(self):
        """Default voice: births only. Deaths do not interrupt."""
        ctx = _C(self.s)
        vstate.bind(ctx)
        make_live(self.s)
        w = W.World.from_dict(self.s.d["world"], seed=self.s.get("seed", 0))
        genome = W.genome_from_bytes(bytes(range(24)))
        w.creatures = [W.Creature(gid=1, genome=dict(genome),
                                  x=5, y=5, energy=0.01, lineage="Eidos_doom")]
        w.next_gid = 2
        self.s.set("world", w.to_dict())
        self.assertEqual(vstate.voice_mode(), "births")
        vstate.advance(w, ticks=3, nutrients=0.0)
        self.assertNotIn("Eidos_doom", vstate.narration_text())


if __name__ == "__main__":
    unittest.main()

def test_big_bang_and_birth_narrations_are_milestones(self):
    """0a1e4b8 follow-up: the two story beats (Big Bang onboard, birth
    announcement) queue as MILESTONES — routine reports cannot clobber
    them (the hows-the-cat silent-Big-Bang incident, 2026-11-09)."""
    import state as vstate2
    class _Store(dict):
        def set(self, k, v): self[k] = v
        def save(self): pass
    class _Ctx:
        def __init__(self, d): self.state = _Store(d)
        def save_session(self, *a, **k): pass
    s = {"universe": {"v": 1, "status": "dormant", "era": 3,
                      "key_fp": "ab12cd34", "genesis": None}}
    vstate2.bind(_Ctx(s))
    vhooks._on_skill_lifecycle(skill_name="probe-skill", action="created")
    rec = vstate2.universe_record()
    self.assertEqual(rec.get("status"), "live")
    # bury the queue under routine reports
    for i in range(6):
        vstate2.queue_narration(f"routine report {i}")
    got = vstate2.pop_narration()
    self.assertIsNotNone(got)
    self.assertIn("This dish is your Vivarium universe", got)
