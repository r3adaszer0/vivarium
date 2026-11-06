"""VIV-28b tests: terminal graphics + localhost gallery (all state-free)."""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import tempfile
import unittest
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import artifacts as A
import termrender as T


def _png(w=16, h=16):
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "d.png")
    rows = [[(6, 40, 22) if (x + y) % 3 else (120, 200, 90) for x in range(w)]
            for y in range(h)]
    A.write_png(path, rows, w)
    return path, open(path, "rb").read()


class TestDetection(unittest.TestCase):
    def test_conservative_by_default(self):
        self.assertEqual(T.detect_graphics({}), "none")
        self.assertEqual(T.detect_graphics({"TERM": "xterm-256color"}), "none")

    def test_kitty(self):
        self.assertEqual(T.detect_graphics({"TERM": "xterm-kitty"}), "kitty")
        self.assertEqual(T.detect_graphics({"KITTY_WINDOW_ID": "1"}), "kitty")

    def test_iterm2(self):
        self.assertEqual(T.detect_graphics({"ITERM_SESSION_ID": "w0t0p0"}), "iterm2")
        self.assertEqual(T.detect_graphics({"TERM_PROGRAM": "iTerm.app"}), "iterm2")

    def test_sixel(self):
        self.assertEqual(T.detect_graphics(
            {"TERM_PROGRAM": "WezTerm", "TERM": "xterm-256color"}), "sixel")
        self.assertEqual(T.detect_graphics({"TERM": "xterm+sixel"}), "sixel")


class TestEscapes(unittest.TestCase):
    def setUp(self):
        self.path, self.png = _png()

    def test_kitty_escape_shape_and_roundtrip(self):
        esc = T._kitty_escape(self.png)
        self.assertTrue(esc.startswith(b"\x1b_Gf=32,a=T,I=1,"))
        self.assertTrue(esc.endswith(b"\x1b\\"))
        # single-chunk PNG: exactly one APC opener, m=0 terminator
        self.assertEqual(esc.count(b"\x1b_G"), 1)
        payload = re.search(rb"m=0;([A-Za-z0-9+/=]+)\x1b\\", esc).group(1)
        self.assertEqual(base64.b64decode(payload), self.png)

    def test_kitty_chunking_over_4096(self):
        # a PNG whose b64 exceeds one chunk (padded dish, 64x64)
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "big.png")
        rows = [[(x * 4 % 256, y * 4 % 256, 30) for x in range(64)]
                for y in range(64)]
        A.write_png(path, rows, 64)
        esc = T._kitty_escape(open(path, "rb").read())
        parts = esc.split(b"\x1b_G")
        self.assertGreater(len(parts) - 1, 1)             # continuation chunks
        self.assertTrue(esc.endswith(b"\x1b\\"))
        # first chunk has the full header; continuations carry only m=
        # (m=1 while more follow, m=0 on the final chunk)
        self.assertTrue(parts[1].startswith(b"f=32,a=T,I=1,m=1;"))
        for chunk in parts[2:-1]:
            self.assertTrue(chunk.startswith(b"m=1;"))
        self.assertTrue(parts[-1].startswith(b"m=0;"))

    def test_iterm2_escape_shape(self):
        esc = T._iterm2_escape(self.png)
        self.assertTrue(esc.startswith(b"\x1b]1337;File=name="))
        self.assertIn(b"inline=1;", esc)
        self.assertTrue(esc.endswith(b"\x1b\\"))
        payload = esc.split(b":", 1)[1][:-2]
        self.assertEqual(base64.b64decode(payload), self.png)

    def test_sixel_escape_shape(self):
        esc = T._sixel_escape(self.png)
        self.assertTrue(esc.startswith(b"\x1bP0;1;0q"))
        self.assertTrue(esc.endswith(b"\x1b\\"))
        self.assertNotIn(b"\x00", esc)
        self.assertGreaterEqual(esc.count(b"-"), 3)       # 16 rows -> 3 bands

    def test_emit_image_without_tty_attaches_instead(self):
        # tests run without a tty -> attachment path, never escapes
        out = T.emit_image(self.path, env={}, force="none")
        self.assertIn("attached", out)
        out = T.emit_image("/nonexistent.png", env={}, force="kitty")
        self.assertIn("could not read", out)

    def test_emit_image_never_escapes_without_a_tty(self):
        """Gateway/chat contexts have no tty — raw kitty escapes there show
        up as mojibake in the message (user's kitty test). Must return the
        attachment path instead of emitting bytes."""
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):     # not a tty
            out = T.emit_image(self.path, env={"TERM": "xterm-kitty"})
        self.assertIn("attached", out)
        self.assertNotIn("emitted", out)
        self.assertEqual(buf.getvalue(), "")       # NOTHING written to stdout


