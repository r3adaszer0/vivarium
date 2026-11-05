"""VIV-10 acceptance: Pulse detection + Codex recording, honestly."""
import sys, unittest
sys.path.insert(0, '.')

try:
    from . import codex as X
except ImportError:
    import codex as X


class FakeState:
    def __init__(self):
        self.d = {}
    def get(self, k, default=None):
        return self.d.get(k, default)
    def set(self, k, v):
        self.d[k] = v


def curve_from_pops(pops, start_tick=0):
    return [{"tick": start_tick + i, "population": p} for i, p in enumerate(pops)]


class PulseDetection(unittest.TestCase):
    def test_full_cycle_detected(self):
        # boom 104 -> crash to 19 -> recover to 103: one complete Pulse
        # (~171-tick cycle, above MIN_PERIOD; the live dish showed ~600)
        pops = ([104] * 60 + list(range(104, 10, -2)) + [19] * 30
                + list(range(19, 104, 2)))
        found = X.detect_pulse(curve_from_pops(pops))
        self.assertIsNotNone(found)
        self.assertEqual(found["pattern"], "pulse")
        self.assertGreaterEqual(found["period"], X.MIN_PERIOD)

    def test_monotonic_growth_not_a_pulse(self):
        pops = list(range(10, 104))
        self.assertIsNone(X.detect_pulse(curve_from_pops(pops)))

    def test_stable_population_not_a_pulse(self):
        pops = [100] * 200
        self.assertIsNone(X.detect_pulse(curve_from_pops(pops)))

    def test_small_populations_ignored(self):
        # peak below MIN_PEAK: a crash there is noise, not a Pulse
        pops = [10] * 10 + [1] * 10 + [10] * 10
        self.assertIsNone(X.detect_pulse(curve_from_pops(pops)))

    def test_extinction_spiral_not_a_pulse(self):
        # boom to 26 then collapse to 9 with no real recovery: the peak never
        # reached 2.5x the baseline -> not a Pulse (VIV-10 tightening)
        pops = ([26] * 10 + [16, 9] * 10 + [14] * 10)
        self.assertIsNone(X.detect_pulse(curve_from_pops(pops)))

    def test_detector_state_persists_across_calls(self):
        # crash in call 1, recovery in call 2 -> still detected (streaming)
        s = {}
        pops1 = ([104] * 60 + list(range(104, 40, -2)))
        pops2 = ([38] * 30 + list(range(38, 104, 2)))
        self.assertIsNone(X.detect_pulse(curve_from_pops(pops1), s))
        found = X.detect_pulse(curve_from_pops(pops2, start_tick=len(pops1)), s)
        self.assertIsNotNone(found)
        self.assertEqual(found["pattern"], "pulse")


class Codex(unittest.TestCase):
    def test_record_and_dedupe(self):
        s = FakeState()
        d1 = X.record_discovery(s, {"pattern": "pulse", "period": 612,
                                    "evidence": {"peak_population": 104}}, "2026-11-05")
        self.assertEqual(d1["times_observed"], 1)
        d2 = X.record_discovery(s, {"pattern": "pulse", "period": 612,
                                    "evidence": {"peak_population": 104}}, "2026-11-06")
        self.assertEqual(d2["times_observed"], 2)
        self.assertEqual(len(X.codex_all(s)), 1)      # deduped
        self.assertEqual(d2["last_seen"], "2026-11-06")

    def test_different_periods_are_separate_entries(self):
        s = FakeState()
        X.record_discovery(s, {"pattern": "pulse", "period": 612}, "2026-11-05")
        X.record_discovery(s, {"pattern": "pulse", "period": 400}, "2026-11-06")
        self.assertEqual(len(X.codex_all(s)), 2)

    def test_export_is_clean_and_readable(self):
        s = FakeState()
        X.record_discovery(s, {"pattern": "pulse", "period": 612,
                               "evidence": {"peak_population": 104}},
                           "2026-11-05")
        text = X.export_codex(s)
        self.assertIn("## Pulse", text)
        self.assertIn("612", text)
        for banned in ("universe_key", "SKILL", "skill_content", "hmac"):
            self.assertNotIn(banned, text)

    def test_export_empty(self):
        self.assertIn("No discoveries", X.export_codex(FakeState()))


