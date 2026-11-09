import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import state as vstate  # noqa: E402
import hooks as vhooks  # noqa: E402


class _Store(dict):
    def set(self, k, v): self[k] = v
    def save(self): pass


class _Ctx:
    def __init__(self, d): self.state = _Store(d)
    def save_session(self, *a, **k): pass


class TestSameTurnRelay(unittest.TestCase):
    """VIV-36b: a milestone queued DURING a turn (Big Bang on skill
    creation) delivers in the SAME turn via transform_tool_result —
    no 'one more message' needed."""

    def test_transform_appends_and_pops_milestone(self):
        vstate.bind(_Ctx({"pending_narration_milestones":
                          ["🌌 Universe born (era 8)."]}))
        out = vhooks._on_transform_tool_result(
            tool_name="skill_manage", result='{"ok": true}')
        self.assertIn("STORY BEAT", out)
        self.assertIn("Universe born", out)
        self.assertIn('{"ok": true}', out)
        # popped: a second transform (next tool same turn) gets nothing
        self.assertIsNone(vhooks._on_transform_tool_result(
            tool_name="anything", result="x"))
        # and the next turn's pre_llm pop is empty too
        self.assertIsNone(vstate.pop_narration())

    def test_no_milestone_no_transform(self):
        vstate.bind(_Ctx({}))
        self.assertIsNone(vhooks._on_transform_tool_result(
            tool_name="skill_manage", result="plain"))


if __name__ == "__main__":
    unittest.main()
