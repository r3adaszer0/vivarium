"""VIV-78: the dish must paint with ZERO third-party dependencies.

The hackathon ships this plugin to judges whose runtime has neither
Pillow nor numpy. The dish/status/birth/stamp/curve renders are stdlib
only (write_png = zlib + struct); Pillow appears only in the optional
callout label and the clip engine. This file PROVES the fresh-user path
by running the real render + slash code in a subprocess where numpy,
PIL and imageio are hard-blocked.
"""
import os
import subprocess
import sys
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_PROBE = r'''
import sys
# hard-block the third-party deps BEFORE anything can import them
for _m in ("numpy", "PIL", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont",
           "imageio", "imageio.v2"):
    sys.modules[_m] = None          # import -> ImportError, guaranteed

import os, tempfile
sys.path.insert(0, REPO)
from types import SimpleNamespace
import state as vstate, world as W, tools, artifacts, termrender

tmp = tempfile.mkdtemp()
store = {"universe": {"status": "live", "era": 2},
         "world": W.new_world(seed=5).to_dict()}
ctx = SimpleNamespace(state=SimpleNamespace(
    get=lambda k, d=None: store.get(k, d),
    set=lambda k, v: store.__setitem__(k, v),
    data_dir=lambda: tmp))
vstate.bind(ctx)

w = vstate.load_world()
p = artifacts.render_dish_png(vstate.state(), w, "depfree_dish")
head = open(p, "rb").read(24)
assert head[:8] == b"\x89PNG\r\n\x1a\n", "dish render is not a PNG"
assert termrender.png_size(p) == (337, 337), termrender.png_size(p)
print("DISH_OK", termrender.png_size(p))

# the slash surface: no ASCII fallback, rows reserved, relay request
out = tools._cmd("status")
assert "The dish:" not in out, "ASCII map leaked in the dep-free path"
assert store.get("paint_requests"), "no relay request dropped"
print("STATUS_OK")

# the clip path: with deps blocked the command must degrade to a FRIENDLY
# message, never a raw traceback. (ffmpeg present + pillow blocked -> the
# ImportError message; both missing -> the ffmpeg message; both present ->
# a real clip. All three are graceful.)
try:
    _clip_out = tools._cmd("clip")
    print("CLIP_GRACEFUL", _clip_out.strip().splitlines()[0][:60])
except Exception as e:
    print("CLIP_RAW_CRASH", type(e).__name__)
'''


class TestZeroDeps(unittest.TestCase):
    def test_dish_paint_path_works_without_numpy_or_pillow(self):
        r = subprocess.run(
            [sys.executable, "-c", _PROBE.replace("REPO", repr(_REPO))],
            capture_output=True, timeout=180, cwd=_REPO)
        out = (r.stdout or b"").decode("utf-8", "replace")
        err = (r.stderr or b"").decode("utf-8", "replace")
        self.assertIn("DISH_OK", out, out + err)
        self.assertIn("STATUS_OK", out, out + err)
        self.assertIn("CLIP_GRACEFUL", out, out + err)
        self.assertNotIn("CLIP_RAW_CRASH", out, out + err)


if __name__ == "__main__":
    unittest.main()