class TestGallery(unittest.TestCase):
    def test_serves_media_and_dish_on_localhost_ephemeral(self):
        tmp = tempfile.mkdtemp()
        path, _ = _png()
        os.replace(path, os.path.join(tmp, "glyph_ab12cd.png"))
        res = T.serve_gallery(tmp, dish_map="X  . :", title="Test Dish",
                              port=0, open_browser=False)
        try:
            self.assertTrue(res["url"].startswith("http://127.0.0.1:"))
            html = urllib.request.urlopen(res["url"], timeout=5).read().decode()
            self.assertIn("Test Dish", html)
            self.assertIn("glyph_ab12cd.png", html)
            self.assertIn("X&nbsp;&nbsp;.&nbsp;:", html)     # dish preserved
            img = urllib.request.urlopen(
                res["url"].rstrip("/") + "/glyph_ab12cd.png", timeout=5).read()
            self.assertTrue(img.startswith(b"\x89PNG"))
        finally:
            res["server"].shutdown()

    def test_no_media_dir_is_an_error(self):
        res = T.serve_gallery("/nonexistent-dir-xyz", open_browser=False)
        self.assertIn("error", res)

    def test_binds_localhost_only(self):
        tmp = tempfile.mkdtemp()
        res = T.serve_gallery(tmp, port=0, open_browser=False)
        try:
            self.assertEqual(res["server"].server_address[0], "127.0.0.1")
        finally:
            res["server"].shutdown()


class TestToolWiring(unittest.TestCase):
    """End-to-end through tools.py with a bound fake state (live universe)."""

    def _bound(self, tmp):
        from types import SimpleNamespace
        import state as vstate, world as W
        store = {"universe": {"status": "live", "era": 2},
                 "world": W.new_world(seed=5).to_dict()}
        w = W.World.from_dict(store["world"])
        W.run(w, 30, 0.05)
        store["world"] = w.to_dict()
        ctx = SimpleNamespace(state=SimpleNamespace(
            get=lambda k, d=None: store.get(k, d),
            set=lambda k, v: store.__setitem__(k, v),
            data_dir=lambda: tmp))
        vstate.bind(ctx)
        return store

    def test_render_image_renders_png_and_reports_graphics(self):
        import tools, json
        tmp = tempfile.mkdtemp()
        self._bound(tmp)
        out = json.loads(tools._tool_render({"image": True}))
        self.assertEqual(out["success"], True)
        self.assertEqual(len(out["media"]), 1)
        self.assertTrue(out["media"][0].endswith(".png"))
        self.assertTrue(os.path.exists(out["media"][0]))
        # no tty in the tool-execution context -> attach, never escape garbage
        self.assertIn("attached", out["graphics"])

    def test_render_slash_is_plain_text_not_json(self):
        """/vivarium render --rich must print real newlines (user screenshot:
        raw JSON with literal \n garbage)."""
        import tools
        tmp = tempfile.mkdtemp()
        self._bound(tmp)
        store = {"universe": {"status": "live", "era": 2}}
        out = tools._cmd("render --rich")
        self.assertFalse(out.strip().startswith("{"))
        self.assertNotIn("\\n", out)              # no literal backslash-n
        self.assertIn("creatures", out)
        self.assertIn("food blooms", out)
        out = tools._cmd("render --image")
        self.assertFalse(out.strip().startswith("{"))
        self.assertIn("🖼️", out)                  # PNG path shown as artifact
        self.assertIn(".png", out)

    def test_status_slash_includes_dish_map(self):
        """/vivarium status must SHOW the dish (summary alone hid it)."""
        import tools
        tmp = tempfile.mkdtemp()
        store = self._bound(tmp)
        store["universe"] = {"status": "live", "era": 2}
        out = tools._cmd("status")
        self.assertIn("The dish:", out)
        self.assertIn("X", out)          # creatures render as X
        self.assertIn("X = creatures", out)   # legend line

    def test_serve_slash_returns_localhost_url(self):
        import tools
        tmp = tempfile.mkdtemp()
        self._bound(tmp)
        out = tools._cmd("serve")
        self.assertIn("http://127.0.0.1:", out)
        self.assertIn("Localhost only", out)


