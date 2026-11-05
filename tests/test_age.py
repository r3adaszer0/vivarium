"""VIV-9 acceptance: age pyramid diagnoses the ecology."""
import sys, unittest
sys.path.insert(0, '.')

try:
    from . import world as W
except ImportError:
    import world as W


def mk(age, energy=5.0, gid=1, lineage="t"):
    return W.Creature(gid=gid, genome={"forage": 1.0, "aggression": 0.5,
                                       "metabolism_mult": 1.0, "sense": 1.5,
                                       "mutate": 1.0, "hue": 0.5},
                      x=0, y=0, energy=energy, age=age, lineage=lineage)


def world_with(creatures):
    w = W.World(w=8, h=8, tick=0, food=[[0.0] * 8 for _ in range(8)],
                creatures=creatures, rng=__import__("random").Random(1))
    return w


class AgePyramid(unittest.TestCase):
    def test_band_boundaries(self):
        # MAX_AGE=900: newborn <90, young <315, adult <630, elder >=630
        w = world_with([mk(0), mk(89), mk(90), mk(314), mk(315), mk(629),
                        mk(630), mk(850)])
        a = W.age_stats(w)
        self.assertEqual(a["newborns"], 2)   # 0, 89
        self.assertEqual(a["young"], 2)      # 90, 314
        self.assertEqual(a["adults"], 2)     # 315, 629
        self.assertEqual(a["elders"], 2)     # 630, 850

    def test_aging_out_verdict(self):
        # all elders, zero newborns -> the pre-crash signature
        w = world_with([mk(800 + i, gid=i + 1) for i in range(5)])
        a = W.age_stats(w)
        self.assertEqual(a["elders"], 5)
        self.assertIn("aging out", a["verdict"])

    def test_healthy_mix_verdict(self):
        w = world_with([mk(5), mk(10), mk(20), mk(100), mk(120)])
        a = W.age_stats(w)
        self.assertEqual(a["verdict"], "healthy mix")

    def test_empty_dish(self):
        a = W.age_stats(world_with([]))
        self.assertEqual(a["verdict"], "the dish is empty")

    def test_stats_includes_ages(self):
        w = world_with([mk(500)])         # 500/900 = 0.56 -> adult
        s = W.stats(w)
        self.assertIn("ages", s)
        self.assertEqual(s["ages"]["adults"], 1)
        self.assertEqual(s["ages"]["oldest"], 500)

    def test_normalized_bands_scale_with_lifespan(self):
        """Bands are fractions of MAX_AGE, not hardcoded ticks."""
        old_max = W.MAX_AGE
        try:
            W.MAX_AGE = 100
            w = world_with([mk(50)])          # 50% of lifespan -> adult
            a = W.age_stats(w)
            self.assertEqual(a["adults"], 1)
        finally:
            W.MAX_AGE = old_max


if __name__ == "__main__":
    unittest.main()
