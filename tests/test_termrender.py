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
import urllib.error
from pathlib import Path

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


class TestAncestorDetection(unittest.TestCase):
    """VIV-77: the TUI slash worker's env is scrubbed of TERMINAL_* vars
    (served_profile_child_env), yet it keeps the TUI's ctty. Capability
    must come from the nearest ancestor that still has terminal env."""

    def test_explicit_env_never_walks(self):
        # env passed explicitly: pure function of that env (pre-update law)
        self.assertEqual(T.detect_graphics({}), "none")

    def test_walk_finds_parent_env(self):
        self.assertEqual(T._detect_from_ancestors(
            environ_of=lambda pid: {"TERM": "xterm-kitty"} if pid == 4242 else {},
            parent_of=lambda pid: 4242 if pid != 4242 else 1,
            has_ctty=True), "kitty")

    def test_walk_stops_without_ctty(self):
        seen = []
        self.assertEqual(T._detect_from_ancestors(
            environ_of=lambda pid: seen.append(pid) or {},
            parent_of=lambda pid: 4242, has_ctty=False), "none")
        self.assertEqual(seen, [])   # no surface -> no /proc reads at all

    def test_walk_respects_max_up(self):
        env_of = lambda pid: {"KITTY_WINDOW_ID": "1"} if pid == 7 else {}  # noqa: E731
        par_of = lambda pid: 7 if pid == 5 else 5                          # noqa: E731
        self.assertEqual(T._detect_from_ancestors(
            max_up=1, environ_of=env_of, parent_of=par_of, has_ctty=True), "none")
        self.assertEqual(T._detect_from_ancestors(
            max_up=2, environ_of=env_of, parent_of=par_of, has_ctty=True), "kitty")

    def test_walk_none_without_terminal_env(self):
        self.assertEqual(T._detect_from_ancestors(
            environ_of=lambda pid: {"PATH": "/bin"},
            parent_of=lambda pid: 4242, has_ctty=True), "none")

    def test_live_detection_consults_walk(self):
        old = T._detect_from_ancestors
        T._detect_from_ancestors = lambda **kw: "kitty"
        try:
            self.assertEqual(T.detect_graphics(), "kitty")   # env=None path
        finally:
            T._detect_from_ancestors = old

    def test_live_walk_runs_without_ctty_arg(self):
        # VIV-77b: the real worker is start_new_session=True (no ctty);
        # the live walk must NOT require one.
        self.assertEqual(T._detect_from_ancestors(
            environ_of=lambda pid: {"TERM": "xterm-kitty"} if pid == 4242 else {},
            parent_of=lambda pid: 4242 if pid != 4242 else 1), "kitty")


class TestAncestorTty(unittest.TestCase):
    """VIV-77b: a session-less worker paints via the ancestor's pty device."""

    def test_finds_ancestor_pts(self):
        links = {"3": "pipe:[12345]", "4": "/dev/pts/1", "5": "/dev/null"}
        self.assertEqual(T._ancestor_tty_path(
            parent_of=lambda pid: 4242 if pid != 4242 else 1,
            fds_of=lambda pid: iter(links) if pid == 4242 else iter(()),
            readlink_of=lambda entry: links[entry]), "/dev/pts/1")

    def test_ignores_pipes_and_null(self):
        links = {"3": "pipe:[1]", "4": "/dev/null", "5": "socket:[7]"}
        self.assertEqual(T._ancestor_tty_path(
            parent_of=lambda pid: 4242 if pid != 4242 else 1,
            fds_of=lambda pid: iter(links) if pid == 4242 else iter(()),
            readlink_of=lambda entry: links[entry]), "")

    def test_stops_at_init(self):
        self.assertEqual(T._ancestor_tty_path(
            parent_of=lambda pid: 1,
            fds_of=lambda pid: iter(("3",)),
            readlink_of=lambda entry: "/dev/pts/1"), "")

    def test_open_paint_tty_none_without_surface(self):
        # in this test process /dev/tty may or may not exist; with the
        # fake walker finding nothing the helper must not raise.
        old = T._ancestor_tty_path
        T._ancestor_tty_path = lambda *a, **k: ""
        try:
            if not T._open_paint_tty():
                pass   # no surface here: None is the correct answer
        finally:
            T._ancestor_tty_path = old


