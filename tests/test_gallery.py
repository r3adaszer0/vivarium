"""VIV-89: the Hermi Gallery serve page.

The page is a naturalist's ledger built from REAL plugin state. These
tests pin the promises that matter:
- it renders every birth as a certificate with the deterministic
  identity (same name_of / glyph spec as the terminal cards);
- closed universes (fossil keys) keep their own shelves;
- the page is self-contained: no external URLs, no CDN, no fonts;
- the SGR dish map parses to a pure grid (no escapes leak to the page);
- serve falls back to the flat page when the gallery build fails.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gallery as vgal          # noqa: E402
import identity as vid          # noqa: E402
import termrender as T          # noqa: E402


def _state(**over):
    g = {"forage": 1.883, "aggression": 0.487, "metabolism_mult": 1.163,
         "sense": 2.605, "mutate": 1.119, "dispersal": 0.79, "hue": 0.04}
    return {
        "births": {
            "airtable": {"eidos": "Eidos_ef543f71", "day": "2026-11-11",
                         "era": 20, "genome": g},
            "arxiv": {"eidos": "Eidos_c2df1e99", "day": "2026-11-11",
                      "era": 20, "genome": dict(g, hue=0.39)},
        },
        "fossils": [
            {"lineage": "Eidos_ef543f71", "genome": g, "universe": "124f0d54",
             "day": "2026-11-10"},
            {"lineage": "Eidos_8fd78ab1", "genome": dict(g, hue=0.6),
             "universe": "124f0d54", "day": "2026-11-10"},
        ],
        "curve": [{"tick": t * 10, "population": (t * 13) % 90, "born": t}
                  for t in range(1, 40)],
        "universe": {"era": 20, "status": "live", "key_fp": "2e987e96",
                     "genesis": {"skill": "seed:42+48", "day": "2026-11-11"}},
        **over,
    }


class _St:
    """Minimal stand-in for the plugin state handle."""

    def __init__(self, data):
        self._d = data

    def get(self, k, d=None):
        return self._d.get(k, d)


RICH = ("\x1b[38;2;233;62;175m█\x1b[38;2;97;26;73m▓\x1b[0m░ \n"
        "\x1b[38;2;60;206;133m██\x1b[0m░░")


class TestDishGrid(unittest.TestCase):
    def test_sgr_map_parses_to_pure_hex_grid(self):
        rows = vgal._grid_json(RICH).split("|")
        self.assertEqual(len(rows), 2)
        cells = rows[0].split(",")
        # █ = full-opacity creature color; ▓ = dimmed; ░/space = lattice
        self.assertEqual(cells[0], "e93eaf f".replace(" ", ""))
        self.assertEqual(cells[1], "611a49b")
        self.assertEqual(len(cells[3]), 7)          # lattice cell, hex+tier
        self.assertNotIn("\x1b", vgal._grid_json(RICH))

    def test_empty_map_gives_empty_grid(self):
        self.assertEqual(vgal._grid_json(""), "")


class TestFacesAndNames(unittest.TestCase):
    def test_certificate_uses_the_identity_spec(self):
        html = vgal.build_page("/nonexistent", RICH, st=_St(_state()))
        genus, epithet, _ = vid.name_of(_state()["births"]["airtable"]["genome"])
        self.assertIn(f"{genus} {epithet}", html)
        self.assertIn("Eidos_ef543f71", html)
        self.assertIn("from skill “airtable”", html)

    def test_birth_matching_a_fossil_lineage_shows_extinct(self):
        html = vgal.build_page("/nonexistent", RICH, st=_St(_state()))
        # ef543f71 IS in the fossil record -> gone; arxiv is not -> alive
        gone = 'class="st gone"'
        alive = 'class="st alive"'
        self.assertIn(gone, html)
        self.assertIn(alive, html)
        self.assertLess(html.index(gone), html.index(alive))

    def test_faces_are_inline_svg_from_glyph_cells(self):
        html = vgal.build_page("/nonexistent", RICH, st=_St(_state()))
        self.assertIn('viewBox="-0.02 -0.02 7.04 7.04"', html)
        self.assertIn("shape-rendering", html)
        self.assertNotIn("<img", html.split("Appendix")[0].split("snaprow")[0])


class TestChaptersAndPulse(unittest.TestCase):
    def test_current_universe_is_a_chapter_and_is_current(self):
        html = vgal.build_page("/nonexistent", RICH, st=_St(_state()))
        self.assertIn('id="u2e987e96"', html)
        self.assertIn("the living era", html)
        self.assertIn("Era 20", html)

    def test_every_fossil_universe_keeps_its_shelf(self):
        html = vgal.build_page("/nonexistent", RICH, st=_St(_state()))
        self.assertIn('id="u124f0d54"', html)
        self.assertIn("A closed universe", html)
        self.assertIn("Eidos_8fd78ab1", html)

    def test_pulse_bands_exist_and_curve_is_real_path(self):
        html = vgal.build_page("/nonexistent", RICH, st=_St(_state()))
        self.assertIn('class="band cur"', html)
        self.assertIn("population", html)
        self.assertIn("<path d=\"M", html)

    def test_no_curve_means_no_fake_curve(self):
        html = vgal.build_page("/nonexistent", RICH, st=_St(_state(curve=[])))
        self.assertNotIn('class="curve"', html.replace('class="curve">', ""))


class TestSelfContainment(unittest.TestCase):
    def test_no_external_urls_or_cdns(self):
        html = vgal.build_page("/nonexistent", RICH, st=_St(_state()))
        for bad in ("https://", "cdn.", "fonts.googleapis", "unpkg", "jsdelivr"):
            self.assertNotIn(bad, html)

    def test_privacy_promises_are_in_the_page(self):
        html = vgal.build_page("/nonexistent", RICH, st=_St(_state()))
        self.assertIn("127.0.0.1 only", html)
        self.assertIn("never leaves this machine", html)
        self.assertIn("deterministic by seed", html)


class TestServeGalleryHtmlOverride(unittest.TestCase):
    def test_serve_gallery_writes_the_given_page(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "a.png"), "wb").write(
                b"\x89PNG\r\n\x1a\n" + b"0" * 20)
            page = "<html><body>the hermi gallery</body></html>"
            res = T.serve_gallery(tmp, dish_map="X", open_browser=False,
                                  html=page)
            self.assertNotIn("error", res)
            written = open(os.path.join(tmp, "index.html")).read()
            self.assertIn("the hermi gallery", written)

    def test_flat_page_still_default_without_html(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "a.png"), "wb").write(
                b"\x89PNG\r\n\x1a\n" + b"0" * 20)
            res = T.serve_gallery(tmp, dish_map="X", open_browser=False)
            self.assertNotIn("error", res)
            written = open(os.path.join(tmp, "index.html")).read()
            self.assertIn("card", written)


class TestFallback(unittest.TestCase):
    def test_broken_state_still_builds_a_page(self):
        # a state with garbage shapes must not raise: serve never breaks
        st = _St({"births": None, "fossils": "junk", "curve": 5,
                  "universe": None})
        html = vgal.build_page("/nonexistent", "", st=st)
        self.assertIn("The Hermi Gallery", html)

    def test_dormant_state_uses_no_canvas(self):
        st = _St({"universe": {"era": 20, "status": "dormant",
                               "key_fp": "2e987e96",
                               "genesis": {"day": "2026-11-11"}}})
        html = vgal.build_page("/nonexistent", "", st=st)
        self.assertNotIn('<canvas class="dish"', html)
        self.assertIn("the dish sleeps", html)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
