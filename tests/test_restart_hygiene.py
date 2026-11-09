import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import state as vstate  # noqa: E402
import universe as U  # noqa: E402


class _Store(dict):
    def set(self, k, v): self[k] = v
    def save(self): pass


class _Ctx:
    def __init__(self, d): self.state = _Store(d)
    def save_session(self, *a, **k): pass


class TestRestartHygiene(unittest.TestCase):
    """Era boundaries: stale narrations and per-universe acts must not
    cross a restart (the era-8 stale-death + missing-act-2 incident)."""

    def _live(self):
        s = {"universe": {"v": 1, "status": "live", "era": 7,
                          "key_fp": "aa11bb33", "genesis": {"day": "d"}},
             "pending_narration": ["🪦 old-era death beat"],
             "pending_narration_milestones": ["old milestone"],
             "acts": {"big_bang": "2026-11-09", "death": "2026-11-09",
                      "_births_since_bang": 3}}
        vstate.bind(_Ctx(s))
        return s

    def test_restart_clears_narrations_and_acts(self):
        self._live()
        st = vstate.state()
        U.restart(st, reason="test")
        self.assertEqual(st["pending_narration"], [])
        self.assertEqual(st["pending_narration_milestones"], [])
        self.assertEqual(st["acts"], {})
        rec = U.universe_record(vstate.state())
        self.assertEqual(rec["status"], "dormant")
        self.assertEqual(rec["era"], 8)


if __name__ == "__main__":
    unittest.main()