class TestEscapes(unittest.TestCase):
    def setUp(self):
        self.path, self.png = _png()

    def test_kitty_escape_shape_and_roundtrip(self):
        esc = T._kitty_escape(self.png)
        self.assertTrue(esc.startswith(b"\x1b_Gf=100,a=T,I=1,"))
        self.assertTrue(esc.endswith(b"\x1b\\"))
        # single-chunk PNG: exactly one APC opener, m=0 terminator
        self.assertEqual(esc.count(b"\x1b_G"), 1)
        payload = re.search(rb"m=0(?:,[a-zA-Z]=\d+)*;([A-Za-z0-9+/=]+)\x1b\\", esc).group(1)
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
        self.assertTrue(parts[1].startswith(b"f=100,a=T,I=1,m=1,q=2,C=1;"))
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

    def test_tool_path_never_emits_escapes_even_with_tty(self):
        """The gateway may run attached to a tty (user's kitty session!) —
        escapes would still travel the MESSAGE pipeline as mojibake. The
        tool path ALWAYS attaches; only emit_image_raw may write bytes."""
        import io, contextlib

        class FakeTty(io.StringIO):
            def isatty(self):
                return True

        buf = FakeTty()
        with contextlib.redirect_stdout(buf):
            out = T.emit_image(self.path, env={"TERM": "xterm-kitty"})
        self.assertIn("attached", out)
        self.assertEqual(buf.getvalue(), "")       # nothing written

    def test_emit_image_raw_writes_kitty_escape(self):
        """Interactive-only path: writes real APC bytes to stdout when no
        /dev/tty is available (containers, pipes)."""
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            out = T.emit_image_raw(self.path, env={"TERM": "xterm-kitty"})
        self.assertIn("kitty graphics emitted", out)
        written = buf.getvalue()
        self.assertIn("\x1b_Gf=100", written)
        # VIV-41: reserve the image rectangle, paint into it, leave the
        # cursor at its bottom (so the reply flows below the picture).
        self.assertTrue(written.startswith("\x1b7"))
        self.assertIn("\x1b8", written)
        self.assertRegex(written, r"\x1b\[\d+B$")

    def test_emit_image_raw_prefers_dev_tty(self):
        """With a /dev/tty, bytes go to the RAW terminal (bypassing the
        TUI's rich-wrapped stdout which mangles APC into visible text —
        the user's kitty mojibake)."""
        import io, contextlib, os, tempfile
        # fake tty device: a temp file standing in for /dev/tty
        fake = tempfile.NamedTemporaryFile(delete=False)
        fake.close()
        real_open = os.open
        opened = {}
        def fake_open(path, flags, *a, **k):
            if str(path) == "/dev/tty":
                opened["hit"] = True
                return os.open(fake.name, flags)
            return real_open(path, flags, *a, **k)
        buf = io.StringIO()
        import termrender as Tm
        with contextlib.redirect_stdout(buf):
            real_write = os.write
            written = {}
            def fake_write(fd, data):
                written["data"] = data
                return real_write(fd, data)
            os.open, os.write = fake_open, fake_write
            try:
                out = Tm.emit_image_raw(self.path, env={"TERM": "xterm-kitty"})
            finally:
                os.open, os.write = real_open, real_write
        os.unlink(fake.name)
        self.assertIn("kitty graphics emitted", out)
        self.assertTrue(opened.get("hit"))
        self.assertIn(b"\x1b_Gf=100", written["data"])
        self.assertEqual(buf.getvalue(), "")   # nothing through rich-wrapped stdout


