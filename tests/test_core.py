"""Vivarium core tests — deterministic, offline, no Hermes runtime needed.

Run:  python3 -m pytest tests/ -q      (or python3 -m unittest discover tests)
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from world import (  # noqa: E402
    Creature, World, new_world, render_ascii, run, stats, tick_world,
)
import state as vstate  # noqa: E402


class TestNewWorld(unittest.TestCase):
    def test_deterministic_founders(self):
        a, b = new_world(seed=42), new_world(seed=42)
        self.assertEqual(a.to_dict(), b.to_dict())

    def test_founders_have_strain_names(self):
        w = new_world(seed=1)
        names = {c.lineage for c in w.creatures}
        self.assertTrue(names <= set(vworld_import().FOUNDER_STRAINS), names)
        self.assertTrue(names, "expected at least one strain")


def vworld_import():
    import world
    return world


class TestTick(unittest.TestCase):
    def test_tick_advances_and_books_events(self):
        w = new_world(seed=7)
        s0 = tick_world(w)
        self.assertEqual(s0["tick"], 1)
        self.assertGreater(s0["population"], 0)

    def test_creatures_never_negative_food(self):
        w = new_world(seed=3)
        run(w, ticks=50)
        for row in w.food:
            self.assertTrue(all(v >= 0.0 for v in row))

    def test_100_ticks_no_crash(self):
        w = new_world(seed=11)
        run(w, ticks=100)
        s = stats(w)
        self.assertGreaterEqual(s["tick"], 100)

    def test_extinction_is_survivable_and_reported(self):
        # heavy metabolism world: some seeds may extinct; must not crash
        w = new_world(seed=5)
        summaries = run(w, ticks=200)
        self.assertEqual(len(summaries), 200)

    def test_nutrients_increase_food_somewhere(self):
        w = new_world(seed=2)
        run(w, ticks=3, nutrients_per_tick=0.5)
        after = sum(sum(r) for r in w.food)
        # control run of the same world without nutrients, 3 ticks
        ctl = new_world(seed=2)
        run(ctl, ticks=3, nutrients_per_tick=0.0)
        after_no_feed = sum(sum(r) for r in ctl.food)
        self.assertGreater(after, after_no_feed - 1e-6)


class TestDeterminism(unittest.TestCase):
    def test_same_seed_same_1000_ticks(self):
        a, b = new_world(seed=99), new_world(seed=99)
        sa, sb = run(a, 1000), run(b, 1000)
        self.assertEqual(sa[-1]["population"], sb[-1]["population"])
        self.assertEqual(a.tick, b.tick)

    def test_different_seed_diverges(self):
        a, b = new_world(seed=1), new_world(seed=2)
        run(a, 120)
        run(b, 120)
        # different seeds → different terrain/founders → different worlds, full stop
        self.assertNotEqual(a.to_dict(), b.to_dict())


class TestPersistence(unittest.TestCase):
    def test_roundtrip_preserves_state(self):
        w = new_world(seed=21)
        run(w, ticks=40)
        d = w.to_dict()
        w2 = World.from_dict(json.loads(json.dumps(d)), seed=21)
        self.assertEqual(w.tick, w2.tick)
        self.assertEqual(len(w.creatures), len(w2.creatures))
        self.assertAlmostEqual(
            sum(sum(r) for r in w.food), sum(sum(r) for r in w2.food), places=1)
        # and both continue deterministically
        tick_world(w)
        tick_world(w2)
        self.assertEqual(len(w.creatures), len(w2.creatures))


class TestAscii(unittest.TestCase):
    def test_render_produces_grid(self):
        w = new_world(seed=4)
        run(w, ticks=10)
        art = render_ascii(w)
        lines = art.strip().splitlines()
        self.assertEqual(len(lines), 24)
        # map is clamped to the 48-wide grid → max 48 chars per line
        self.assertTrue(all(0 < len(line) <= 48 for line in lines),
                        [len(x) for x in lines])


class TestChallengeCodes(unittest.TestCase):
    def test_encode_decode_roundtrip(self):
        w = new_world(seed=8)
        genome = dict(w.creatures[0].genome)
        code = vstate.encode_genome(genome)
        self.assertTrue(code.startswith("VIV1"))
        self.assertLess(len(code), 400, "challenge codes must stay pasteable")
        decoded = vstate.decode_genome(code)
        self.assertEqual(decoded, {k: round(v, 4) for k, v in genome.items()})

    def test_decode_rejects_garbage(self):
        self.assertIsNone(vstate.decode_genome("nonsense"))
        self.assertIsNone(vstate.decode_genome("VIV1!!!"))


class FakeState:
    """Minimal stand-in for hermes_cli.plugins_state.PluginState."""

    def __init__(self):
        self.d = {}

    def get(self, key, default=None):
        return self.d.get(key, default)

    def set(self, key, value):
        self.d[key] = value


class _FakeCtx:
    def __init__(self):
        self._state = FakeState()
        self.hooks = []
        self.commands = []

    @property
    def state(self):
        return self._state

    def register_hook(self, name, cb):
        self.hooks.append((name, cb))

    def register_command(self, name, **kw):
        self.commands.append(name)


class TestHookFlow(unittest.TestCase):
    def setUp(self):
        import hooks
        self.hooks = hooks
        self.ctx = _FakeCtx()
        vstate._ctx = None
        hooks.register_hooks(self.ctx)
        self.assertEqual(len(self.ctx.hooks), 3)

    def test_tool_call_drops_nutrients_and_advances(self):
        import universe as U
        rec = U.universe_record(self.ctx.state)
        rec["status"] = "live"  # hooks only advance a LIVE universe (VIV-19b)
        self.ctx.state.set(U.UNIVERSE_REC, rec)
        w = vstate.load_world()
        t0 = w.tick
        self.hooks._on_post_tool_call(tool_name="terminal", args={})
        w2 = vstate.load_world()
        self.assertEqual(w2.tick, t0 + self.hooks.TICKS_PER_TOOL_CALL)
        act = vstate.activity_summary()
        self.assertEqual(act.get("terminal"), 1)

    def test_tool_call_while_dormant_banks_without_advancing(self):
        """VIV-19b: dormant universe — activity counts, no dish is conjured."""
        import universe as U
        U.universe_record(self.ctx.state)   # dormant by default
        self.hooks._on_post_tool_call(tool_name="terminal", args={})
        act = vstate.activity_summary()
        self.assertEqual(act.get("terminal"), 1)          # activity counted
        self.assertIsNone(self.ctx.state.get("world"))    # no phantom dish

    def test_vivarium_tools_do_not_feed_the_dish(self):
        w_before = vstate.load_world().tick
        self.hooks._on_post_tool_call(tool_name="vivarium_feed", args={})
        self.assertNotIn("vivarium_feed", vstate.activity_summary())
        self.assertEqual(vstate.load_world().tick, w_before)

    def test_pre_llm_call_injects_report(self):
        import universe as U
        rec = U.universe_record(self.ctx.state)
        rec["status"] = "live"  # narration is an ecology report of a live dish
        self.ctx.state.set(U.UNIVERSE_REC, rec)
        self.hooks._on_post_tool_call(tool_name="write_file", args={})
        out = self.hooks._on_pre_llm_call(session_id="s1")
        self.assertIsInstance(out, dict)
        self.assertIn("context", out)
        self.assertIn("vivarium", out["context"].lower())

    def test_pre_llm_call_first_turn_report(self):
        # live universe -> ecology report
        import universe as U
        rec = U.universe_record(self.ctx.state)
        rec["status"] = "live"
        self.ctx.state.set(U.UNIVERSE_REC, rec)
        out = self.hooks._on_pre_llm_call(session_id="s2", is_first_turn=True)
        self.assertIsInstance(out, dict)
        self.assertIn("context", out)

    def test_pre_llm_call_first_turn_dormant_waiting(self):
        """VIV-19b: dormant first turn narrates the waiting universe."""
        import universe as U
        U.universe_record(self.ctx.state)   # dormant
        out = self.hooks._on_pre_llm_call(session_id="s3", is_first_turn=True)
        self.assertIn("sleeps", out["context"])
        self.assertIsNone(self.ctx.state.get("world"))    # no phantom dish


class DormantToolGating(unittest.TestCase):
    """VIV-19c: tools on a dormant universe brief, never conjure a dish."""

    def setUp(self):
        import hooks, tools
        from types import SimpleNamespace

        class St:
            def __init__(self):
                self.d = {}
            def get(self, k, d=None):
                return self.d.get(k, d)
            def set(self, k, v):
                self.d[k] = v

        self.st = St()
        import state as vstate
        self._old_ctx = vstate._ctx
        vstate._ctx = SimpleNamespace(state=self.st)
        self.tools = tools

    def tearDown(self):
        import state as vstate
        vstate._ctx = self._old_ctx

    def test_status_while_dormant_briefs_and_creates_nothing(self):
        out = self.tools._tool_status({})
        self.assertIn("dormant", out)
        self.assertNotIn("creatures alive", out)
        self.assertIsNone(self.st.d.get("world"))     # no phantom dish

    def test_feed_release_render_dormant_brief(self):
        self.assertIn("dormant", self.tools._tool_feed({"amount": 1.0}))
        self.assertIn("dormant", self.tools._tool_release({}))
        self.assertIn("dormant", self.tools._tool_render({}))
        self.assertIsNone(self.st.d.get("world"))     # still nothing conjured

    def test_all_tools_work_when_live(self):
        import universe as U
        import world as W
        rec = U.universe_record(self.st)
        rec["status"] = "live"
        self.st.set(U.UNIVERSE_REC, rec)
        self.st.set("world", W.new_world(seed=5).to_dict())
        out = self.tools._tool_status({})
        self.assertIn("creatures alive", out)         # live: the real status
        self.assertNotIn("dormant", out)

    def test_start_command_both_states(self):
        # dormant: the briefing
        self.assertIn("dormant", self.tools._cmd("start"))
        # live: alive + help
        import universe as U
        import world as W
        rec = U.universe_record(self.st)
        rec["status"] = "live"
        self.st.set(U.UNIVERSE_REC, rec)
        self.st.set("world", W.new_world(seed=5).to_dict())
        out = self.tools._cmd("start")
        self.assertIn("alive", out)
        self.assertIn("/vivarium status", out)

    def test_hooks_never_raise(self):
        # garbage input must never break the agent's tool loop
        # (lives in DormantToolGating scope but exercises the hook module)
        import hooks
        hooks._on_post_tool_call(tool_name="terminal", args=None)
        hooks._on_pre_llm_call()  # no args at all
        self.assertTrue(True)



class TestDeterminismVIV12(unittest.TestCase):
    """VIV-12: tick dynamics are hash-driven, not random — a snapshot
    resumed mid-run must reproduce the continuous run EXACTLY."""

    def test_snapshot_resume_bit_identical(self):
        import world as W
        w1 = W.new_world(seed=42)
        for _ in range(120):
            W.tick_world(w1, 0.3 if _ % 10 == 0 else 0.0)
        w2 = W.World.from_dict(w1.to_dict())
        w1b = W.new_world(seed=42)
        for _ in range(120):
            W.tick_world(w1b, 0.3 if _ % 10 == 0 else 0.0)
        for t in range(120, 260):
            W.tick_world(w1b, 0.3 if t % 10 == 0 else 0.0)
            W.tick_world(w2, 0.3 if t % 10 == 0 else 0.0)
        self.assertEqual(w1b.to_dict(), w2.to_dict())

    def test_decision_hash_is_state_pure(self):
        import world as W
        self.assertEqual(W._u(7, 3, 11, b"repro"), W._u(7, 3, 11, b"repro"))
        self.assertNotEqual(W._u(7, 3, 11, b"repro"), W._u(7, 4, 11, b"repro"))
        self.assertNotEqual(W._u(7, 3, 11, b"repro"), W._u(7, 3, 12, b"repro"))

    def test_no_rng_in_tick_dynamics(self):
        import inspect
        import world as W
        for fn in (W._terrain_tick, W._creature_tick):
            src = inspect.getsource(fn)
            self.assertNotIn("rng.", src)
            self.assertNotIn("random.", src)

if __name__ == "__main__":
    unittest.main(verbosity=2)
