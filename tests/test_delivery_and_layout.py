import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hooks as vhooks  # noqa: E402
import termrender as vterm  # noqa: E402


class _Ctx:
    def __init__(self):
        self.hooks = {}

    def register_hook(self, name, fn):
        self.hooks[name] = fn

    def register_tool(self, *a, **k):
        pass

    def register_command(self, *a, **k):
        pass


class TestDeliveryRegistration(unittest.TestCase):
    """VIV-40: a handler that exists is NOT a handler that runs. The
    transform_tool_result handler existed and plugin.yaml listed it, but
    register_hooks() never called ctx.register_hook for it, so every
    story beat waited for the next turn's pre_llm (the exact bug the
    user hit twice). The registration is the fix; this test pins it."""

    def test_register_hooks_registers_transform_tool_result(self):
        ctx = _Ctx()
        vhooks.register_hooks(ctx)
        self.assertIn("transform_tool_result", ctx.hooks)
        self.assertIn("on_skill_lifecycle", ctx.hooks)
        self.assertIn("pre_llm_call", ctx.hooks)
        self.assertIn("post_tool_call", ctx.hooks)


class TestImageRowReservation(unittest.TestCase):
    """VIV-39: the inline image must reserve its rows, or the reply and
    reasoning print underneath it (user: 'the dish image is on top of
    the reasoning and the hermes reply')."""

    def test_emit_image_raw_reserves_image_rows(self):
        import tempfile
        from PIL import Image
        captured = {}

        def fake_kitty(png_bytes):
            return b"\x1b_Gfake"

        class FakeTty:
            def __init__(self): self.data = b""
            def write(self, b): self.data += b
            def __enter__(self): return self
            def __exit__(self, *a): return False

        orig_kitty = vterm._kitty_escape
        orig_open = os.open
        orig_close = os.close
        orig_write = os.write
        vterm._kitty_escape = fake_kitty
        try:
            fd = 99
            def fake_open(path, flags, *a):
                if path == "/dev/tty":
                    return fd
                return orig_open(path, flags, *a)
            def fake_write(f, data):
                if f == fd:
                    captured["data"] = data
                    return len(data)
                return orig_write(f, data)
            os.open = fake_open
            os.write = fake_write
            os.close = lambda f: None
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fh:
                path = fh.name
            img = Image.new("RGB", (300, 300), (10, 20, 10))
            img.save(path)
            note = vterm.emit_image_raw(path, force="kitty")
            os.unlink(path)
        finally:
            vterm._kitty_escape = orig_kitty
            os.open = orig_open
            os.write = orig_write
            os.close = orig_close
        self.assertIn("emitted", note)
        data = captured.get("data", b"")
        # Deterministic envelope: save cursor, reserve the block with real
        # newlines, restore, paint the image into the block, move to its
        # bottom so later text flows below the picture.
        self.assertTrue(data.startswith(b"\x1b7" + b"\n" * 20 + b"\x1b8"))
        self.assertIn(b"\x1b_Gfake", data)
        self.assertTrue(data.endswith(b"\x1b[20B"))


if __name__ == "__main__":
    unittest.main()