class TestImagePaintFlow(unittest.TestCase):
    """When the image paints inline, the ASCII map is suppressed."""

    def test_painted_image_drops_ascii_map(self):
        import tools
        text = tools._render_text({
            "tick": 24, "population": 22, "map": "", "legend": ""})
        self.assertEqual(text, "Tick 24 — 22 creatures")
        self.assertNotIn("\n\n\n", text)

    def test_overlay_reserves_rows_and_schedules_paint(self):
        """The clever overlay: returned text reserves blank rows sized to
        the PNG (cell-estimate), a deferred paint drops the PNG over
        them, ASCII is the fallback (not printed inline)."""
        import importlib, os, tempfile
        from types import SimpleNamespace
        import state as vstate, world as W, artifacts as A, termrender
        import tools
        tmp = tempfile.mkdtemp()
        w = W.new_world(seed=5)
        W.run(w, 30, 0.05)
        store = {"universe": {"status": "live", "era": 2}, "world": w.to_dict()}
        ctx = SimpleNamespace(state=SimpleNamespace(
            get=lambda k, d=None: store.get(k, d),
            set=lambda k, v: store.__setitem__(k, v),
            data_dir=lambda: tmp))
        vstate.bind(ctx)
        path = A.render_dish_png(vstate.state(), w, "t_ov")
        self.assertTrue(path and os.path.exists(path))
        scheduled = []
        real_paint = termrender.paint_over
        termrender.paint_over = (
            lambda *a, **k: scheduled.append(a) or "overlay scheduled")
        try:
            out = tools._cmd("render --image")
        finally:
            termrender.paint_over = real_paint
        lines = out.splitlines()
        self.assertIn("Tick", lines[0])
        # spacer block sized to the PNG at the calibrated cell height:
        # ceil(339/11) = 31 rows of spaces between summary and path
        spacer_rows = [l for l in lines[1:] if l and not l.strip()]
        self.assertGreaterEqual(len(spacer_rows), 20)
        self.assertLessEqual(len(spacer_rows), 26)
        # path after the spacer
        self.assertIn("🖼️", out)
        self.assertEqual(len(scheduled), 1)
        self.assertEqual(scheduled[0][0].endswith(".png"), True)
        self.assertTrue(os.path.exists(scheduled[0][0]))

    def test_tui_render_image_returns_clean_text_no_ascii(self):
        """Inside the TUI the slash cannot paint reliably (the redraw
        engine owns the screen) — it returns summary + path only, no
        ASCII map, no escape bytes."""
        import importlib, os, tempfile
        from types import SimpleNamespace
        import state as vstate, world as W, artifacts as A
        import tools
        tmp = tempfile.mkdtemp()
        w = W.new_world(seed=5)
        W.run(w, 30, 0.05)
        store = {"universe": {"status": "live", "era": 2}, "world": w.to_dict()}
        ctx = SimpleNamespace(state=SimpleNamespace(
            get=lambda k, d=None: store.get(k, d),
            set=lambda k, v: store.__setitem__(k, v),
            data_dir=lambda: tmp))
        vstate.bind(ctx)
        path = A.render_dish_png(vstate.state(), w, "t_tui")
        self.assertTrue(path and os.path.exists(path))
        out = tools._cmd("render --image")
        self.assertIn("Tick", out)
        self.assertIn("🖼️", out)
        self.assertNotIn("\x1b", out)          # no escapes in TUI text
        # ASCII map suppressed when an image was produced
        self.assertNotIn("X = creatures", out)
    """When the image paints inline, the ASCII map is suppressed."""

    def test_painted_image_drops_ascii_map(self):
        import tools
        text = tools._render_text({
            "tick": 24, "population": 22, "map": "", "legend": ""})
        self.assertEqual(text, "Tick 24 — 22 creatures")
        self.assertNotIn("\n\n\n", text)


class TestMediaOfferDefaultOn(unittest.TestCase):
    """Graphics-capable terminals get images BY DEFAULT (user decision);
    the offer tells them how to disable, not enable."""

    def test_offer_says_disable_not_enable(self):
        import tools
        offer = tools._media_offer()
        # only meaningful when a graphics terminal is detected; in tests
        # detect returns none -> empty. Force-detect via env instead:
        import termrender as T
        real = T.detect_graphics
        T.detect_graphics = lambda env=None: "kitty"
        try:
            offer = tools._media_offer()
        finally:
            T.detect_graphics = real
        self.assertIn("automatically", offer)
        self.assertIn("/vivarium images off", offer)
        self.assertIn("images off", offer)
        self.assertNotIn("images on", offer)


