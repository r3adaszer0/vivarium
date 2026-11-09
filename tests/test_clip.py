"""VIV-33: /vivarium clip — the dish as an MP4 (ffmpeg pipe, PIL frames)."""

from __future__ import annotations

import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tools as T  # noqa: E402
import world as W  # noqa: E402
import birth as vbirth  # noqa: E402
import cinematography as vcin  # noqa: E402
from test_birth import FakeState, make_live  # noqa: E402


class _C:
    def __init__(self, st):
        self.state = st


@unittest.skipIf(shutil.which("ffmpeg") is None, "ffmpeg not available")
class TestClip(unittest.TestCase):
    def setUp(self):
        self.s = FakeState()
        make_live(self.s)
        T.vstate._ctx = _C(self.s)
        self.res = vbirth.birth_species(
            self.s, "proof-skill",
            "# proof-skill\\n\\nCompletely unique clip content 9931.\\n",
            save_world=lambda w_: self.s.set("world", w_.to_dict()),
            load_world=lambda: W.World.from_dict(
                self.s.d["world"], seed=self.s.get("seed", 0)))

    def test_clip_whole_dish_writes_mp4(self):
        import tempfile
        import artifacts as vart
        art = os.path.join(tempfile.mkdtemp(), "media")
        os.makedirs(art, exist_ok=True)
        orig = vart.media_dir
        vart.media_dir = lambda s: art
        try:
            out = T._cmd("clip 20")
        finally:
            vart.media_dir = orig
        self.assertIn("Clip written", out)
        self.assertTrue(any(f.endswith(".mp4") for f in os.listdir(art)))

    def test_clip_species_highlight(self):
        import tempfile
        import artifacts as vart
        art = os.path.join(tempfile.mkdtemp(), "media")
        os.makedirs(art, exist_ok=True)
        orig = vart.media_dir
        vart.media_dir = lambda s: art
        try:
            out = T._cmd("clip proof 20")
        finally:
            vart.media_dir = orig
        self.assertIn(self.res["eidos"], out)
        self.assertIn("highlighted", out)

    def test_clip_unknown_species(self):
        out = T._cmd("clip nope")
        self.assertIn("Unknown species", out)

    def test_render_clip_ffmpeg_produces_file(self):
        import tempfile
        w = W.World.from_dict(self.s.d["world"], seed=self.s.get("seed", 0))
        path = os.path.join(tempfile.mkdtemp(), "c.mp4")
        got = vcin.render_clip_ffmpeg(w, path, ticks=15)
        self.assertEqual(got, path)
        self.assertGreater(os.path.getsize(path), 1000)


if __name__ == "__main__":
    unittest.main()
