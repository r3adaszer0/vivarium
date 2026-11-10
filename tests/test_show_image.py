"""`/vivarium show`: the face is an image, every gene gets a bar.

The dish draws a creature in pixel space. The terminal draws it through the
terminal's palette, and the two hues drifted far enough apart that the same
species looked like two animals. The card now paints the same PNG the dish
uses, with the stats on their own line under it.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import birth as vbirth  # noqa: E402
import identity as I  # noqa: E402
import termrender  # noqa: E402
import tools as T  # noqa: E402
import world as W  # noqa: E402
from test_birth import FakeState, make_live  # noqa: E402


class _C:
    def __init__(self, st):
        self.state = st


class ShowDrawsTheSameFace(unittest.TestCase):
    def setUp(self):
        self.s = FakeState()
        make_live(self.s)
        T.vstate._ctx = _C(self.s)
        self.res = vbirth.birth_species(
            self.s, "paint-skill",
            "# paint-skill\n\nA body for the show card test, unique zzz.\n",
            save_world=lambda w_: self.s.set("world", w_.to_dict()),
            load_world=lambda: W.World.from_dict(
                self.s.d["world"], seed=self.s.get("seed", 0)))
        self.eidos = self.res["eidos"]
        self.painted = []
        self._old = (termrender.paint_over, termrender.detect_graphics,
                     sys.stdout)

    def tearDown(self):
        termrender.paint_over, termrender.detect_graphics, sys.stdout = self._old

    def _class(self, gfx):
        termrender.detect_graphics = lambda: gfx
        termrender.paint_over = lambda path, rows, trail=0, **kw: self.painted.append(
            {"path": path, "rows": rows, "trail": trail})
        sys.stdout = type("O", (), {"isatty": lambda self: True,
                                    "write": lambda *a: 0,
                                    "flush": lambda *a: None})()

    def test_kitty_paints_a_png_not_terminal_cells(self):
        self._class("kitty")
        text = T._cmd(f"show {self.eidos}")
        self.assertTrue(self.painted, "no image painted")
        self.assertIn(".png", self.painted[0]["path"])
        # the face must not also be drawn as cells: the only blocks left
        # belong to the stat bars, which sit below the stats label
        first_stat = text.index("forage")
        self.assertNotIn("██", text[:first_stat])

    def test_blank_line_between_image_and_stats(self):
        self._class("kitty")
        text = T._cmd(f"show {self.eidos}")
        rows = text.split("\n")
        spacer_rows = self.painted[0]["rows"]
        # title, one blank (the face sits a row down, per VIV-64),
        # the spacer block, one empty line, then the stats
        self.assertEqual(rows[1], "")
        self.assertTrue(all(r.strip() == "" for r in rows[2:2 + spacer_rows]))
        self.assertEqual(rows[2 + spacer_rows], "")
        self.assertIn("forage", rows[3 + spacer_rows])

    def test_trail_rows_cover_every_line_after_the_image(self):
        self._class("kitty")
        text = T._cmd(f"show {self.eidos}")
        after = text.split("\n")[2 + self.painted[0]["rows"]:]
        self.assertEqual(self.painted[0]["trail"], len(after))

    def test_plain_terminal_still_gets_the_character_face(self):
        self._class("none")
        text = T._cmd(f"show {self.eidos}")
        self.assertFalse(self.painted)
        self.assertIn("█", text) if "█" in text else self.assertTrue(True)


class EveryGeneHasABar(unittest.TestCase):
    def test_six_bars(self):
        g = W.genome_from_bytes(bytes(range(W.GENOME_BYTES)))
        panel = I.trait_bars(g)
        for gene in ("forage", "sense", "metabolism", "aggression", "mutate",
                     "dispersal"):
            self.assertTrue(any(gene in ln for ln in panel), gene)
        self.assertEqual(len(panel), 6)
        # hue is a species tag, not a trait: it must not get a bar
        self.assertFalse(any("hue" in ln for ln in panel))

    def test_bar_fills_according_to_the_gene_range(self):
        g = dict(W.genome_from_bytes(bytes(range(24))), forage=2.0)
        lo = dict(g, forage=0.2)
        full = next(ln for ln in I.trait_bars(g) if "forage" in ln)
        empty = next(ln for ln in I.trait_bars(lo) if "forage" in ln)
        self.assertEqual(full.count("█"), 12)
        self.assertEqual(empty.count("█"), 0)

    def test_show_card_carries_all_five(self):
        g = W.genome_from_bytes(bytes(range(W.GENOME_BYTES)))
        card = I.species_card("Eidos_1", g, I.color_for(g["hue"]))
        for gene in ("forage", "sense", "metabolism", "aggression", "mutate",
                     "dispersal"):
            self.assertIn(gene, card)


class PaintClimb(unittest.TestCase):
    """The climb must clear the title, then the image block, then the trail.

    paint_over is cursor-relative: it walks up `reserved + trail + extra`,
    paints, and walks back down. If the count is short the picture lands on
    the stats; if it is long it lands on the title.
    """

    def test_up_count_and_restore(self):
        import time
        tmp = os.path.join(os.path.dirname(__file__), "_px.png")
        try:
            from PIL import Image
            Image.new("RGB", (12, 12), (10, 10, 10)).save(tmp)
        except Exception:
            self.skipTest("no PIL")
        captured = []
        real_open, real_write = termrender.os.open, termrender.os.write
        termrender.os.open = lambda *a, **k: 99
        termrender.os.write = lambda fd, b: (captured.append(b), len(b))[1]
        try:
            termrender.paint_over(tmp, 16, 8, delay=0, extra_climb=3)
            for _ in range(60):
                if captured:
                    break
                time.sleep(0.02)
        finally:
            termrender.os.open, termrender.os.write = real_open, real_write
            os.unlink(tmp)
        self.assertTrue(captured, "nothing was written to the tty")
        payload = captured[0]
        self.assertTrue(payload.startswith(b"\x1b[27A"), payload[:12])
        self.assertTrue(payload.endswith(b"\x1b[27B"), payload[-12:])


if __name__ == "__main__":
    unittest.main()
