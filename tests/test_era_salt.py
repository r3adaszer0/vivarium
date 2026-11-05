"""VIV-6 acceptance: era-salted restart never replays the same world."""
import sys, unittest
sys.path.insert(0, '.')

try:
    from . import universe as U, seeding as S, world as W
except ImportError:
    import universe as U, seeding as S, world as W


class FakeState:
    def __init__(self):
        self.d = {}
    def get(self, k, default=None):
        return self.d.get(k, default)
    def set(self, k, v):
        self.d[k] = v


SKILLS = [
    {"name": "alpha", "is_canon": True, "bytes": b"canon skill one"},
    {"name": "beta", "is_canon": True, "bytes": b"canon skill two"},
    {"name": "private-x", "is_canon": False, "bytes": b"my secret skill"},
]


def snapshot_world(w):
    return (tuple(tuple(round(f, 4) for f in row) for row in w.food),
            tuple((c.gid, c.x, c.y, round(c.energy, 3)) for c in w.creatures))


class EraSalt(unittest.TestCase):
    def test_era1_public_bigbang_deterministic(self):
        s1, s2 = FakeState(), FakeState()
        r1 = S.seed(s1, SKILLS, lambda w: None)
        r2 = S.seed(s2, SKILLS, lambda w: None)
        # same canon kit + same era-1 public derivation -> same world
        self.assertEqual(snapshot_world(r1["world"]), snapshot_world(r2["world"]))

    def test_era2_never_replays_era1(self):
        s = FakeState()
        r1 = S.seed(s, SKILLS, lambda w: None)
        snap1 = snapshot_world(r1["world"])
        U.restart(s, reason="test")
        r2 = S.seed(s, SKILLS, lambda w: None)
        snap2 = snapshot_world(r2["world"])
        self.assertNotEqual(snap1, snap2)          # same kit, different world
        self.assertEqual(r2["record"]["era"], 2)

    def test_two_restarts_all_different(self):
        s = FakeState()
        snaps = []
        for era in (1, 2, 3):
            S.seed(s, SKILLS, lambda w: None)
            snaps.append(snapshot_world(W.load_world_for_test(s)
                                        if hasattr(W, "load_world_for_test")
                                        else S.seed.__wrapped__ if False else None)
                          if False else None)
            U.restart(s, reason="cycle")
        # explicit re-seed chain: era1, era2, era3 must all differ pairwise
        s = FakeState()
        r1 = S.seed(s, SKILLS, lambda w: None); a = snapshot_world(r1["world"])
        U.restart(s, reason="1->2")
        r2 = S.seed(s, SKILLS, lambda w: None); b = snapshot_world(r2["world"])
        U.restart(s, reason="2->3")
        r3 = S.seed(s, SKILLS, lambda w: None); c = snapshot_world(r3["world"])
        self.assertNotEqual(a, b)
        self.assertNotEqual(b, c)
        self.assertNotEqual(a, c)

    def test_species_roster_survives_era_change(self):
        """Canon Eidos IDs are era-independent (shared mythology holds)."""
        s = FakeState()
        r1 = S.seed(s, SKILLS, lambda w: None)
        roster1 = sorted(sp["eidos"] for sp in r1["canon_species"])
        U.restart(s, reason="test")
        r2 = S.seed(s, SKILLS, lambda w: None)
        roster2 = sorted(sp["eidos"] for sp in r2["canon_species"])
        self.assertEqual(roster1, roster2)


if __name__ == "__main__":
    unittest.main()
