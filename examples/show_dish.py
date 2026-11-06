#!/usr/bin/env python3
"""Standalone kitty paint probe — run INSIDE kitty:

    python3 ~/.hermes/plugins/vivarium/examples/show_dish.py [png_path]

1. Paints a tiny 64x64 red test square via APC (raw /dev/tty).
2. Sleeps 2s so you SEE whether kitty paints it.
3. Then paints the latest dish PNG (default: newest in media/).

Diagnoses two failure modes:
- no red square  -> kitty never paints from this process (protocol/env issue)
- red square yes, dish missing -> the dish write itself failed (path/format)
"""
import glob
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from termrender import _kitty_escape  # noqa: E402


def write_tty(payload: bytes) -> None:
    try:
        fd = os.open("/dev/tty", os.O_WRONLY)
        try:
            os.write(fd, payload)
        finally:
            os.close(fd)
    except OSError:
        sys.stdout.write(payload.decode("latin-1"))
        sys.stdout.flush()


def tiny_png() -> bytes:
    # 64x64 solid red PNG, hand-built (zlib store)
    import struct
    import zlib

    w = h = 64
    raw = b"".join(b"\x00" + b"\xe7\x3c\x3c" * w for _ in range(h))

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def newest_dish() -> str | None:
    base = os.path.expanduser(
        "~/.hermes/plugin-data/agent-plugin-vivarium-*/media/dish_*.png")
    cands = sorted(glob.glob(base))
    return cands[-1] if cands else None


def main() -> None:
    print("probe: painting 64x64 red square in 1s…", flush=True)
    time.sleep(1)
    write_tty(_kitty_escape(tiny_png(), img_id=77))
    print("\nprobe: red square above? sleeping 2s…", flush=True)
    time.sleep(2)

    path = sys.argv[1] if len(sys.argv) > 1 else newest_dish()
    if not path:
        print("probe: no dish PNG found — run /vivarium render --image first")
        return
    with open(path, "rb") as f:
        png = f.read()
    print(f"probe: painting {path} ({len(png)} bytes)…", flush=True)
    write_tty(_kitty_escape(png, img_id=78))
    print("probe: done — the dish should be painted above. The protocol"
          " now uses f=100 (PNG) + q=2 (no kitty reply), fixing the"
          " earlier EINVAL (f=32 means raw pixels, not PNG) and the"
          " typed-in EINVAL garbage.", flush=True)


if __name__ == "__main__":
    main()
