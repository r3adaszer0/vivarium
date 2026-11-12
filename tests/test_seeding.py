"""Discovery + seeding tests: canon==canon across universes, private!=private."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discovery as vdisc      # noqa: E402
import seeding as S            # noqa: E402
import universe as U           # noqa: E402
import world as W              # noqa: E402
from tests.test_universe import FakeState  # noqa: E402


class TestDiscovery(unittest.TestCase):
    @unittest.skipUnless(vdisc.discover(),
                         "no installed skills on this machine (CI runner)")
    def test_classifies_bundled_vs_private(self):
        # the real machine: bundled catalog exists; user dir may have extras
        skills = vdisc.discover()
        self.assertTrue(skills, "expected at least one installed skill")
        kinds = {sk["kind"] for sk in skills}
        self.assertTrue(kinds & {"canon"}, "bundled skills must classify as canon")
        # every non-canon skill must be either private or private-modified
        for sk in skills:
            if not sk["is_canon"]:
                self.assertIn(sk["kind"], {"private", "private-modified"})

    def test_modified_bundled_skill_is_not_canon(self):
        # synthetic: tamper a canon skill -> must reclassify
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "skills" / "fake-bundled"
            root.mkdir(parents=True)
            (root / "SKILL.md").write_text("tampered")
            skills = vdisc.discover(skills_dir=Path(td) / "skills")
            self.assertEqual(len(skills), 1)
            self.assertFalse(skills[0]["is_canon"])
            self.assertEqual(skills[0]["kind"], "private")


class TestSeeding(unittest.TestCase):
    def _skills(self):
        canon = {"name": "stock-a", "path": "/x", "is_canon": True, "kind": "canon",
                 "bytes": b"identical stock bytes"}
        priv = {"name": "my-secret-skill", "path": "/y", "is_canon": False,
                "kind": "private", "bytes": b"private skill content"}
        return [canon, priv]

    def test_seed_creates_live_universe_with_pods(self):
        s = FakeState()
        saved = {}
        out = S.seed(s, self._skills(), save_world=lambda w: saved.update(world=w))
        self.assertIsNotNone(out)
        w = out["world"]
        # 2 species x 4 pod + 24 natives = 32
        self.assertEqual(len(w.creatures), 32)
        lineages = {c.lineage for c in w.creatures}
        self.assertTrue(any(l.startswith("Eidos_") for l in lineages))
        self.assertEqual(out["record"]["status"], "live")

    def test_canon_same_across_universes_private_differs(self):
        s1, s2 = FakeState(), FakeState()
        out1 = S.seed(s1, self._skills(), save_world=lambda w: None)
        out2 = S.seed(s2, self._skills(), save_world=lambda w: None)
        canon1 = {sp["eidos"] for sp in out1["canon_species"]}
        canon2 = {sp["eidos"] for sp in out2["canon_species"]}
        priv1 = {sp["eidos"] for sp in out1["private_species"]}
        priv2 = {sp["eidos"] for sp in out2["private_species"]}
        self.assertEqual(canon1, canon2, "same stock skills -> same canon species")
        self.assertNotEqual(priv1, priv2, "same private skills -> different species")
        # and the genomes back it up
        g1 = next(c for c in out1["world"].creatures
                  if c.lineage in priv1).genome
        g2 = next(c for c in out2["world"].creatures
                  if c.lineage in priv2).genome
        self.assertNotEqual(g1, g2)

    def test_genome_sanity_of_seeded_species(self):
        s = FakeState()
        out = S.seed(s, self._skills(), save_world=lambda w: None)
        for c in out["world"].creatures:
            if c.lineage.startswith("Eidos_"):
                for trait, (lo, hi) in W.GENOME_RANGES.items():
                    self.assertGreaterEqual(c.genome[trait], lo)
                    self.assertLessEqual(c.genome[trait], hi)

    def test_seed_refused_when_live(self):
        s = FakeState()
        S.seed(s, self._skills(), save_world=lambda w: None)
        self.assertIsNone(S.seed(s, self._skills(), save_world=lambda w: None))

    def test_onboard_message_mentions_both_tiers(self):
        s = FakeState()
        out = S.seed(s, self._skills(), save_world=lambda w: None)
        msg = S.onboard_message(out)
        self.assertIn("canon", msg)
        self.assertIn("private", msg)
        self.assertIn("die-off", msg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
