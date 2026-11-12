"""Phase 2 security: the plugin resolves the RUNNING profile's dirs.

skill_content used to hardcode ``Path.home()/.hermes/skills``, so a
non-default Hermes profile read the DEFAULT profile's skills. The
delivery trace had the same disease (it wrote into the default profile's
tree). The resolver now walks bound data dir -> $HERMES_HOME -> home
fallback, and an authoritative source (bound dir or env) ends the search
even when it has no skills dir yet, so a profile can never leak another
profile's skills just because it has none of its own.
"""
from __future__ import annotations

import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import delivery_trace as dt    # noqa: E402
import state as vstate         # noqa: E402


def _skill(base: Path, name: str, body: str) -> None:
    d = base / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"# {name}\n\n{body}\n", encoding="utf-8")


class _Homes:
    """Pin $HERMES_HOME and Path.home for one test, restore both after."""

    def __init__(self, hermes_home=None, path_home=None):
        self.hermes_home = hermes_home
        self.path_home = path_home

    def __enter__(self):
        self._old_env = os.environ.get("HERMES_HOME")
        self._old_home = Path.home
        if self.hermes_home is not None:
            os.environ["HERMES_HOME"] = str(self.hermes_home)
        else:
            os.environ.pop("HERMES_HOME", None)
        if self.path_home is not None:
            Path.home = lambda: Path(self.path_home)  # noqa: E731
        return self

    def __exit__(self, *a):
        if self._old_env is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = self._old_env
        Path.home = self._old_home


def _bind(data_dir=None):
    """Bind a minimal ctx (with an optional data_dir); returns the old ctx."""
    old = vstate._ctx
    state_obj = types.SimpleNamespace(
        get=lambda k, d=None: None, set=lambda k, v: None)
    if data_dir is not None:
        state_obj.data_dir = str(data_dir)
    vstate._ctx = types.SimpleNamespace(state=state_obj)
    return old


class TestSkillsDirResolution(unittest.TestCase):
    def test_hermes_home_env_beats_the_default_home(self):
        with tempfile.TemporaryDirectory() as a, \
                tempfile.TemporaryDirectory() as b:
            _skill(Path(a), "target-skill", "from HERMES_HOME")
            _skill(Path(b) / ".hermes", "target-skill", "from the default")
            old = _bind(None)
            try:
                with _Homes(hermes_home=a, path_home=b):
                    got = vstate.skill_content("target-skill")
            finally:
                vstate._ctx = old
            self.assertIsNotNone(got)
            self.assertIn("from HERMES_HOME", got)

    def test_the_bound_data_dir_wins_over_the_env(self):
        with tempfile.TemporaryDirectory() as bound_home, \
                tempfile.TemporaryDirectory() as env_home:
            _skill(Path(bound_home), "target-skill",
                   "from the bound profile")
            _skill(Path(env_home), "target-skill", "from HERMES_HOME")
            old = _bind(Path(bound_home) / "plugin-data" / "vivarium")
            try:
                with _Homes(hermes_home=env_home, path_home=bound_home):
                    got = vstate.skill_content("target-skill")
            finally:
                vstate._ctx = old
            self.assertIn("from the bound profile", got)

    def test_a_bound_profile_without_skills_never_leaks_the_default(self):
        with tempfile.TemporaryDirectory() as bound_home, \
                tempfile.TemporaryDirectory() as decoy:
            (Path(bound_home) / "plugin-data" / "vivarium").mkdir(parents=True)
            _skill(Path(decoy) / ".hermes", "target-skill",
                   "from the default")
            old = _bind(Path(bound_home) / "plugin-data" / "vivarium")
            try:
                with _Homes(hermes_home=None, path_home=decoy):
                    self.assertIsNone(vstate.skill_content("target-skill"))
            finally:
                vstate._ctx = old

    def test_unbound_without_env_falls_back_to_the_home(self):
        with tempfile.TemporaryDirectory() as home:
            _skill(Path(home) / ".hermes", "target-skill", "from the home")
            old = _bind(None)
            try:
                with _Homes(hermes_home=None, path_home=home):
                    got = vstate.skill_content("target-skill")
            finally:
                vstate._ctx = old
            self.assertIn("from the home", got)


class TestDeliveryTracePath(unittest.TestCase):
    def test_the_bound_data_dir_hosts_the_log_next_to_the_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "plugin-data" / "vivarium"
            old = _bind(data_dir)
            try:
                dt.log("probe", stage="bound")
                self.assertTrue((data_dir / "delivery.log").exists())
                self.assertIn("probe", dt.tail())
            finally:
                vstate._ctx = old

    def test_hermes_home_env_places_the_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = _bind(None)
            try:
                with _Homes(hermes_home=tmp, path_home=tmp):
                    dt.log("probe", stage="env")
                    p = Path(tmp) / "plugin-data" / "vivarium" / "delivery.log"
                    self.assertTrue(p.exists())
            finally:
                vstate._ctx = old

    def test_the_plugin_data_override_still_wins_over_the_home_fallback(self):
        with tempfile.TemporaryDirectory() as a, \
                tempfile.TemporaryDirectory() as b:
            old = _bind(None)
            old_pd = os.environ.get("HERMES_PLUGIN_DATA")
            os.environ["HERMES_PLUGIN_DATA"] = a
            try:
                with _Homes(hermes_home=None, path_home=b):
                    dt.log("probe", stage="override")
                    self.assertTrue((Path(a) / "delivery.log").exists())
            finally:
                vstate._ctx = old
                if old_pd is None:
                    os.environ.pop("HERMES_PLUGIN_DATA", None)
                else:
                    os.environ["HERMES_PLUGIN_DATA"] = old_pd


class TestTempSkillsHarness(unittest.TestCase):
    """The shared skills harness must pin BOTH knobs the resolver reads.

    TempSkills used to patch only Path.home; with $HERMES_HOME set on the
    host (every Hermes host) the env source is authoritative and the fake
    skill was invisible: 7 harness-dependent failures in test_birth and
    test_viv104, not security regressions. This guard keeps the harness
    honest without needing HERMES_HOME to be set outside.
    """

    def test_tempskills_pins_and_restores_hermes_home(self):
        from test_birth import TempSkills
        old_env = os.environ.get("HERMES_HOME")
        old_ctx = vstate._ctx
        vstate._ctx = None                    # force the env source, not a bind
        try:
            with TempSkills("harness-probe-skill", "probe body one") as ts:
                self.assertEqual(
                    Path(os.environ["HERMES_HOME"]),
                    Path(ts.tmp.name) / ".hermes")
                self.assertIn("probe body one",
                              vstate.skill_content("harness-probe-skill"))
            self.assertEqual(os.environ.get("HERMES_HOME"), old_env)
        finally:
            vstate._ctx = old_ctx
            if old_env is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = old_env


if __name__ == "__main__":
    unittest.main()
