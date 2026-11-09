"""VIV-31: the fledge window — newborn pods can establish at the cap.

Three measured mechanisms, all deterministic (state + hash only):
1. contest grace: a fledgling never takes a cell an adult holds;
2. displacement: a fledgling sharing a cell with an adult steps aside
   to the richest adjacent adult-free cell;
3. reserved burst: a fledgling PARENT may reproduce into
   POP_CAP + FLEDGE_BURST (adults stay capped at POP_CAP) — the
   headroom belongs to the pod, incumbents cannot consume it.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import world as W  # noqa: E402


def _plateau(seed: int = 99, ticks: int = 4000) -> W.World:
    w = W.new_world(seed=seed)
    g0 = W.genome_from_bytes(bytes(range(24)))
    for i in range(60):
        w.creatures.append(W.Creature(
            gid=i + 1, genome=dict(g0), x=(i * 7) % w.w,
            y=(i * 13) % w.h, energy=5.0, lineage="jade"))
    w.next_gid = 61
    for _ in range(ticks):
        W.tick_world(w, 0.0)
    return w


class TestFledge(unittest.TestCase):
    def test_grace_registry_serializes(self):
        w = W.new_world(seed=1)
        w.fledge["Eidos_abc"] = 5
        w2 = W.World.from_dict(w.to_dict(), seed=1)
        self.assertEqual(w2.fledge, {"Eidos_abc": 5})

    def test_is_fledgling_by_age_and_registry(self):
        w = W.new_world(seed=1)
        w.fledge["Eidos_abc"] = 0
        c = W.Creature(gid=1, genome=W.genome_from_bytes(bytes(range(24))),
                       x=1, y=1, energy=5.0, lineage="Eidos_abc")
        self.assertTrue(W._is_fledgling(w, c))
        c.age = W.FLEDGE_AGE          # grace expired
        self.assertFalse(W._is_fledgling(w, c))
        c2 = W.Creature(gid=2, genome=W.genome_from_bytes(bytes(range(24))),
                        x=2, y=2, energy=5.0, lineage="other")
        self.assertFalse(W._is_fledgling(w, c2))   # not in registry
        w.fledge.clear()
        self.assertFalse(W._is_fledgling(w, c))    # registry gone

    def test_fledge_displacement_steps_aside(self):
        w = W.new_world(seed=3)
        w.fledge["Eidos_kid"] = 0
        adult = W.Creature(gid=1, genome=dict(W.genome_from_bytes(bytes(range(24)))),
                           x=10, y=10, energy=50.0, lineage="jade")
        adult.age = 200
        kid = W.Creature(gid=2, genome=dict(adult.genome),
                         x=10, y=10, energy=5.0, lineage="Eidos_kid")
        w.creatures = [adult, kid]
        w.food[10][10] = 0.0
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx or dy:
                    w.food[(10 + dy) % w.h][(10 + dx) % w.w] = 1.0
        W.tick_world(w, 0.0)
        self.assertNotEqual((kid.x, kid.y), (adult.x, adult.y),
                            "fledgling must not keep sharing an adult cell")

    def test_reserved_burst_lets_pod_reproduce_at_cap(self):
        w = _plateau()
        d = bytes(range(24))
        genome = W.genome_from_bytes(d)
        # land the pod at a high-food, empty cell (plateau has some)
        cell = None
        for y in range(w.h):
            for x in range(w.w):
                if not any(c.x == x and c.y == y for c in w.creatures) \
                        and w.food[y][x] > 1.0:
                    cell = (x, y)
                    break
            if cell:
                break
        self.assertIsNotNone(cell, "plateau must have an open fertile cell")
        x0, y0 = cell
        for i in range(4):
            w.creatures.append(W.Creature(
                gid=w.next_gid + i, genome=dict(genome),
                x=x0, y=y0, energy=8.0, lineage="Eidos_probe"))
        w.next_gid += 4
        w.fledge["Eidos_probe"] = w.tick
        n0 = len(w.creatures)
        peak = 0
        for _ in range(600):
            W.tick_world(w, 0.0)
            peak = max(peak, sum(1 for c in w.creatures
                                 if c.lineage == "Eidos_probe" and c.alive()))
        self.assertGreater(peak, 4,
                           "pod with reserved burst must grow past its landing size")
        self.assertLessEqual(len(w.creatures), W.POP_CAP + W.FLEDGE_BURST,
                             "burst headroom is bounded")

    def test_population_never_exceeds_cap_without_fledglings(self):
        w = _plateau(ticks=4000)
        # no fledge registry: adults may not use the burst, so the dish
        # stays at/below POP_CAP even while births continue
        for _ in range(200):
            W.tick_world(w, 0.0)
            self.assertLessEqual(len(w.creatures), W.POP_CAP,
                                 "adults must not reproduce past POP_CAP")

    def test_prune_keeps_registry_bounded(self):
        w = W.new_world(seed=7)
        w.fledge = {f"Eidos_{i:02d}": i for i in range(20)}
        w.tick = 1000
        W._prune_fledge(w)
        self.assertTrue(all(w.tick - t < W.FLEDGE_AGE * 4
                            for t in w.fledge.values()))


if __name__ == "__main__":
    unittest.main()
