"""Render the dish as an actual PNG with square cells (GoL-style) + block-ASCII.

Pure stdlib PNG writer (zlib + struct) - no dependencies. Deterministic world rebuild.
"""
from __future__ import annotations
import struct, sys, os, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from demo_lifeform import derive, SKILLS
from world import Creature
import world as W

# ── rebuild the canonical demo world ─────────────────────────────────────────
digest0, *_ = derive(*SKILLS[0])
w = W.new_world(seed=int.from_bytes(digest0[:4], "big"))
lineage_color = {}
STRAIN_RGB = {"amber": (222, 170, 60), "violet": (150, 96, 200),
              "jade": (64, 178, 122), "ember": (214, 92, 58)}
EIDOS_RGB = [(250, 105, 160), (90, 170, 250), (240, 210, 90)]  # the 3 skill species
for i, (name, text) in enumerate(SKILLS):
    _, g, e, gl, *_ = derive(name, text)
    for _ in range(6):
        c = Creature(gid=w.next_gid, genome=dict(g), x=w.rng.randrange(w.w),
                     y=w.rng.randrange(w.h), energy=1.6, lineage=e)
        w.creatures.append(c); w.next_gid += 1
        lineage_color[e] = EIDOS_RGB[i]
W.run(w, ticks=60)
for s, rgb in STRAIN_RGB.items():
    lineage_color.setdefault(s, rgb)

def hue_to_rgb(h):
    import colorsys
    r, g, b = colorsys.hls_to_rgb(h, 0.55, 0.75)
    return int(r * 255), int(g * 255), int(b * 255)

# ── PNG: 48x48 cells -> 6x6 px squares, 2px border between cells ─────────────
CELL, PAD = 6, 1
size = w.w * (CELL + PAD) + PAD
img = bytearray(b"\x00" * (size * 3 * 1))  # placeholder; we build rows directly
rows = []
# background
bg = (14, 16, 20)
row_bg = bytearray()
for _ in range(size):
    row_bg += bytes(bg)
rows_data = []
for py in range(size):
    rows_data.append(bytes(row_bg))

def set_px(px_x, px_y, rgb):
    if 0 <= px_x < size and 0 <= px_y < size:
        off = px_x * 3  # offset within the row
        rows_data[px_y] = rows_data[px_y][:off] + bytes(rgb) + rows_data[px_y][off + 3:]

occ = {}
for c in w.creatures:
    occ.setdefault((c.x, c.y), []).append(c)

for y in range(w.h):
    for x in range(w.w):
        f = w.food[y][x] / W.MAX_FOOD
        x0, y0 = PAD + x * (CELL + PAD), PAD + y * (CELL + PAD)
        cs = occ.get((x, y), [])
        if cs:
            # creature: full square + thin lighter outline
            dom = cs[0]
            rgb = lineage_color.get(dom.lineage) or hue_to_rgb(dom.genome["hue"])
            hi = tuple(min(255, v + 70) for v in rgb)
            for dy in range(CELL):
                for dx in range(CELL):
                    edge = dx in (0, CELL - 1) or dy in (0, CELL - 1)
                    set_px(x0 + dx, y0 + dy, hi if edge else rgb)
        elif f > 0.04:
            # food: small dim dot at cell center (survives compression, no ghost cells)
            dot = 3
            cx0, cy0 = x0 + (CELL - dot) // 2, y0 + (CELL - dot) // 2
            g = int(55 + 110 * f)
            for dy in range(dot):
                for dx in range(dot):
                    set_px(cx0 + dx, cy0 + dy, (28, g, 32))

raw = b"".join(b"\x00" + r for r in rows_data)
def chunk(tag, data):
    c = struct.pack(">I", len(data)) + tag + data
    return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
png = (b"\x89PNG\r\n\x1a\n"
       + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
       + chunk(b"IDAT", zlib.compress(raw, 9))
       + chunk(b"IEND", b""))
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "dish_render.png")
open(out, "wb").write(png)
print(f"PNG written: {out} ({size}x{size}, {len(png)} bytes)")

# ── block-ASCII (what CLI users see): blocks for food, blocks for creatures ──
BLOCKS = " ░▒▓█"
lines = []
for y in range(w.h):
    line = []
    occ_row = {}
    for c in w.creatures:
        if c.y == y:
            occ_row.setdefault(c.x, []).append(c)
    for x in range(w.w):
        f = w.food[y][x] / W.MAX_FOOD
        cs = occ_row.get(x, [])
        if cs:
            # creatures: full block, lower = eidos species, upper = native strain
            dom = cs[0]
            ch = dom.lineage[0].upper() if not dom.lineage.startswith("Eidos") else "◆"
        else:
            ch = BLOCKS[min(4, int(f * 4.999))]
        line.append(ch)
    lines.append("".join(line))
print("\nBLOCK RENDER (CLI view): █▓▒░ food density, letters/◆ creatures")
print("\n".join(lines))
