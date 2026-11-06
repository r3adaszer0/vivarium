"""VIV-21 tests: scenario protocol — deterministic, shareable experiments."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scenario as SC
import world as W


def _code(forage=1.0, aggression=0.4, metabolism=1.0, sense=2.0, mutate=1.0, hue=0.3):
    """Build a VIV1 challenge code from trait values (test helper)."""
    import state as S
    genome = {"forage": forage, "aggression": aggression,
              "metabolism_mult": metabolism, "sense": sense,
              "mutate": mutate, "hue": hue}
    return S.encode_genome(genome)


A = _code(hue=0.10, forage=1.6, aggression=0.3)     # grazer line
B = _code(hue=0.75, forage=0.9, aggression=1.4)     # aggressive line
BAD = "SCEN1-not-a-real-code"


class TestScenarioCodes(unittest.TestCase):
    def test_round_trip(self):
        code = SC.encode_scenario("meadow-1", 1200, [A, B])
        spec = SC.decode_scenario(code)
        self.assertIsNotNone(spec)
        self.assertEqual(spec["seed"], "meadow-1")
        self.assertEqual(spec["ticks"], 1200)
        self.assertEqual(spec["contestants"], [A, B])

    def test_malformed_codes_return_none(self):
        for bad in ["", "VIV1abc", "SCEN1", "SCEN1!!!", "SCEN1<anything"]:
            self.assertIsNone(SC.decode_scenario(bad), bad)

    def test_ticks_bounds_enforced(self):
        code = SC.encode_scenario("s", ticks=5, contestants=[])
        self.assertIsNone(SC.decode_scenario(code))     # below minimum
        code = SC.encode_scenario("s", ticks=99999, contestants=[])
        self.assertIsNone(SC.decode_scenario(code))     # above maximum

    def test_max_eight_contestants(self):
        codes = [_code(hue=i / 10) for i in range(9)]
        code = SC.encode_scenario("s", contestants=codes)
        self.assertIsNone(SC.decode_scenario(code))
        code = SC.encode_scenario("s", contestants=codes[:8])
        self.assertIsNotNone(SC.decode_scenario(code))

    def test_scenario_hash_is_public_and_stable(self):
        # same (seed, ticks) -> same digest; NO universe key involved
        self.assertEqual(SC.scenario_hash("meadow-1", 1200),
                         SC.scenario_hash("meadow-1", 1200))
        self.assertNotEqual(SC.scenario_hash("meadow-1", 1200),
                            SC.scenario_hash("meadow-2", 1200))
        self.assertNotEqual(SC.scenario_hash("meadow-1", 1200),
                            SC.scenario_hash("meadow-1", 1201))


class TestScenarioDish(unittest.TestCase):
    def test_build_dish_is_bit_identical_across_runs(self):
        spec = SC.decode_scenario(SC.encode_scenario("meadow-1", 400, [A, B]))
        w1 = SC.build_dish(spec)
        w2 = SC.build_dish(spec)
        self.assertEqual(w1.to_dict(), w2.to_dict())

    def test_different_seed_different_dish(self):
        s1 = SC.decode_scenario(SC.encode_scenario("alpha", 400, [A]))
        s2 = SC.decode_scenario(SC.encode_scenario("beta", 400, [A]))
        self.assertNotEqual(SC.build_dish(s1).to_dict(),
                            SC.build_dish(s2).to_dict())

    def test_contestants_landed_with_pods_and_labels(self):
        spec = SC.decode_scenario(SC.encode_scenario("meadow-1", 400, [A, B]))
        w = SC.build_dish(spec)
        counts = {}
        for c in w.creatures:
            counts[c.lineage] = counts.get(c.lineage, 0) + 1
        labels = {lab for lab, _ in SC.entry_digests(spec)}
        self.assertEqual(len(labels), 2)                 # distinct labels
        for lab in labels:
            self.assertEqual(counts.get(lab), SC.POD_PER_CONTESTANT)

    def test_invalid_contestant_codes_are_skipped(self):
        spec = SC.decode_scenario(SC.encode_scenario("meadow-1", 400, [A, BAD]))
        self.assertEqual(len(SC.entry_digests(spec)), 1)

    def test_no_universe_key_needed(self):
        # scenario building must not touch plugin state at all
        spec = SC.decode_scenario(SC.encode_scenario("meadow-1", 400, [A]))
        w = SC.build_dish(spec)     # no FakeState, no key, no error
        # 24 genesis founders minus settling losses, + one 4-member pod
        label = SC.entry_digests(spec)[0][0]
        pods = sum(1 for c in w.creatures if c.lineage == label)
        self.assertEqual(pods, SC.POD_PER_CONTESTANT)
        self.assertGreater(len(w.creatures), SC.POD_PER_CONTESTANT)


class TestScenarioRun(unittest.TestCase):
    def test_short_run_scores_and_ranks(self):
        spec = SC.decode_scenario(SC.encode_scenario("meadow-1", 200, [A, B]))
        res = SC.run_scenario(spec)
        self.assertEqual(res["ticks"], 200)
        self.assertTrue(res["scores"])
        # ranking is score-descending, name-ascending as tie-break
        self.assertEqual(res["ranking"],
                         sorted(res["ranking"], key=lambda k: (-res["scores"][k], k)))
        # score = area under curve: always >= peak (curve of >= 1 for >= peak ticks)
        for name, curve in res["curves"].items():
            self.assertGreaterEqual(res["scores"][name], max(curve))

    def test_extinct_strain_scores_zero_or_late(self):
        # an engineered liar strain: aggression max, forage min — should die fast
        liar = _code(hue=0.99, forage=0.2, aggression=2.0, metabolism=1.6)
        spec = SC.decode_scenario(SC.encode_scenario("meadow-1", 300, [liar]))
        res = SC.run_scenario(spec)
        label = SC.entry_digests(spec)[0][0]
        if label in res["curves"]:
            curve = res["curves"][label]
            self.assertLess(sum(curve), sum(v for k, v in res["scores"].items()
                                            if k != label) + 1)

    def test_results_deterministic(self):
        spec = SC.decode_scenario(SC.encode_scenario("meadow-1", 200, [A, B]))
        r1 = SC.run_scenario(SC.decode_scenario(SC.encode_scenario("meadow-1", 200, [A, B])))
        r2 = SC.run_scenario(SC.decode_scenario(SC.encode_scenario("meadow-1", 200, [A, B])))
        self.assertEqual(r1["scores"], r2["scores"])
        self.assertEqual(r1["ranking"], r2["ranking"])

    def test_format_results_plain_language(self):
        spec = SC.decode_scenario(SC.encode_scenario("meadow-1", 200, [A, B]))
        out = SC.format_results(SC.run_scenario(spec))
        self.assertIn("Scenario finished", out)
        self.assertIn("score", out)


class TestSlashRace(unittest.TestCase):
    def test_race_via_slash_command(self):
        """End-to-end: /vivarium race <seed> <codes...> through tools._cmd."""
        import tools
        out = tools._cmd(f"race slash-test {A} {B}")
        self.assertIn("Scenario finished", out)
        # both contestants appear in the scoreboard
        labels = {lab for lab, _ in SC.entry_digests(
            SC.decode_scenario(SC.encode_scenario("slash-test", 1200, [A, B])))}
        for lab in labels:
            self.assertIn(lab, out)

    def test_race_usage_and_bad_code(self):
        import tools
        self.assertIn("Usage:", tools._cmd("race"))
        self.assertIn("Invalid scenario code", tools._cmd("race SCEN1garbage"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
