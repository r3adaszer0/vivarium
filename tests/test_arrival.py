"""The arrival beat: a face, a ring, and an honest answer for duplicates."""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import acts          # noqa: E402
import card          # noqa: E402
import portrait      # noqa: E402


class Portrait(unittest.TestCase):
    """One genome, one face: the portrait is the glyph, only bigger."""

    def setUp(self):
        import world as W
        self.g = W.genome_from_bytes(bytes(range(24)))
        self.other = W.genome_from_bytes(bytes(range(1, 25)))

    def test_same_genome_same_face(self):
        self.assertEqual(portrait.sprite_lines(genome=self.g),
                         portrait.sprite_lines(genome=self.g))

    def test_different_genome_different_face(self):
        self.assertNotEqual(portrait.sprite_lines(genome=self.g),
                            portrait.sprite_lines(genome=self.other))

    def test_portrait_is_the_show_glyph_widened(self):
        import identity as I
        cells = I.glyph_cells(self.g)
        lines = portrait.sprite_lines(genome=self.g, scale=3)
        self.assertEqual(len(lines), len(cells))
        for row, line in zip(cells, lines):
            plain = line.split("m", 1)[1].rsplit("\x1b", 1)[0]
            self.assertEqual(len(plain), 15)
            for i, v in enumerate(row):
                block = plain[i * 3:(i + 1) * 3]
                self.assertEqual(len(set(block)), 1)
                self.assertEqual(block[0] == " ", v == 0)

    def test_missing_genome_still_gives_a_stable_face(self):
        a = portrait.sprite_lines(eidos="Eidos_abc123")
        b = portrait.sprite_lines(eidos="Eidos_abc123")
        self.assertEqual(a, b)
        self.assertTrue(any("█" in ln for ln in a))


class ArtInTheCard(unittest.TestCase):
    def _render(self, cols):
        body = ("\n\nNew species Eidos_abc123: hatched from your 'x' skill."
                + acts.DISH_MARKER + acts.act3_for({"eidos": "Eidos_abc123",
                                                    "name": "x", "pod": 4}))
        return card.render(body, cols, acts.DISH_MARKER,
                           live={"tick": 3, "alive": 10, "lineages": 2},
                           dish_rows=23, dish=True, dish_cols=39)

    def test_sentinel_never_reaches_the_screen(self):
        for cols in (72, 120):
            text = self._render(cols)["text"]
            self.assertNotIn("<<ART", text)
            self.assertNotIn("</ART>>", text)

    def test_portrait_sits_beside_the_dish(self):
        text = card.plain(self._render(120)["text"])
        art_rows = [ln for ln in text.split("\n") if "█" in ln]
        self.assertTrue(art_rows, "no portrait drawn")
        body = [ln for ln in text.split("\n")
                if "Remember the promise" in ln]
        self.assertTrue(body)
        # the face starts where the copy starts: same left column
        self.assertGreaterEqual(art_rows[0].index("█"),
                                body[0].index("Remember") - 2)

    def test_narrow_terminal_keeps_the_portrait(self):
        text = card.plain(self._render(72)["text"])
        self.assertTrue(any("█" in ln for ln in text.split("\n")))


class StripArt(unittest.TestCase):
    def test_chat_relay_has_no_block_art(self):
        t = acts.act3_for({"eidos": "Eidos_abc123", "name": "x", "pod": 4})
        out = acts.strip_art(t)
        self.assertNotIn("█", out)
        self.assertIn("Remember the promise", out)


if __name__ == "__main__":
    unittest.main()


class LadderSurvivesAFailedRender(unittest.TestCase):
    """A crash while building an act must not burn the act."""

    def setUp(self):
        import acts as A
        self.A = A
        self.s = _Dict()

    def test_failed_act3_leaves_the_counter_untouched(self):
        import acts as A
        real = A.act3_for
        g = _genome()
        res = {"eidos": "Eidos_aaa111", "name": "probe", "pod": 4,
               "tick": 12, "genome": g}

        def boom(_r):
            raise RuntimeError("art path exploded")

        A.act3_for = boom
        try:
            with self.assertRaises(RuntimeError):
                A.birth_narration(self.s, "BASE", res, is_big_bang=False)
        finally:
            A.act3_for = real
        self.assertNotIn("first_hermi", self.s.get("acts", {}))
        self.assertEqual(self.s.get("acts", {}).get("_births_since_bang", 0), 0)

    def test_next_birth_still_gets_act3(self):
        import acts as A
        res = {"eidos": "Eidos_bbb222", "name": "probe", "pod": 3,
               "tick": 20, "genome": _genome()}
        text = A.birth_narration(self.s, "BASE", res, is_big_bang=False)
        self.assertIn("Remember the promise", text)


class _Dict:
    def __init__(self):
        self.d = {}

    def get(self, k, default=None):
        return self.d.get(k, default)

    def set(self, k, v):
        self.d[k] = v


def _genome():
    import world as W
    return W.genome_from_bytes(bytes(range(24)))
