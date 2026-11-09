import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hooks as vhooks  # noqa: E402


class _Ctx:
    def __init__(self):
        self.hooks = {}

    def register_hook(self, name, fn):
        self.hooks[name] = fn

    def register_tool(self, *a, **k):
        pass

    def register_command(self, *a, **k):
        pass


class TestNoInTurnDelivery(unittest.TestCase):
    """VIV-46: beats never ride tool results.

    VIV-36b delivered story beats by appending them to the tool result, so
    the agent's reply carried Vivarium copy. That is exactly the invasion
    the user rejected: Hermes answers the user, Vivarium speaks for
    itself, after the turn.
    """

    def test_transform_tool_result_is_not_registered(self):
        ctx = _Ctx()
        vhooks.register_hooks(ctx)
        self.assertNotIn("transform_tool_result", ctx.hooks)


if __name__ == "__main__":
    unittest.main()
