"""VIV-8 acceptance: glyphs and names are deterministic, distinct, spec-stable."""
import sys, unittest
sys.path.insert(0, '.')

try:
    from . import identity as I, world as W
except ImportError:
    import identity as I, world as W

G1 = {"forage": 1.61, "aggression": 0.18, "metabolism_mult": 0.805,
      "sense": 2.328, "mutate": 1.903, "hue": 0.42}
G2 = dict(G1, forage=0.62, hue=0.71)
G3 = dict(G1, sense=2.87, metabolism_mult=1.14, hue=0.13)


class GlyphSpec(unittest.TestCase):
    def test_shape_and_shades(self):
        cells = I.glyph_cells(G1)
        self.assertEqual(len(cells), 7)
        for row in cells:
            self.assertEqual(len(row), 7)
            for v in row:
                self.assertIn(v, (0, 1, 2, 3))

    def test_mirror_symmetry(self):
        cells = I.glyph_cells(G1)
        for row in cells:
            self.assertEqual(row, row[::-1])

    def test_deterministic(self):
        self.assertEqual(I.glyph_cells(G1), I.glyph_cells(G1))
        self.assertEqual(I.glyph_ascii(G1), I.glyph_ascii(G1))

    def test_sensitivity(self):
        """A meaningfully different genome grows a different face."""
        faces = {tuple(tuple(r) for r in I.glyph_cells(g)) for g in (G1, G2, G3)}
        self.assertEqual(len(faces), 3)

    def test_robust_to_tiny_float_noise(self):
        """Rounding to 4 decimals: save/load float jitter must not change the face."""
        g = dict(G1, forage=G1["forage"] + 1e-9)
        self.assertEqual(I.glyph_cells(g), I.glyph_cells(G1))


class Names(unittest.TestCase):
    def test_binomial_structure(self):
        genus, epithet, common = I.name_of(G1)
        self.assertIn(genus, set(I._GENUS.values()))
        self.assertIn(epithet, I._EPITHETS)
        self.assertTrue(common.startswith("the "))

    def test_dominant_trait_drives_genus(self):
        # pure-trait probes: push one trait to the top of its range
        g_sense = dict(G1, sense=3.0, mutate=0.5, forage=0.2, hue=0.1)
        self.assertEqual(I.name_of(g_sense)[0], "Oculata")
        g_mut = dict(G1, sense=1.0, mutate=1.5, forage=0.2, hue=0.1)
        self.assertEqual(I.name_of(g_mut)[0], "Mutabilis")
        g_for = dict(G1, sense=1.0, mutate=0.5, forage=2.5, hue=0.1)
        self.assertEqual(I.name_of(g_for)[0], "Foragia")

    def test_stable(self):
        self.assertEqual(I.name_of(G1), I.name_of(dict(G1)))

    def test_epithet_varies_when_genus_shared(self):
        genera = {}
        for i in range(30):
            g = dict(G1, sense=1.0 + i * 0.06, mutate=0.5 + (i % 7) * 0.2,
                     hue=(i * 0.033) % 1.0)
            genus, epithet, _ = I.name_of(g)
            genera.setdefault(genus, set()).add(epithet)
        multi = [v for v in genera.values() if len(v) >= 2]
        self.assertTrue(multi, "epithets should vary within a genus")


class Card(unittest.TestCase):
    def test_card_contains_identity(self):
        card = I.species_card("Eidos_c88c94", G1, I.color_for(G1["hue"]),
                              lineage_count=4, founding_skill="demo-skill")
        self.assertIn("Eidos_c88c94", card)
        self.assertIn("demo-skill", card)
        self.assertIn("living members 4", card)


if __name__ == "__main__":
    unittest.main()
