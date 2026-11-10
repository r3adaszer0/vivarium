"""The genome contract: six evolvable genes, one species tag, hard ranges.

- `hue` is a TAG, not a trait: derived from the lineage id, inherited
  exactly, never jittered. One lineage is one colour, by construction.
- `dispersal` is a real gene: it decides whether a creature leaves a
  crowded cell, and it costs energy to use.
- Every gene is clamped to its declared range. Mutation used to have only a
  floor, so hue had drifted to 2.08 against a 0..1 contract.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import birth as vbirth  # noqa: E402
import birth  # noqa: E402
import state as vstate  # noqa: E402
import world as W  # noqa: E402
from collections import Counter  # noqa: E402


class GenomeShape(unittest.TestCase):
    def test_seven_keys_six_of_them_evolvable(self):
        g = W.genome_from_bytes(bytes(range(W.GENOME_BYTES)))
        self.assertEqual(set(g), set(W.GENOME_KEYS))
        self.assertEqual(len(g), 7)
        self.assertEqual(W.GENOME_BYTES, 28)
        self.assertIn("hue", W.FIXED_GENES)
        self.assertNotIn("dispersal", W.FIXED_GENES)

    def test_short_input_pads_to_the_floor(self):
        g = W.genome_from_bytes(bytes(range(24)))       # pre-dispersal genome
        self.assertEqual(g["dispersal"], 0.0)          # floor = the old dish
        self.assertAlmostEqual(g["hue"], 0.08, places=2)

    def test_every_gene_stays_inside_its_range(self):
        g = {k: 99.0 for k in W.GENOME_KEYS}
        for k in W.GENOME_KEYS:
            self.assertLessEqual(W.clamp_gene(k, g[k]), W.GENOME_RANGES[k][1])
        g2 = {k: -99.0 for k in W.GENOME_KEYS}
        for k in W.GENOME_KEYS:
            self.assertGreaterEqual(W.clamp_gene(k, g2[k]), W.GENOME_RANGES[k][0])


class HueIsATag(unittest.TestCase):
    def test_hue_comes_from_the_id(self):
        self.assertEqual(W.lineage_hue("Eidos_15d6f36b"),
                         W.lineage_hue("Eidos_15d6f36b"))
        self.assertNotEqual(W.lineage_hue("Eidos_15d6f36b"),
                            W.lineage_hue("Eidos_deadbeef"))

    def test_one_lineage_one_colour_after_two_hundred_ticks(self):
        w = W.new_world(seed=11)
        for _ in range(200):
            W.tick_world(w, 0.0)
        hues = {}
        for c in w.creatures:
            if not c.alive():
                continue
            hues.setdefault(c.lineage, set()).add(round(c.genome["hue"], 6))
        self.assertTrue(hues)
        for lineage, seen in hues.items():
            self.assertEqual(len(seen), 1, f"{lineage} drifted to {seen}")

    def test_hue_is_not_jittered_by_reproduction(self):
        w = W.new_world(seed=3)
        for c in w.creatures:
            c.energy = 50.0
            c.age = 200
        parents = {c.gid: c.genome["hue"] for c in w.creatures}
        for _ in range(30):
            W.tick_world(w, 0.0)
        for c in w.creatures:
            if c.lineage in {"amber", "ember", "jade", "violet"}:
                continue
            parent_hues = set(parents.values())
            self.assertIn(round(c.genome["hue"], 6),
                          {round(h, 6) for h in parent_hues})


class DispersalIsAGene(unittest.TestCase):
    def _crowded_world(self, dispersal: float):
        w = W.new_world(seed=5)
        g = W.genome_from_bytes(bytes(range(W.GENOME_BYTES)))
        g["dispersal"] = dispersal
        g["sense"] = 1.0
        ready = []
        for i in range(4):
            c = W.Creature(gid=w.next_gid + i, genome=dict(g), x=12, y=12,
                           energy=20.0, lineage="Eidos_probe")
            ready.append(c)
        w.next_gid += 4
        w.creatures = ready
        w.fledge = {}
        # Uniform food around the cell, so nothing is gained by walking:
        # the only reason to move is that four creatures are sharing one
        # meal. That isolates the gene from the sense-driven movement.
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                w.food[(12 + dy) % w.h][(12 + dx) % w.w] = 1.2
        return w

    def test_a_disperser_leaves_a_crowded_cell(self):
        w = self._crowded_world(1.0)
        W.tick_world(w, 0.0)
        moved = [c for c in w.creatures if (c.x, c.y) != (12, 12)]
        self.assertTrue(moved, "a crowded disperser must step aside")

    def test_zero_dispersal_keeps_the_old_dish(self):
        w = self._crowded_world(0.0)
        W.tick_world(w, 0.0)
        self.assertTrue(all((c.x, c.y) == (12, 12) for c in w.creatures))

    def test_dispersal_is_polymorphic_not_fixed(self):
        w = W.new_world(seed=7)
        for _ in range(200):
            W.tick_world(w, 0.0)
        vals = [c.genome["dispersal"] for c in w.creatures if c.alive()]
        self.assertTrue(vals)
        self.assertLess(sum(vals) / len(vals), 0.95, "the gene fixed at max")
        self.assertGreater(max(vals), 0.0, "the gene never appeared")


class OldCodesStillDecode(unittest.TestCase):
    def test_code_without_dispersal_decodes_with_a_floor(self):
        old = {"forage": 1.0, "aggression": 0.5, "metabolism_mult": 1.0,
               "sense": 2.0, "mutate": 1.0, "hue": 0.4}
        code = "VIV1" + base64.urlsafe_b64encode(
            json.dumps(old).encode()).decode().rstrip("=")
        got = vstate.decode_genome(code)
        self.assertIsNotNone(got)
        self.assertEqual(got["dispersal"], 0.0)
        self.assertEqual(got["forage"], 1.0)


if __name__ == "__main__":
    unittest.main()


class ANameIsGivenOnce(unittest.TestCase):
    def test_stored_name_beats_a_recomputed_one(self):
        import birth

        g = W.genome_from_bytes(bytes(range(W.GENOME_BYTES)))
        res = {"eidos": "Eidos_0badc0de", "name": "demo", "genome": g,
               "species": "Oculata robusta", "common": "the watcher"}
        line = birth.announcement(res)
        self.assertIn("Oculata robusta", line)
        self.assertNotIn(birth._name_species(g)[0], line)

    def test_a_new_gene_does_not_rename_the_roster(self):
        g = W.genome_from_bytes(bytes(range(W.GENOME_BYTES)))
        before = birth._name_species(g)[0]
        g2 = dict(g)
        g2["dispersal"] = 0.93          # as if a later gene changed the profile
        # `name_of` reads genes that did not exist when this species was
        # named, so its verdict can drift; the record is what wins.
        res = {"eidos": "Eidos_0badc0de", "genome": g2, "name": "demo",
               "species": before}
        self.assertIn(before, birth.announcement(res))
