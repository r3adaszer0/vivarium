"""VIV-80: the layout fixes the user asked for on the live era-13 dish.

Four explicit asks, each pinned by a test so they cannot silently
regress again (the white-ring legend had been reported repeatedly):

1. act-2: one empty terminal line between the copy and the dish.
2. act-3: the Hermi face two lines higher, so the Meet/Watch lines rise
   with it and the census lands just under the dish.
3. NO "white ring = the pod" legend, anywhere, ever.
4. /vivarium show paints the face IMAGE on every surface: a headless
   drain reserves the rows and drops a `show` paint request the
   terminal-owning process claims (the status relay contract, extended).
"""

from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import state as vstate          # noqa: E402
import hooks as vhooks          # noqa: E402
import card as vcard            # noqa: E402
import tools as T               # noqa: E402
import termrender               # noqa: E402
import world as W               # noqa: E402
import birth as vbirth          # noqa: E402
from test_birth import FakeState, make_live  # noqa: E402

BANG = ("Universe born (era 13). Seeded 89 species from your skills: "
        "87 canon, 2 private.\n\nThe Hadean die-off begins: only lineages "
        "that fit the dish's living rules survive.")
LIVE = {"tick": 12, "alive": 317, "lineages": 92, "lineages_total": 120,
        "coloured": 8, "grey": 112}


def _bind(store=None):
    store = store if store is not None else {}
    ctx = SimpleNamespace(state=SimpleNamespace(
        get=lambda k, d=None: store.get(k, d),
        set=lambda k, v: store.__setitem__(k, v),
        data_dir=lambda: os.path.join(os.environ.get("TMPDIR", "/tmp"),
                                      "viv80")))
    vstate.bind(ctx)
    return store


class TestCardLayout(unittest.TestCase):
    def setUp(self):
        self.store = _bind()

    def tearDown(self):
        vstate.bind(None)

    def test_act2_has_one_blank_line_before_the_dish(self):
        import re as _re
        r = vcard.render(BANG, 100, "vivarium", live=LIVE, dish=True,
                         dish_cols=39, era=13)
        self.assertTrue(r["has_dish"])
        texts = [_re.sub(r"\x1b\[[0-9;]*m", "", ln).strip()
                 for ln in r["text"].split("\n")]
        die_off = max(i for i, t in enumerate(texts)
                      if t.startswith("The Hadean die-off"))
        self.assertEqual(texts[die_off + 1], "", "one empty line")
        # then the reserved dish rows: a solid block of empty rows before
        # the next non-blank line (the command table)
        blanks = 0
        for t in texts[die_off + 2:]:
            if t:
                break
            blanks += 1
        self.assertGreaterEqual(blanks, 15, "the reserved dish rows follow")

    def test_act2_reserves_dish_rows_at_all(self):
        # the pre-VIV-80 bug: the act-2 card reserved NOTHING, so the
        # image had nowhere to land even with the relay fixed
        r = vcard.render(BANG, 100, "vivarium", live=LIVE, dish=True,
                         dish_cols=39, era=13)
        self.assertTrue(r["has_dish"])
        self.assertGreaterEqual(r["rows"], 20)

    def test_no_white_ring_legend_anywhere(self):
        for body, era in ((BANG, 13),
                          ("New species Eidos_1a2b3c4d test.\n\n<<ART:"
                           "Eidos_1a2b3c4d>>\n o o \n<</ART>>\nMeet it.",
                           13)):
            r = vcard.render(body, 100, "vivarium", live=LIVE, dish=True,
                             dish_cols=39, era=era)
            self.assertNotIn("white ring", r["text"])
            self.assertNotIn("ring =", r["text"])

    def test_face_sits_higher_in_the_art_block(self):
        import acts as vacts
        genome = {"forage": 0.2, "sense": 1.0, "metabolism_mult": 0.7,
                  "aggression": 0.05, "mutate": 0.5, "dispersal": 0.0,
                  "hue": 0.6}
        block = vacts.art_block("Eidos_1a2b3c4d", genome)
        inner = block.split("\n")[1:-1]          # strip the ART fences
        first_content = next(i for i, ln in enumerate(inner) if ln.strip())
        # the face leads with at most one pad row (was three)
        self.assertLessEqual(first_content, 1)


class TestShowRelay(unittest.TestCase):
    def setUp(self):
        self.s = FakeState()
        make_live(self.s)
        T.vstate._ctx = type("C", (), {"state": self.s})()
        self.res = vbirth.birth_species(
            self.s, "relay-skill",
            "# relay-skill\n\nA body for the show relay test, unique www.\n",
            save_world=lambda w_: self.s.set("world", w_.to_dict()),
            load_world=lambda: W.World.from_dict(
                self.s.d["world"], seed=self.s.get("seed", 0)))
        self.eidos = self.res["eidos"]
        self._old = (termrender.paint_over, termrender.detect_graphics)
        termrender.detect_graphics = lambda *a, **k: "none"

    def tearDown(self):
        termrender.paint_over, termrender.detect_graphics = self._old
        vstate.bind(None)

    def test_headless_show_drops_a_show_request_with_geometry(self):
        out = T._cmd(f"show {self.eidos}")
        reqs = self.s.get("paint_requests") or []
        self.assertTrue(reqs, "the headless show must drop a paint request")
        req = reqs[-1]
        self.assertEqual(req.get("kind"), "show")
        self.assertTrue(req.get("path", "").endswith(".png"))
        self.assertGreaterEqual(int(req.get("res_rows") or 0), 1)
        # the reserved rows ride the returned text
        self.assertIn(" " * 12, out)

    def test_show_relay_paints_the_requested_glyph(self):
        out = T._cmd(f"show {self.eidos}")
        req = (self.s.get("paint_requests") or [])[-1]
        painted = []
        termrender.paint_over = (
            lambda p, rows, trail, delay=0.0: painted.append((p, rows, trail)))
        vhooks._paint_show_relay(req)
        self.assertEqual(len(painted), 1)
        self.assertEqual(painted[0][0], req["path"])
        self.assertEqual(painted[0][1], int(req["res_rows"]))

    def test_paint_relay_dispatches_by_kind(self):
        T._cmd(f"show {self.eidos}")
        req = (self.s.get("paint_requests") or [])[-1]
        painted = []
        termrender.paint_over = (
            lambda p, rows, trail, delay=0.0: painted.append((p, rows, trail)))
        vhooks._paint_show_relay({"kind": "show", "path": req["path"],
                                  "res_rows": req["res_rows"],
                                  "trail": req["trail"]})
        self.assertTrue(painted)
        # a status request still goes down the dish path (no path field)
        vhooks._paint_show_relay({"kind": "status"})
        self.assertEqual(len(painted), 1, "status must not use the glyph path")


if __name__ == "__main__":
    unittest.main()
