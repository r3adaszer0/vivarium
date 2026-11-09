import unittest


class TestDisplayHue(unittest.TestCase):
    """Species colors must never land in the food palette (green)."""

    def test_no_species_color_is_green(self):
        import colorsys
        from identity import display_hue
        for i in range(200):
            h = i / 200
            out = display_hue(h)
            self.assertFalse(0.15 <= out < 0.50, f"hue {h} -> {out}")

    def test_display_hue_injective_and_deterministic(self):
        from identity import display_hue
        outs = [display_hue(i / 1000) for i in range(1000)]
        self.assertEqual(len(set(outs)), 1000)
        self.assertEqual(outs[0], display_hue(0.0))
        self.assertEqual(outs[500], display_hue(0.5))

    def test_color_for_uses_display_hue(self):
        from identity import color_for, display_hue
        import colorsys
        h = 0.33  # plain green genome
        r, g, b = color_for(h)
        er, eg, eb = colorsys.hls_to_rgb(display_hue(h), 0.58, 0.8)
        self.assertEqual((r, g, b), (int(er * 255), int(eg * 255), int(eb * 255)))
        # and it is NOT green-dominant
        self.assertFalse(g > r and g > b)


if __name__ == "__main__":
    unittest.main()
