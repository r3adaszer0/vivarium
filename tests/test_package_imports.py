"""Every module must import the way the plugin loader imports it.

The plugin is loaded as a package (`hermes_plugins.vivarium.<mod>`), not as
loose scripts on sys.path. A flat-only import (`from identity import ...`)
therefore works in every local check and fails only when the hook fires
live, inside a handler that swallows the exception: act 3 vanished exactly
that way. This test imports the real package and touches the code path, so
the mistake cannot reach a user again.
"""

import importlib
import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PKG = "vivarium_packagetest"


def _load_package():
    if PKG in sys.modules:
        return sys.modules[PKG]
    spec = importlib.util.spec_from_file_location(
        PKG, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[PKG] = mod
    spec.loader.exec_module(mod)
    return mod


class PackageImports(unittest.TestCase):
    def test_modules_import_as_a_package(self):
        _load_package()
        for name in ("identity", "world", "portrait", "acts", "card",
                     "artifacts", "birth", "state", "termrender", "seeding"):
            with self.subTest(module=name):
                importlib.import_module(f"{PKG}.{name}")

    def test_arrival_art_renders_when_loaded_as_a_package(self):
        """The exact call that failed live: art_block -> portrait -> identity."""
        _load_package()
        acts = importlib.import_module(f"{PKG}.acts")
        world = importlib.import_module(f"{PKG}.world")
        g = world.genome_from_bytes(bytes(range(24)))
        block = acts.art_block("Eidos_0e09ba", g)
        self.assertIn("\u2588", block)
        self.assertIn("<<ART:Eidos_0e09ba>>", block)

    def test_act3_beat_survives_the_package_path(self):
        _load_package()
        acts = importlib.import_module(f"{PKG}.acts")
        world = importlib.import_module(f"{PKG}.world")

        class S:
            def __init__(self):
                self.d = {}

            def get(self, k, default=None):
                return self.d.get(k, default)

            def set(self, k, v):
                self.d[k] = v

        g = world.genome_from_bytes(bytes(range(24)))
        res = {"eidos": "Eidos_0e09ba", "name": "probe", "pod": 4,
               "tick": 12, "genome": g}
        text = acts.birth_narration(S(), "BASE", res, is_big_bang=False)
        self.assertIn(acts.DISH_MARKER, text)
        self.assertIn("<<ART:", text)
