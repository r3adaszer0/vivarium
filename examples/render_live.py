"""Render the LIVE universe from real plugin state: PNG (GoL-style squares)
+ terminal block map. Lineage-colored: natives by strain, Eidos by genome hue.
"""
from __future__ import annotations

import colorsys
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import universe as U   # noqa: E402
import world as W      # noqa: E402

STRAIN_RGB = {"amber": (222, 170, 60), "violet": (150, 96, 200),
              "jade": (64, 178, 122), "ember": (214, 92, 58)}


def real_state():
    from hermes_cli.plugins_state import PluginState
    return PluginState("vivarium")


def hue_rgb(h, l=0.58, s=0.8):
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return int(r * 255), int(g * 255), int(b * 255)


def main(out_path=None):
    s = real_state()
    d = s.get("world")
    if not d:
        raise SystemExit("no live universe — run make_universe.py first")
    w = W.World.from_dict(d)
    out_path = out_path or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "docs", "dish_render.png")

    CELL, PAD = 6, 1
    size = w.w * (CELL + PAD) + PAD
    bg = (13, 15, 18)
    rows_data = [bytes(bg) * size for _ in range(size)]

    def set_px(px_x, px_y, rgb):
        if 0 <= px_x < size and 0 <= px_y < size:
            off = px_x * 3
            rows_data[px_y] = rows_data[px_y][:off] + bytes(rgb) + rows_data[px_y][off + 3:]

    occ = {}
    for c in w.creatures:
        occ.setdefault((c.x, c.y), []).append(c)

    # lineage-accurate colors: dominant 8 lineages get colors, the long tail grey
    counts = {}
    for c in w.creatures:
        counts[c.lineage] = counts.get(c.lineage, 0) + 1
    top = [l for l, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:8]]
    oldest_hue = {}
    for c in sorted(w.creatures, key=lambda c: c.gid):
        if c.lineage not in oldest_hue:
            oldest_hue[c.lineage] = c.genome["hue"]
    lineage_color = {l: (STRAIN_RGB.get(l) or hue_rgb(oldest_hue[l])) for l in top}

    for y in range(w.h):
        for x in range(w.w):
            f = w.food[y][x] / W.MAX_FOOD
            x0, y0 = PAD + x * (CELL + PAD), PAD + y * (CELL + PAD)
            cs = occ.get((x, y), [])
            if cs:
                dom = cs[0]
                rgb = lineage_color.get(dom.lineage, (200, 200, 200))
                hi = tuple(min(255, v + 70) for v in rgb)
                for dy in range(CELL):
                    for dx in range(CELL):
                        edge = dx in (0, CELL - 1) or dy in (0, CELL - 1)
                        set_px(x0 + dx, y0 + dy, hi if edge else rgb)
            elif f > 0.04:
                dot = 4
                cx0, cy0 = x0 + (CELL - dot) // 2, y0 + (CELL - dot) // 2
                g = int(80 + 140 * f)
                for dy in range(dot):
                    for dx in range(dot):
                        set_px(cx0 + dx, cy0 + dy, (30, g, 36))

    print("\nLEGEND (lineage → color):")
    for lin, rgb in lineage_color.items():
        print(f"  {lin}: rgb{rgb}")

    raw = b"".join(b"\x00" + r for r in rows_data)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    open(out_path, "wb").write(png)
    print(f"PNG: {out_path} ({size}x{size})")

    st = W.stats(w)
    print(f"tick {st['tick']} | pop {st['population']} | lineages: "
          + ", ".join(f"{n}×{c}" for n, c in st["lineages"]))
    print("\nTERMINAL VIEW:")
    print(W.render_ascii(w, cols=64, rows=24))


if __name__ == "__main__":
    main()
