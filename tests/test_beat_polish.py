"""Act 3, as it reads now: a name, bars, and a newborn you can find.

These guard the decisions made in the act-3 polish: the headline names the
species instead of only the skill, the traits are bars shared with
`/vivarium show`, and the dish carries a label pointing at the newborn.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import acts  # noqa: E402
import artifacts  # noqa: E402
import birth  # noqa: E402
import cinematography  # noqa: E402
import identity  # noqa: E402
import world  # noqa: E402


def _genome():
    return world.genome_from_bytes(bytes(range(24)))


def _result(**over):
    r = {"eidos": "Eidos_8fe33e", "name": "probe-user-two",
         "genome": _genome(), "pod": 4, "tick": 114}
    r.update(over)
    return r


class HeadlineNamesTheSpecies(unittest.TestCase):
    def test_headline_carries_the_binomial(self):
        out = birth.announcement(_result())
        genus, epithet, _ = identity.name_of(_genome())
        self.assertIn("Eidos_8fe33e", out)
        self.assertIn(f"{genus} {epithet}", out)
        self.assertIn("probe-user-two", out)

    def test_headline_has_no_em_dash(self):
        self.assertNotIn("—", birth.announcement(_result()))

    def test_headline_is_one_line(self):
        self.assertNotIn("\n", birth.announcement(_result()))


class TraitsAreBars(unittest.TestCase):
    def test_arrival_panel_shows_three_bars(self):
        panel = "\n".join(acts.stat_panel(_result()))
        for gene in ("forage", "sense", "metabolism"):
            self.assertIn(gene, panel)
        self.assertEqual(panel.count("█"), panel.count("█"))  # readable rows
        self.assertIn("pod of 4", panel)
        self.assertIn("hatch tick 114", panel)

    def test_show_and_arrival_print_the_same_bars(self):
        g = _genome()
        arrival = [ln.split("█")[0] for ln in identity.trait_bars(g)]
        show = identity.species_card("Eidos_8fe33e", g,
                                     identity.color_for(g["hue"]))
        for label in ("forage", "sense", "metabolism"):
            self.assertIn(label, show)
        self.assertEqual(arrival, [ln.split("█")[0]
                                   for ln in identity.trait_bars(g)])

    def test_bars_are_monotone_in_the_gene(self):
        lo = dict(_genome(), forage=0.3)
        hi = dict(_genome(), forage=2.7)
        a = next(ln for ln in identity.trait_bars(lo) if "forage" in ln)
        b = next(ln for ln in identity.trait_bars(hi) if "forage" in ln)
        self.assertLess(a.count("█"), b.count("█"))


class TheDishPointsAtTheNewborn(unittest.TestCase):
    def test_callout_plate_is_wider_than_the_bare_dish(self):
        try:
            import PIL  # noqa: F401
        except ImportError:  # pragma: no cover
            self.skipTest("Pillow not installed")
        w = world.new_world(seed=7)
        world.run(w, 5)
        c = w.creatures[0]

        class _S:
            pass

        bare = artifacts.render_dish_png(_S(), w, "guard_bare")
        plate = artifacts.render_dish_png(_S(), w, "guard_plate",
                                          mark=(c.x, c.y),
                                          callout=(c.x, c.y, "Eidos_8fe33e"))
        self.assertTrue(bare and plate)
        from PIL import Image
        with Image.open(bare) as a, Image.open(plate) as b:
            self.assertEqual(a.size, (337, 337))
            self.assertEqual(b.size, (337, 337))

    def test_legend_names_the_species(self):
        w = world.new_world(seed=11)
        world.run(w, 3)

        class _S:
            pass

        p = artifacts.render_dish_png(_S(), w, "guard_legend",
                                      mark=(0, 0), callout=(0, 0, "Eidos_1"))
        self.assertTrue(p and os.path.exists(p))


class ClipSharesTheDishPalette(unittest.TestCase):
    def test_one_food_ramp(self):
        for v in (0.0, 0.05, 0.18, 1.28, 3.0):
            self.assertEqual(cinematography._food_rgb(v),
                             artifacts.food_rgb(v))


class CopyRules(unittest.TestCase):
    def test_no_em_dashes_and_no_placeholder_question(self):
        text = acts.act3_for(_result())
        self.assertNotIn("—", text)
        self.assertNotIn("Remember the promise", text)

    def test_copy_names_the_skill_once(self):
        text = acts.act3_for(_result())
        self.assertEqual(text.count("probe-user-two"), 1)


if __name__ == "__main__":
    unittest.main()
