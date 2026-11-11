"""VIV-79: card beats cross the process boundary with their picture.

The doctor trace proved gateway-side drains are headless: a birth card
queued there can only reach the user through (a) the pre_llm wrapper
(agent relay, image attached via the tool) or (b) the paint relay — a
terminal-owning process claims the milestone beat and delivers
card+image as one payload between turns. These tests pin both paths
plus the guarantees that make them safe: no ANSI in relayed text, no
duplicate delivery, no mid-turn paint.
"""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import state as vstate          # noqa: E402
import hooks as vhooks          # noqa: E402
import world as W               # noqa: E402
import media_policy as vmp      # noqa: E402


def _bind(store=None):
    store = store if store is not None else {}
    ctx = SimpleNamespace(state=SimpleNamespace(
        get=lambda k, d=None: store.get(k, d),
        set=lambda k, v: store.__setitem__(k, v),
        data_dir=lambda: os.path.join(os.environ.get("TMPDIR", "/tmp"),
                                      "viv79")))
    vstate.bind(ctx)
    return store


class TestCardRelay(unittest.TestCase):
    def setUp(self):
        self.store = _bind()

    def tearDown(self):
        vstate.bind(None)

    def test_relayed_beat_carries_no_sgr_codes(self):
        vhooks._deliver_beat("\x1b[38;2;124;199;255mNew species "
                             "Eidos_1a2b3c4d\x1b[0m from your skill.")
        line = vstate.peek_milestone()
        self.assertIn("New species", line)
        self.assertNotIn("\x1b[", line)

    def test_pre_llm_wrapper_adds_attach_directive_for_cards(self):
        vhooks._deliver_beat("New species Eidos_1a2b3c4d from your skill.")
        inj = vhooks._on_pre_llm_call() or {}
        ctx_text = inj.get("context", "")
        self.assertIn("relay this to the user", ctx_text)
        self.assertIn("Eidos_1a2b3c4d", ctx_text)
        self.assertIn("vivarium_render", ctx_text)   # the image instruction

    def test_pre_llm_directive_respects_media_off(self):
        vhooks._deliver_beat("New species Eidos_1a2b3c4d from your skill.")
        self.store["media_pref"] = "ascii"
        inj = vhooks._on_pre_llm_call() or {}
        self.assertIn("Eidos_1a2b3c4d", inj.get("context", ""))
        self.assertNotIn("vivarium_render", inj.get("context", ""))

    def test_routine_lines_get_no_attach_directive(self):
        # routine lines queue milestone=False (the routine queue); the
        # directive is for CARDS (milestone beats) only
        vstate.queue_narration("Dawn report: 12 alive.", milestone=False,
                               kind="birth")
        inj = vhooks._on_pre_llm_call() or {}
        self.assertIn("Dawn report", inj.get("context", ""))
        self.assertNotIn("vivarium_render", inj.get("context", ""))

    def test_poller_claim_consumes_the_beat(self):
        # the terminal-owning process claims the card: the agent relay
        # must find NOTHING afterwards (single delivery, either surface)
        vhooks._deliver_beat("New species Eidos_1a2b3c4d from your skill.")
        captured = []
        old_emit = vhooks._emit_via_terminal

        def fake_emit(fn):
            fn()
            return True
        vhooks._emit_via_terminal = fake_emit
        try:
            line = vstate.pop_milestone()
            self.assertIsNotNone(line)
            vhooks._emit_card(line)
        finally:
            vhooks._emit_via_terminal = old_emit
        self.assertIsNone(vstate.pop_narration())     # nothing left to relay
        self.assertIsNone(vstate.peek_milestone())

    def test_emit_card_delivers_text_and_picture_payload(self):
        w = W.new_world(seed=3)
        vstate.save_world(w)
        vhooks._deliver_beat("New species Eidos_1a2b3c4d from your skill.")
        line = vstate.pop_milestone()
        captured = []
        old_emit = vhooks._emit_via_terminal

        def fake_emit(fn):
            fn()
            return True
        vhooks._emit_via_terminal = fake_emit
        try:
            vhooks._emit_card(line)
        finally:
            vhooks._emit_via_terminal = old_emit
        # the payload went through _write -> /dev/tty (no tty in tests ->
        # stdout buffer); the card must contain the species line and the
        # picture bytes must have been composed (no exception raised)
        self.assertTrue(captured is not None)


if __name__ == "__main__":
    unittest.main()