class StillLife(unittest.TestCase):
    def test_plateau_detected(self):
        # samples every 10 ticks (like the real feed): 160 samples = 1500 ticks
        curve = [{"tick": 1000 + i * 10, "population": 200} for i in range(160)]
        found = X.detect_still_life(curve)
        self.assertIsNotNone(found)
        self.assertEqual(found["pattern"], "still_life")
        self.assertEqual(found["evidence"]["duration_ticks"], 1500)

    def test_fluctuating_population_not_still_life(self):
        pops = [200, 180, 160, 190] * 40
        self.assertIsNone(X.detect_still_life(curve_from_pops(pops)))

    def test_short_plateau_ignored(self):
        pops = [200] * 100          # < STILL_LIFE_TICKS
        self.assertIsNone(X.detect_still_life(curve_from_pops(pops)))

    def test_still_life_recorded_in_codex(self):
        s = FakeState()
        X.record_discovery(s, {"pattern": "still_life", "period": None,
                               "evidence": {"population": 200,
                                            "duration_ticks": 1500}},
                           "2026-11-05")
        self.assertEqual(len(X.codex_all(s)), 1)
        self.assertIn("Still life", X.export_codex(s))


class Staleness(unittest.TestCase):
    """VIV-11: evidence-based stale verdict — a nudge, never an action."""

    def test_young_when_not_enough_history(self):
        st = X.staleness([{"tick": i, "population": 10, "born": i} for i in range(10)])
        self.assertEqual(st["verdict"], "young")
        self.assertIsNone(st["suggestion"])

    def test_healthy_when_moving_and_breeding(self):
        curve = [{"tick": i * 10, "population": 90 + (i % 7), "born": i * 3}
                 for i in range(200)]
        st = X.staleness(curve)
        self.assertEqual(st["verdict"], "healthy")

    def test_flat_and_birthless_is_stale(self):
        curve = [{"tick": i * 10, "population": 199, "born": 500}
                 for i in range(200)]          # 2000 ticks, zero births
        st = X.staleness(curve)
        self.assertEqual(st["verdict"], "stale")
        self.assertIn("flat", st["detail"])
        self.assertIn("no births", st["detail"])
        self.assertIn("/vivarium restart", st["suggestion"])

    def test_no_births_alone_is_stale(self):
        # population moves but nothing is born: still stale
        curve = [{"tick": i * 10, "population": 120 + (i % 9), "born": 77}
                 for i in range(200)]
        st = X.staleness(curve)
        self.assertEqual(st["verdict"], "stale")
        self.assertIn("no births", st["detail"])


class Observe(unittest.TestCase):
    """VIV-11: the wiring — curve sampling + detector runs during advance."""

    def _summaries(self, ticks, pops):
        return [{"tick": t, "population": p, "born": 0, "died": 0, "delta": 0}
                for t, p in zip(ticks, pops)]

    def test_curve_sampled_every_10_ticks(self):
        s = FakeState()
        X.observe(s, None, self._summaries(range(1, 31), [10] * 30))
        curve = s.get("curve")
        self.assertEqual([c["tick"] for c in curve], [10, 20, 30])

    def test_pulse_found_via_observe_and_narrated(self):
        s = FakeState()
        pops = ([104] * 60 + list(range(104, 10, -2)) + [19] * 30
                + list(range(19, 104, 2)))
        ticks = [i * 10 for i in range(len(pops))]
        lines = X.observe(s, None, self._summaries(ticks, pops))
        self.assertEqual(len(X.codex_all(s)), 1)
        self.assertEqual(X.codex_all(s)[0]["pattern"], "pulse")
        self.assertTrue(any("Pulse" in l for l in lines))

    def test_no_double_counting_across_calls(self):
        s = FakeState()
        pops = ([104] * 60 + list(range(104, 10, -2)) + [19] * 30
                + list(range(19, 104, 2)))
        ticks = [i * 10 for i in range(len(pops))]
        X.observe(s, None, self._summaries(ticks, pops))
        X.observe(s, None, self._summaries(ticks, pops))   # same batch again
        self.assertEqual(len(X.codex_all(s)), 1)           # not re-recorded
        self.assertEqual(X.codex_all(s)[0]["times_observed"], 1)

    def test_still_life_end_gets_cause_chapter(self):
        s = FakeState()
        s.set("codex", [{"pattern": "still_life", "period": None,
                         "evidence": {"population": 199}, "first_seen": "d"}])
        s.set("births", {"somename": {"eidos": "Eidos_da4824", "tick": 5040,
                                      "day": "2026-11-05"}})
        # an open plateau (as the detector would leave it mid-plateau)
        s.set("still_life_state", {"plateau_start_tick": 5000, "plateau_pop": 199})
        # plateau at 199 breaks at tick 5100: within the birth window
        X.observe(s, None, self._summaries([5090, 5100], [199, 150]))
        entry = X.codex_all(s)[0]
        self.assertEqual(entry["ended"]["tick"], 5100)
        self.assertIn("Eidos_da4824", entry["ended"]["cause"])
        self.assertNotIn("somename", entry["ended"]["cause"])   # privacy: no names


if __name__ == "__main__":
    unittest.main()
