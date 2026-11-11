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

    def test_latest_birth_replaces_latest_clip(self):
        """VIV-92: NOW features the newest born SPECIES — face, name,
        provenance, chip — linked to its certificate. No clip card."""
        html = vgal.build_page("/nonexistent", RICH, st=_St(_state()))
        self.assertIn("Latest birth", html)
        self.assertNotIn("Latest clip", html)
        import re as _re
        now_sec = html.split('id="now"')[1].split("</section>")[0]
        m = _re.search(r'href="#cert-([0-9a-f]+)"', now_sec)
        self.assertTrue(m, "the featured card must link to a certificate")
        # the linked eidos is the one the card actually names
        self.assertIn(f"Eidos_{m.group(1)}", now_sec)
        # its certificate is anchorable
        self.assertIn(f'id="cert-{m.group(1)}"', html)

    def test_no_births_no_latest_card(self):
        """A fresh install has no births -> no featured card, no crash."""
        html = vgal.build_page("/nonexistent", RICH, st=_St(_state(births={})))
        self.assertNotIn("Latest birth", html)

    def test_pulse_section_is_gone(self):
        html = vgal.build_page("/nonexistent", RICH, st=_St(_state()))
        self.assertNotIn('id="pulse"', html)
        self.assertNotIn("The Pulse", html)
        self.assertNotIn("<path d=\"M", html)
        self.assertNotIn("population history", html)
        # the masthead nav still carries every universe
        self.assertIn('class="eras"', html)

    def test_curve_data_is_ignored_not_rendered(self):
        html = vgal.build_page("/nonexistent", RICH, st=_St(_state(curve=[
            {"tick": t * 10, "population": t, "born": t} for t in range(50)])))
        self.assertNotIn('class="curve"', html)
        self.assertNotIn("<path d=\"M", html)

    def test_live_flag_marks_the_canvas(self):
        """VIV-90: the served page asks the dish for its current tick."""
        html = vgal.build_page("/nonexistent", RICH, st=_St(_state()))
        self.assertIn("data-live", html)
        self.assertIn("/live/dish.json", html)
        plain = vgal.build_page("/nonexistent", RICH, st=_St(_state()),
                                live_flag=False)
        self.assertNotIn("data-live", plain)


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


class TestAnyUser(unittest.TestCase):
    """VIV-89 follow-up: the gallery must work for ANY install.

    Nothing on the page may be keyed to one machine's registry — the
    whole page is derived from the state handle that is passed in.
    """

    def test_fresh_install_renders_a_valid_page(self):
        # a brand-new user: era 1, no births, no fossils, no curve, no media
        st = _St({"births": {}, "fossils": [], "curve": [],
                  "universe": {"era": 1, "status": "live", "key_fp": "a1b2c3d4",
                               "genesis": {"skill": "seed:demo", "day": "2026-11-11"}}})
        html = vgal.build_page("/nonexistent", "", st=st)
        self.assertIn("The Hermi Gallery", html)
        self.assertIn("Era 1", html)
        self.assertIn("0 fossils", html)
        self.assertIn("0 births", html)
        self.assertIn('id="ua1b2c3d4"', html)
        self.assertIn("No clips filmed in this era yet", html)
        self.assertNotIn('class="cert"', html)      # no registry yet — honest
        self.assertNotIn('class="spec"', html)      # no fallen yet

    def test_a_foreign_registry_names_its_own_species(self):
        # someone else's universe: different skills, genomes, keys
        g1 = {"forage": 0.4, "sense": 3.0, "metabolism_mult": 0.9,
              "aggression": 2.2, "mutate": 0.5, "dispersal": 1.4, "hue": 0.5}
        st = _St({"births": {"totally-other-skill": {"eidos": "Eidos_aaaabbbb",
                                                     "day": "2026-10-01",
                                                     "era": 3, "genome": g1}},
                  "fossils": [{"lineage": "Eidos_ccccdddd", "genome": g1,
                               "universe": "ffffffff", "day": "2026-09-30"}],
                  "curve": [{"tick": 10, "population": 12, "born": 12}],
                  "universe": {"era": 3, "status": "live", "key_fp": "ffffffff",
                               "genesis": {"day": "2026-10-01"}}})
        html = vgal.build_page("/nonexistent", "", st=st)
        genus, epithet, _ = vid.name_of(g1)
        self.assertIn(f"{genus} {epithet}", html)
        self.assertIn("totally-other-skill", html)
        self.assertIn('id="uffffffff"', html)
        self.assertIn("Eidos_aaaabbbb", html)
        # nothing from THIS machine's registry leaks into their page
        self.assertNotIn("Eidos_ef543f71", html)
        self.assertNotIn("2e987e96", html)
        self.assertNotIn("airtable", html)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
