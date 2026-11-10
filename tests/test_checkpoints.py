"""Numbered checkpoints: a moment can be replayed, not just photographed."""

import pathlib
import sys
import tempfile
import types
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import artifacts as A      # noqa: E402
import state as vstate     # noqa: E402
import world as W          # noqa: E402


class FakeState:
    def __init__(self, data_dir):
        self.data_dir = pathlib.Path(data_dir)
        self.d = {}

    def get(self, k, default=None):
        return self.d.get(k, default)

    def set(self, k, v):
        self.d[k] = v


def bind(data_dir):
    s = FakeState(data_dir)
    vstate._ctx = types.SimpleNamespace(state=s)
    return s


class CheckpointWrite(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = bind(self.tmp.name)
        self.w = W.new_world(seed=7) if hasattr(W, "new_world") else None

    def tearDown(self):
        self.tmp.cleanup()

    def test_offbeat_tick_writes_nothing(self):
        if self.w is None:
            self.skipTest("no world factory")
        self.w.tick = 5
        self.assertIsNone(vstate.save_checkpoint(self.w))

    def test_beat_tick_writes_its_number(self):
        if self.w is None:
            self.skipTest("no world factory")
        self.w.tick = vstate.CHECKPOINT_EVERY
        path = vstate.save_checkpoint(self.w)
        self.assertIsNotNone(path)
        self.assertTrue(str(path).endswith(
            f"tick_{vstate.CHECKPOINT_EVERY:05d}.json"))

    def test_round_trip_restores_the_same_world(self):
        if self.w is None:
            self.skipTest("no world factory")
        self.w.tick = vstate.CHECKPOINT_EVERY
        vstate.save_checkpoint(self.w)
        back = vstate.load_checkpoint(vstate.CHECKPOINT_EVERY)
        self.assertIsNotNone(back)
        self.assertEqual(back.tick, self.w.tick)
        self.assertEqual(len(back.creatures), len(self.w.creatures))
        self.assertEqual([round(v, 6) for v in back.food[0]],
                         [round(v, 6) for v in self.w.food[0]])

    def test_list_reports_population(self):
        if self.w is None:
            self.skipTest("no world factory")
        self.w.tick = vstate.CHECKPOINT_EVERY
        vstate.save_checkpoint(self.w)
        rows = vstate.list_checkpoints()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["tick"], vstate.CHECKPOINT_EVERY)
        self.assertEqual(rows[0]["population"], len(self.w.creatures))

    def test_ring_keeps_the_newest_only(self):
        if self.w is None:
            self.skipTest("no world factory")
        for i in range(vstate.CHECKPOINT_KEEP + 3):
            self.w.tick = (i + 1) * vstate.CHECKPOINT_EVERY
            vstate.save_checkpoint(self.w)
        self.assertLessEqual(len(vstate.list_checkpoints()),
                             vstate.CHECKPOINT_KEEP)


class FoodRamp(unittest.TestCase):
    def test_empty_cell_is_soil_not_a_hole(self):
        r, g, b = A.food_rgb(0.0)
        self.assertEqual((r, g, b), A.FOOD_EMPTY)
        self.assertGreater(g, 15, "bare soil must not be background black")

    def test_ramp_rises_with_food(self):
        greens = [A.food_rgb(f)[1] for f in (0.1, 0.5, 1.0, 2.0, 3.0)]
        self.assertEqual(greens, sorted(greens))

    def test_low_food_is_visible(self):
        # 6% of saturation: the shipped linear ramp drew this at g=62,
        # four steps from the background. The gamma floor keeps it read.
        self.assertGreaterEqual(A.food_rgb(0.18)[1], 68)


if __name__ == "__main__":
    unittest.main()