class TestColoredRichMap(unittest.TestCase):
    """VIV-28c: --color creatures as truecolor background blocks."""

    def test_colored_map_structure(self):
        import re
        import world as W
        w = W.new_world(seed=9)
        W.run(w, 30, 0.05)
        plain = W.render_ascii_rich(w, color=False)
        colored = W.render_ascii_rich(w, color=True)
        stripped = re.sub(r"\x1b\[[0-9;]*m", "", colored)
        # strip must yield exactly the same geometry (spaces where █ was)
        self.assertEqual([len(l) for l in stripped.splitlines()],
                         [len(l) for l in plain.splitlines()])
        self.assertEqual(stripped.count(" "), plain.count("█"))
        # every creature cell carries a truecolor bg escape
        self.assertEqual(colored.count("\x1b[48;2;"), plain.count("█"))

    def test_colors_differ_across_lineages(self):
        import world as W
        import identity as I
        w = W.new_world(seed=9)
        W.run(w, 30, 0.05)
        hues = {c.genome["hue"] for c in w.creatures}
        self.assertGreater(len({I.color_for(h) for h in hues}), 1)

    def test_tool_gates_color_on_tty(self):
        """color=true in a no-tty context (gateway/chat) must NOT embed
        ANSI codes — same law as graphics escapes."""
        import json, tools, tempfile
        from types import SimpleNamespace
        import state as vstate, world as W
        tmp = tempfile.mkdtemp()
        store = {"universe": {"status": "live", "era": 2},
                 "world": W.new_world(seed=5).to_dict()}
        w = W.World.from_dict(store["world"]); W.run(w, 30, 0.05)
        store["world"] = w.to_dict()
        ctx = SimpleNamespace(state=SimpleNamespace(
            get=lambda k, d=None: store.get(k, d),
            set=lambda k, v: store.__setitem__(k, v),
            data_dir=lambda: tmp))
        vstate.bind(ctx)
        out = json.loads(tools._tool_render({"rich": True, "color": True}))
        self.assertNotIn("\x1b[", out["map"])   # no ANSI in chat payload


class TestMediaPref(unittest.TestCase):
    """VIV-27: the media preference knob + terminal-aware start offer."""

    def _bound(self, tmp):
        from types import SimpleNamespace
        import state as vstate, world as W
        store = {"universe": {"status": "dormant", "era": 0}}
        ctx = SimpleNamespace(state=SimpleNamespace(
            get=lambda k, d=None: store.get(k, d),
            set=lambda k, v: store.__setitem__(k, v),
            data_dir=lambda: tmp))
        vstate.bind(ctx)
        return store

    def test_default_is_auto_and_roundtrips(self):
        import tools
        tmp = tempfile.mkdtemp()
        store = self._bound(tmp)
        self.assertEqual(tools.media_pref(), "auto")
        self.assertIn("image", tools.set_media_pref("image"))
        self.assertEqual(tools.media_pref(), "image")
        self.assertIn("ascii", tools.set_media_pref("ascii"))
        self.assertEqual(tools.media_pref(), "ascii")
        self.assertIn("auto", tools.set_media_pref("auto"))
        self.assertEqual(tools.media_pref(), "auto")

    def test_images_slash_command(self):
        import tools
        tmp = tempfile.mkdtemp()
        self._bound(tmp)
        self.assertIn("auto", tools._cmd("images"))
        out = tools._cmd("images on")
        self.assertIn("image", out)
        out = tools._cmd("images off")
        self.assertIn("ascii", out)
        self.assertIn("Set with", tools._cmd("images"))  # no-arg: status+usage

    def test_bad_mode_rejected(self):
        import tools
        tmp = tempfile.mkdtemp()
        self._bound(tmp)
        self.assertIn("Unknown mode", tools.set_media_pref("always"))
        self.assertEqual(tools.media_pref(), "auto")   # unchanged

    def test_start_offer_only_when_graphics_terminal(self):
        import tools
        tmp = tempfile.mkdtemp()
        self._bound(tmp)
        # plain env -> no offer (detect_graphics sees the real env here; on
        # this dev box it's 'none', on a kitty box the test still holds
        # because pref stays 'auto' and the offer must appear)
        offer_present = "images on" in tools._cmd("start")
        real = __import__("termrender").detect_graphics()
        self.assertEqual(offer_present, real in ("kitty", "iterm2", "sixel"))
        # once the user chooses, the offer never nags again
        tools.set_media_pref("ascii")
        self.assertNotIn("images on", tools._cmd("start"))
        tools.set_media_pref("image")
        self.assertNotIn("images on", tools._cmd("start"))
        tools.set_media_pref("auto")

    def test_restart_narration_carries_the_offer(self):
        """Same offer on /vivarium restart — the user's testable moment."""
        import tools
        tmp = tempfile.mkdtemp()
        store = self._bound(tmp)
        store["universe"] = {"status": "live", "era": 1}
        out = tools._cmd("restart")
        self.assertIn("brand-new world", out)
        real = __import__("termrender").detect_graphics()
        self.assertEqual("images on" in out, real in ("kitty", "iterm2", "sixel"))
        # and the no-nag rule holds here too
        tools.set_media_pref("ascii")
        out2 = tools._cmd("restart")
        self.assertNotIn("images on", out2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
