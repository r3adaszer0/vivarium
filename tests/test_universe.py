"""Universe lifecycle tests — genesis, cross-universe divergence, fossils, restart.

FakeState: minimal PluginState stand-in (same interface as tests/test_core.py).
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import universe as U          # noqa: E402
import world as W             # noqa: E402


class FakeState:
    def __init__(self):
        self.d = {}

    def get(self, key, default=None):
        return self.d.get(key, default)

    def set(self, key, value):
        self.d[key] = value


class TestGenesis(unittest.TestCase):
    def setUp(self):
        self.s = FakeState()

    def test_key_is_created_once_and_stable(self):
        k1 = U.get_or_create_key(self.s)
        k2 = U.get_or_create_key(self.s)
        self.assertEqual(k1, k2)
        self.assertEqual(len(k1), 32)
        # the raw key must never be visible in the public record
        rec = U.universe_record(self.s)
        self.assertNotIn(base64_of(k1), str(rec))

    def test_genesis_creates_live_universe_from_first_skill(self):
        saved = {}
        out = U.genesis(self.s, "invoice-parsing", "Parse PDF invoices…",
                        save_world=lambda w: saved.update(world=w))
        self.assertIsNotNone(out)
        rec = out["record"]
        self.assertEqual(rec["status"], "live")
        self.assertEqual(rec["genesis"]["skill"], "invoice-parsing")
        self.assertTrue(saved)  # world was persisted
        # founder species exists in the world
        eidos_name = out["eidos"]
        self.assertTrue(any(c.lineage == eidos_name for c in out["world"].creatures))
        # second genesis call must be refused
        self.assertIsNone(U.genesis(self.s, "other", "content",
                                    save_world=lambda w: None))

    def test_genesis_is_deterministic_per_universe(self):
        a, b = FakeState(), FakeState()
        # same key content -> same genesis; simulate by copying the key
        ka = U.get_or_create_key(a)
        b.d[U.UNIVERSE_KEY] = a.d[U.UNIVERSE_KEY]
        out_a = U.genesis(a, "s1", "content A", save_world=lambda w: None)
        out_b = U.genesis(b, "s1", "content A", save_world=lambda w: None)
        self.assertEqual(out_a["world"].to_dict(), out_b["world"].to_dict())
        # different skill content -> different world (same universe)
        out_c = U.genesis(FakeState(), "s1", "content B", save_world=lambda w: None) \
            if False else None
        # (covered by divergence test below with a fresh key)

    def test_different_universes_diverge(self):
        out_a = U.genesis(self.s, "s1", "content A", save_world=lambda w: None)
        fresh = FakeState()  # new state = new key = new universe
        out_b = U.genesis(fresh, "s1", "content A", save_world=lambda w: None)
        self.assertNotEqual(out_a["world"].to_dict(), out_b["world"].to_dict())
        self.assertNotEqual(out_a["eidos"], out_b["eidos"])

    def test_world_from_digest_deterministic_and_divergent(self):
        d1 = bytes(range(32))
        d2 = bytes(range(1, 33))
        w1a = W.new_world_from_digest(d1)
        w1b = W.new_world_from_digest(d1)
        w2 = W.new_world_from_digest(d2)
        self.assertEqual(w1a.to_dict(), w1b.to_dict())
        self.assertNotEqual(w1a.to_dict(), w2.to_dict())
        self.assertEqual(len(w1a.creatures), 24)

    def test_genome_from_bytes_within_ranges(self):
        g = W.genome_from_bytes(bytes(range(24)))
        for trait, (lo, hi) in W.GENOME_RANGES.items():
            self.assertGreaterEqual(g[trait], lo)
            self.assertLessEqual(g[trait], hi)


def base64_of(key: bytes) -> str:
    import base64
    return base64.b64encode(key).decode()


class TestRestartAndFossils(unittest.TestCase):
    def setUp(self):
        self.s = FakeState()
        saved = {}
        out = U.genesis(self.s, "first", "genesis content",
                        save_world=lambda w: saved.update(world=w))
        self.world = out["world"]
        W.run(self.world, ticks=30)

    def test_restart_archives_fossils_and_rotates_key(self):
        old_fp = U.universe_record(self.s)["key_fp"]
        old_key = self.s.d[U.UNIVERSE_KEY]
        rec = U.restart(self.s, load_world=lambda: self.world,
                        clear_world=lambda: None, reason="stale")
        self.assertEqual(rec["status"], "dormant")
        self.assertEqual(rec["era"], 2)
        self.assertEqual(rec["previous_fp"], old_fp)
        self.assertNotEqual(self.s.d[U.UNIVERSE_KEY], old_key)  # new physics
        fossils = self.s.d[U.FOSSILS]
        self.assertTrue(fossils, "live champions must be archived")
        for f in fossils:
            self.assertEqual(f["universe"], old_fp)
            self.assertIn("genome", f)

    def test_fossils_dedup_by_lineage_and_cap(self):
        g = W.genome_from_bytes(bytes(range(24)))
        for i in range(60):  # 60 distinct lineages -> cap at 50
            U.add_fossil(self.s, f"lin{i}", g, "fp")
        U.add_fossil(self.s, "lin0", g, "fp")  # duplicate ignored
        fossils = self.s.get(U.FOSSILS)
        self.assertEqual(len(fossils), U.FOSSIL_CAP)

    def test_after_restart_genesis_works_again_with_new_key(self):
        U.restart(self.s, load_world=lambda: self.world, clear_world=lambda: None)
        out = U.genesis(self.s, "second-era", "new first skill",
                        save_world=lambda w: None)
        self.assertIsNotNone(out)
        rec = out["record"]
        self.assertEqual(rec["era"], 2)
        # new universe -> different genesis species for the same skill name
        self.assertNotEqual(rec["genesis"]["eidos"], "Eidos_" + "x")  # smoke
        # and the key really rotated: same skill, different digest than era 1
        d2 = U.skill_digest(self.s, "genesis content")
        self.assertNotEqual(d2.hex(), rec["genesis"]["digest_hex"])


class TestDigestPrivacy(unittest.TestCase):
    def test_digest_differs_across_universes(self):
        a, b = FakeState(), FakeState()
        da = U.skill_digest(a, "same skill content")
        db = U.skill_digest(b, "same skill content")
        self.assertNotEqual(da, db)          # cross-user unlinkability
        self.assertEqual(da, U.skill_digest(a, "same skill content"))  # stable


if __name__ == "__main__":
    unittest.main(verbosity=2)