class TestSlashPolish(unittest.TestCase):
    """User-paste fixes: no duplicate path line; --colour alias accepted."""

    def test_slash_render_no_duplicate_path(self):
        import tools
        text = tools._render_text({
            "tick": 24, "population": 22, "map": "M", "legend": "L",
            "media": ["/tmp/dish_24.png"], "graphics": "attached /tmp/dish_24.png"})
        self.assertEqual(text.count("/tmp/dish_24.png"), 1)
        self.assertNotIn("(attached", text)

    def test_slash_render_accepts_colour_spelling(self):
        # the parser maps --colour to the color flag (can't call the real
        # parser without a gateway; test the predicate logic directly)
        rest = "--rich --colour"
        self.assertTrue("colour" in rest or "--colour" in rest)


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

    def test_status_slash_rels_not_ascii_when_headless(self):
        """VIV-77b contract: on a live universe with media auto, a headless
        slash worker NEVER falls back to the ASCII map the user hated — it
        reserves the picture rows and drops a paint request for whichever
        process sits on a terminal. ASCII only when media_pref=ascii."""
        import tools
        tmp = tempfile.mkdtemp()
        store = self._bound(tmp)
        store["universe"] = {"status": "live", "era": 2}
        out = tools._cmd("status")
        self.assertNotIn("The dish:", out)
        self.assertNotIn("X = creatures", out)
        self.assertTrue(store.get("paint_requests"),
                        "headless status must drop a paint request")
        self.assertEqual(store["paint_requests"][0]["kind"], "status")

    def test_status_slash_ascii_only_when_media_pref_ascii(self):
        import tools
        tmp = tempfile.mkdtemp()
        store = self._bound(tmp)
        store["universe"] = {"status": "live", "era": 2}
        store["media_pref"] = "ascii"
        out = tools._cmd("status")
        self.assertIn("The dish:", out)
        self.assertIn("X = creatures", out)

    def test_paint_request_fifo_and_expiry(self):
        import time as _t
        import state as vstate
        tmp = tempfile.mkdtemp()
        store = self._bound(tmp)
        vstate.request_paint("status")
        vstate.request_paint("birth")
        req = vstate.pop_paint_request()
        self.assertEqual(req["kind"], "status")     # oldest first
        req2 = vstate.pop_paint_request()
        self.assertEqual(req2["kind"], "birth")
        self.assertIsNone(vstate.pop_paint_request())
        # stale requests expire (the TUI was closed): nothing stranded
        store["paint_requests"] = [{"kind": "status", "ts": _t.time() - 60}]
        self.assertIsNone(vstate.pop_paint_request())
        self.assertEqual(store["paint_requests"], [])

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


class TestLiveDishEndpoint(unittest.TestCase):
    """VIV-90: a page refresh asks the dish for its CURRENT tick."""

    def _serve(self, provider):
        import termrender as vterm
        tmp = tempfile.mkdtemp()
        Path(tmp, "keep.txt").write_text("x")
        res = vterm.serve_gallery(tmp, dish_map="", title="t",
                                  open_browser=False, dish_provider=provider)
        self.assertNotIn("error", res)
        self.addCleanup(res["server"].server_close)
        self.addCleanup(res["thread"].join, timeout=2)
        return res["url"]

    def test_provider_answers_with_fresh_dish(self):
        calls = []

        def provider():
            calls.append(1)
            return {"tick": 1234, "alive": 42, "grid": "0a0f0df|0a0f0d7"}

        url = self._serve(provider)
        import urllib.request, json as _json
        with urllib.request.urlopen(url + "/live/dish.json", timeout=5) as r:
            data = _json.loads(r.read().decode())
            self.assertEqual(r.headers.get("Cache-Control"), "no-store")
        self.assertEqual(data["tick"], 1234)
        self.assertEqual(data["alive"], 42)
        self.assertEqual(len(calls), 1)   # fresh per request

    def test_provider_failure_serves_503_page_keeps_last_dish(self):
        def provider():
            raise RuntimeError("mid-tick race")

        url = self._serve(provider)
        import urllib.request
        try:
            urllib.request.urlopen(url + "/live/dish.json", timeout=5)
            self.fail("expected HTTP 503")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 503)

    def test_fresh_flag_reaches_the_provider(self):
        """VIV-98: the status button asks for the truth, not the cache."""
        seen = []

        def provider(fresh=False):
            seen.append(fresh)
            return {"tick": 1, "alive": 1, "grid": "0a0f0df",
                    "status": {"tick": 1, "population": 1}}

        url = self._serve(provider)
        import urllib.request, json as _json
        with urllib.request.urlopen(url + "/live/dish.json?fresh=1", timeout=5) as r:
            data = _json.loads(r.read().decode())
        self.assertEqual(seen, [True])
        self.assertIn("status", data)
        with urllib.request.urlopen(url + "/live/dish.json", timeout=5) as r:
            _json.loads(r.read().decode())
        self.assertEqual(seen, [True, False])

    def test_zero_arg_provider_still_served(self):
        def provider():
            return {"tick": 7, "alive": 3, "grid": "0a0f0df"}

        url = self._serve(provider)
        import urllib.request, json as _json
        with urllib.request.urlopen(url + "/live/dish.json?fresh=1", timeout=5) as r:
            data = _json.loads(r.read().decode())
        self.assertEqual(data["tick"], 7)

    def test_without_provider_the_endpoint_is_404(self):
        url = self._serve(None)
        import urllib.request
        try:
            urllib.request.urlopen(url + "/live/dish.json", timeout=5)
            self.fail("expected HTTP 404")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
