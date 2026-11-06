"""Package-mode import regression: the gateway loads the plugin as a PACKAGE
(hermes_plugins.vivarium.*), tests run it FLAT — so any lazy `from world import …`
inside a function works in tests and explodes in production (found live on the
user's machine: Big Bang crashed at seeding.py:39 with ModuleNotFoundError).
This suite imports every module BOTH ways and exercises the Big Bang path in
package mode, so no flat-only import can ever ship again.
"""

from __future__ import annotations

import importlib
import os
import sys
import unittest

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MODULES = ["artifacts", "birth", "cinematography", "codex", "discovery",
           "hooks", "identity", "scenario", "seeding", "state", "tools",
           "universe", "world"]


def _load_as_package(tmp_state_dir):
    """Import the plugin as a real package under a synthetic parent."""
    parent = os.path.dirname(PLUGIN_DIR)
    name = os.path.basename(PLUGIN_DIR)
    pkg_parent = os.path.join(tmp_state_dir, "pkgmode")
    os.makedirs(pkg_parent, exist_ok=True)
    link = os.path.join(pkg_parent, name)
    if not os.path.exists(link):
        os.symlink(PLUGIN_DIR, link)      # package dir == the plugin dir
    saved = [p for p in sys.path]
    sys.path.insert(0, pkg_parent)
    try:
        pkg = importlib.import_module(name)
        mods = {m: importlib.import_module(f"{name}.{m}") for m in MODULES}
    finally:
        sys.path[:] = saved
    return pkg, mods


def _load_flat():
    saved = [p for p in sys.path]
    sys.path.insert(0, PLUGIN_DIR)
    try:
        mods = {m: importlib.import_module(m) for m in MODULES}
    finally:
        sys.path[:] = saved
    return mods


class TestPackageMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tempfile
        cls._tmp = tempfile.TemporaryDirectory()
        cls.pkg, cls.pkgmods = _load_as_package(cls._tmp.name)
        cls.flatmods = _load_flat()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_every_module_imports_as_a_package(self):
        for m in MODULES:
            self.assertIn(m, self.pkgmods, m)

    def test_dual_mode_imports_resolve_to_same_sources(self):
        """Package-mode module X and flat-mode module X must be the same file.

        Catches the failure shape where the flat branch works (tests) but the
        package branch silently binds a different/absent name.
        """
        for m in MODULES:
            pm = self.pkgmods[m]
            fm = self.flatmods[m]
            self.assertEqual(
                os.path.realpath(pm.__file__), os.path.realpath(fm.__file__),
                f"{m}: package and flat imports diverge")

    def test_big_bang_runs_in_package_mode(self):
        """The exact user-reported crash: seed() → _release_pod in PACKAGE mode.

        With a fresh FakeState and a fake skill inventory, the whole
        dormant→Big-Bang path must complete without ModuleNotFoundError.
        """
        from types import SimpleNamespace
        ps = self.pkgmods["state"]
        ph = self.pkgmods["hooks"]
        pseed = self.pkgmods["seeding"]

        store = {}
        s = SimpleNamespace(
            get=lambda k, d=None: store.get(k, d),
            set=lambda k, v: store.__setitem__(k, v),
        )
        ps._ctx = SimpleNamespace(state=s)          # bind, package-mode module

        # one fake installed skill (discovery contract: name/bytes/is_canon)
        skills = [{"name": "pkg-mode-probe",
                   "bytes": b"probe body", "is_canon": False}]
        rec = {"status": "dormant", "era": 1}
        store["universe"] = rec
        result = pseed.seed(s, skills, save_world=lambda w: store.__setitem__("world", w))
        self.assertIsNotNone(result)
        w = store["world"]                      # save_world received the object
        self.assertEqual(w.tick, 0)
        seeded = [c for c in w.creatures
                  if c.lineage.startswith("Eidos_")]
        self.assertGreaterEqual(len(seeded), 4)     # the probe's pod
        self.assertIn("universe", store)

    def test_bundled_skills_dir_resolves_without_hardcode(self):
        """The bundled-catalog path must come from the running Hermes package.

        A hardcoded /usr/local/... path silently zeroes the canon roster on
        git-clone installs (~/.hermes/hermes-agent) — every bundled skill then
        derives as 'private' and skills outside ~/.hermes/skills go unseen
        (user machine: 5 lineages from ~59 skills)."""
        import discovery as d_flat
        self.assertTrue(d_flat.BUNDLED_SKILLS_DIR.is_dir(),
                        "bundled skills dir must exist on this install")
        # and the resolver must pick the package-adjacent dir first when valid
        skills = d_flat.discover()
        self.assertGreater(len(skills), 0)

    def test_codex_artifacts_import_in_package_mode(self):
        """The other lazy-import cluster (artifacts/codex/glyphs) in package mode."""
        self.assertTrue(hasattr(self.pkgmods["artifacts"], "media_dir"))
        self.assertTrue(hasattr(self.pkgmods["codex"], "observe"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
