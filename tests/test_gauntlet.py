"""VIV-13 Gauntlet: challenge-code export -> race entry -> scoreboard."""
import json
import os
import tempfile
import unittest
from types import SimpleNamespace

import state as vstate
import tools
import world as W


def _live_state(store):
    tmp = tempfile.mkdtemp()
    w = W.new_world(seed=5)
    ctx = SimpleNamespace(state=SimpleNamespace(
        get=lambda k, d=None: store.get(k, d),
        set=lambda k, v: store.__setitem__(k, v),
        data_dir=lambda: tmp))
    vstate.bind(ctx)
    return ctx, w


class TestExport(unittest.TestCase):
    def test_export_lists_species_codes(self):
        store = {"universe": {"status": "live", "era": 1},
                 "births": {"my-skill": {
                     "eidos": "Eidos_abc123", "day": "2026-11-06",
                     "tick": 90, "pod": 4, "digest_fp": "abcd1234",
                     "era": 1,
                     "genome": {"forage": 0.8, "aggression": 0.2,
                                "metabolism_mult": 1.0, "sense": 0.5,
                                "mutate": 0.1, "hue": 0.3}}}}
        _live_state(store)
        out = tools._export_text([])
        self.assertIn("Eidos_abc123", out)
        self.assertIn("my-skill", out)
        self.assertIn("VIV1", out)

    def test_export_one_species_shows_code(self):
        store = {"universe": {"status": "live", "era": 1},
                 "births": {"sk": {"eidos": "Eidos_aaa111",
                                   "genome": {"forage": 0.9,
                                              "aggression": 0.1,
                                              "metabolism_mult": 1.0,
                                              "sense": 0.4,
                                              "mutate": 0.1, "hue": 0.2}}}}
        _live_state(store)
        out = tools._export_text(["sk"])
        self.assertIn("Eidos_aaa111", out)
        code = [l for l in out.splitlines() if l.startswith("VIV1")]
        self.assertEqual(len(code), 1)

    def test_export_unknown_and_ambiguous(self):
        store = {"universe": {"status": "live", "era": 1},
                 "births": {"alpha-one": {"eidos": "Eidos_1",
                                          "genome": {"forage": 0.5, "aggression": 0.5,
                                                     "metabolism_mult": 1.0,
                                                     "sense": 0.5, "mutate": 0.1,
                                                     "hue": 0.5}},
                            "alpha-two": {"eidos": "Eidos_2",
                                          "genome": {"forage": 0.5, "aggression": 0.5,
                                                     "metabolism_mult": 1.0,
                                                     "sense": 0.5, "mutate": 0.1,
                                                     "hue": 0.5}}}}
        _live_state(store)
        self.assertIn("Unknown species", tools._export_text(["nope"]))
        self.assertIn("Ambiguous name", tools._export_text(["alpha"]))
        one = tools._export_text(["alpha-one"])
        self.assertIn("Eidos_1", one)

    def test_export_pre_viv13_species_flagged(self):
        store = {"universe": {"status": "live", "era": 1},
                 "births": {"old": {"eidos": "Eidos_old"}}}
        _live_state(store)
        out = tools._export_text([])
        self.assertIn("code unavailable", out)

    def test_export_never_leaks_skill_content(self):
        store = {"universe": {"status": "live", "era": 1},
                 "births": {"secret-skill-name": {
                     "eidos": "Eidos_x", "genome": {"forage": 0.5,
                     "aggression": 0.5, "metabolism_mult": 1.0,
                     "sense": 0.5, "mutate": 0.1, "hue": 0.5}}}}
        _live_state(store)
        out = tools._export_text([])
        self.assertIn("secret-skill-name", out)  # user's OWN list: names OK
        self.assertNotIn("UNIVERSE_KEY", out)


class TestGauntletFlow(unittest.TestCase):
    def test_export_then_race_end_to_end(self):
        """The Gauntlet loop: born species -> code -> race -> scoreboard."""
        genome = {"forage": 0.95, "aggression": 0.1, "metabolism_mult": 0.9,
                  "sense": 0.6, "mutate": 0.1, "hue": 0.4}
        store = {"universe": {"status": "live", "era": 1},
                 "births": {"champ": {"eidos": "Eidos_g13",
                                      "genome": genome}}}
        _live_state(store)
        out = tools._export_text(["champ"])
        code = next(l for l in out.splitlines() if l.startswith("VIV1"))
        # race it (single entrant vs the field)
        text = tools._cmd(f"race gauntlet-seed {code}")
        self.assertIn("Scenario finished", text)
        self.assertIn("X", text)          # digest-derived entrant label
        self.assertIn("SCEN1", text)      # shareable race code echoed

    def test_race_share_code_roundtrips(self):
        import scenario as vscen
        code = tools._cmd("race probe-seed").split("SCEN1", 1)
        self.assertEqual(len(code), 2)    # a share code was emitted
        scode = "SCEN1" + code[1].split("\n")[0]
        spec = vscen.decode_scenario(scode)
        self.assertIsNotNone(spec)
        self.assertEqual(spec["seed"], "probe-seed")


if __name__ == "__main__":
    unittest.main()
