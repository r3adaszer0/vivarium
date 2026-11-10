"""The arrival beat: a face, a ring, and an honest answer for duplicates."""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import acts          # noqa: E402
import card          # noqa: E402
import portrait      # noqa: E402


class Portrait(unittest.TestCase):
    def test_same_eidos_same_face(self):
        self.assertEqual(portrait.body_plan("Eidos_abc123"),
                         portrait.body_plan("Eidos_abc123"))

    def test_different_species_different_face(self):
        self.assertNotEqual(portrait.body_plan("Eidos_abc123"),
                            portrait.body_plan("Eidos_def456"))

    def test_sprite_is_symmetric_and_square(self):
        grid = portrait.body_plan("Eidos_abc123")
        self.assertEqual({len(r) for r in grid}, {15})
        for row in grid:
            self.assertEqual(row, list(reversed(row)))


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
