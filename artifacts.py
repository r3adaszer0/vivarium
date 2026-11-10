"""Artifact rendering for the Codex gallery (VIV-10b).

Renders the shareable images a discovery or species implies, into the
plugin's media directory. Everything is derived from data (deterministic
world, keyed digests), so every image here is reproducible bit-for-bit
from its Codex entry — the PNGs are a cache, never the source of truth.

Media lives beside state.json:
    ~/.hermes/plugin-data/<vivarium>/media/
"""
from __future__ import annotations

import json
import struct
import tempfile
import zlib
from typing import Dict, Optional, Tuple

try:  # package context (Hermes plugin) or flat import (tests)
    from . import world as W
    from . import identity as I
except ImportError:  # pragma: no cover
    import world as W
    import identity as I


# ── minimal PNG writer (zero-dependency, proven in render_live.py) ───────────
def write_png(path: str, pixels, size: int) -> None:
    """Write an RGB or RGBA PNG. Alpha (color type 6) lets a sprite's empty
    cells show the terminal's own background, the same way the dish's
    trails already do not exist: the picture is the creature, nothing else."""
    px0 = pixels[0][0]
    rgba = len(px0) == 4
    raw = b"".join(b"\x00" + b"".join(bytes(px) for px in row) for row in pixels)
    def chunk(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c))
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8,
                                      6 if rgba else 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(png)


def media_dir(s) -> str:
    """The plugin's media directory, created on demand."""
    import os
    d = getattr(s, "data_dir", None)          # real PluginState
    if d is not None and hasattr(d, "__truediv__"):
        path = str(d / "media")
    else:                                     # FakeState in tests
        path = os.path.join(tempfile.gettempdir(), "vivarium-media")
    os.makedirs(path, exist_ok=True)
    return path


# ── artifacts ─────────────────────────────────────────────────────────────────
# ── food colour ──────────────────────────────────────────────────────────────
# The scale used to be linear with a near-black floor: at 6% of saturation a
# cell drew four steps from invisible, so a grazed dish looked like a hole and
# a fed one like a light switch. Two changes fix the read without touching the
# data: lift the floor and compress the top with a gamma, and paint bare cells
# as poor soil rather than leaving them as background.
FOOD_EMPTY = (28, 37, 30)
FOOD_FLOOR_G, FOOD_TOP_G, FOOD_GAMMA = 40, 165, 0.42


def food_rgb(f: float):
    """Green for a food value: 0 is poor soil, MAX_FOOD is rich."""
    if f <= 0.0:
        return FOOD_EMPTY
    t = min(1.0, f / W.MAX_FOOD) ** FOOD_GAMMA
    return (30, int(FOOD_FLOOR_G + (FOOD_TOP_G - FOOD_FLOOR_G) * t), 40)



def render_glyph_png(s, eidos: str, genome: Dict[str, float]) -> Optional[str]:
    """One species face (7x7 -> 210px), tinted by its hue."""
    name = f"glyph_{eidos[6:]}.png"
    path = f"{media_dir(s)}/{name}"
    SCALE, PAD = int(210 / I.GLYPH_SIZE), 10
    size = I.GLYPH_SIZE * SCALE + 2 * PAD
    rgb = I.glyph_rgb_cells(genome, I.color_for(genome["hue"]))
    EMPTY = (24, 26, 32)
    # Empty glyph cells go fully transparent: the face floats on the
    # terminal's own background instead of carrying a dark box into every
    # card. Filled cells stay opaque so hue survives any background.
    pixels = [[(rgb[(py - PAD) // SCALE][(px - PAD) // SCALE] + (255,))
               if PAD <= py < size - PAD and PAD <= px < size - PAD
               and rgb[(py - PAD) // SCALE][(px - PAD) // SCALE] != EMPTY
               else (0, 0, 0, 0) for px in range(size)] for py in range(size)]
    write_png(path, pixels, size)
    return path


def render_discovery_stamp_png(s, discovery: dict, world_dict: dict) -> Optional[str]:
    """Dish snapshot at the discovery moment (full dish, 6px/cell).

    Uses the world dict captured when the pattern fired, so the image is the
    exact dish state the detector saw — re-derivable by replaying to that tick.
    """
    pattern = discovery["pattern"].replace("_", "-")
    extra = discovery.get("evidence", {}).get("duration_ticks",
                                              discovery.get("period", ""))
    name = f"discovery_{pattern}_{extra}.png"
    path = f"{media_dir(s)}/{name}"
    w = W.World.from_dict(world_dict)
    CELL, PAD = 6, 1
    size = w.w * (CELL + PAD) + PAD
    rows = [bytes((13, 15, 18)) * size for _ in range(size)]

    def px(x, y, rgb):
        if 0 <= x < size and 0 <= y < size:
            o = x * 3
            rows[y] = rows[y][:o] + bytes(rgb) + rows[y][o + 3:]

    # food layer: every cell, so bare ground reads as poor soil
    for y in range(w.h):
        for x in range(w.w):
            rgb = food_rgb(w.food[y][x])
            for iy in range(CELL - 1):
                for ix in range(CELL - 1):
                    px(x * (CELL + PAD) + 1 + ix, y * (CELL + PAD) + 1 + iy,
                       rgb)
    # creatures as lineage-colored squares (top-8 coloring like render_live)
    counts: Dict[str, int] = {}
    for c in w.creatures:
        counts[c.lineage] = counts.get(c.lineage, 0) + 1
    top = [l for l, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:8]]
    for c in w.creatures:
        rgb = I.color_for(c.genome["hue"]) if c.lineage in top else (90, 96, 110)
        for iy in range(CELL - 2):
            for ix in range(CELL - 2):
                px(c.x * (CELL + PAD) + 1 + ix, c.y * (CELL + PAD) + 1 + iy, rgb)
    # assemble rows into a pixel matrix for write_png
    pixels = [[tuple(rows[y][x * 3:x * 3 + 3]) for x in range(size)]
              for y in range(size)]
    write_png(path, pixels, size)
    return path


def _callout_plate(pixels, size, cell_xy, label, cell: int, pad: int,
                   margin: int = 108):
    """Ring the cell, then point at it from a label in the right margin.

    A ring alone tells the eye *where* but not *what*: at 232px the dish is
    a field of dots, and "the white ring" is a scavenger hunt. The plate
    widens the canvas and draws the id beside the dish, joined by a leader
    line, so a newcomer can be found in the picture and named in the same
    glance. Pillow is optional: without it we fall back to the ring.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:  # pragma: no cover - no Pillow, no label
        return None
    img = Image.new("RGB", (size, size), (13, 15, 18))
    img.putdata([px for row in pixels for px in row])
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 10)
    except Exception:  # pragma: no cover
        font = ImageFont.load_default()
    mx, my = int(cell_xy[0]), int(cell_xy[1])
    cx = mx * (cell + pad) + (cell + pad) // 2
    cy = my * (cell + pad) + (cell + pad) // 2
    # The label rides next to the cell, not in a far margin: a long leader
    # line crosses half the dish and turns the arrow into a cut. Short hop,
    # short line, and the box is clamped to stay inside the picture.
    tw = d.textlength(label, font=font)
    bw, bh = int(tw) + 16, 18
    bx = cx + 12
    if bx + bw > size - 3:
        bx = cx - 12 - bw
    bx = max(3, min(bx, size - bw - 3))
    by = max(3, min(cy - bh // 2, size - bh - 3))
    d.line([cx, cy, bx if bx > cx else bx + bw, by + bh // 2],
           fill=(120, 190, 245), width=1)
    d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=4,
                        fill=(16, 26, 42), outline=(90, 170, 235), width=1)
    d.text((bx + 8, by + bh // 2), label, font=font,
           fill=(180, 218, 255), anchor="lm")
    # No badge digit: the label box carries the id itself, so the eye
    # goes cell -> line -> id with no cipher to decode.
    return img


def render_dish_png(s, w, name: str, mark=None, callout=None) -> Optional[str]:
    """Snapshot of the CURRENT dish (VIV-28b): same visual language as the
    discovery stamp — food blooms + lineage-colored creature squares."""
    CELL, PAD = 6, 1
    size = w.w * (CELL + PAD) + PAD
    rows = [bytearray((13, 15, 18) * size) for _ in range(size)]

    def px(x, y, rgb):
        if 0 <= x < size and 0 <= y < size:
            o = x * 3
            rows[y][o:o + 3] = bytes(rgb)

    for y in range(w.h):
        for x in range(w.w):
            rgb = food_rgb(w.food[y][x])
            for iy in range(CELL - 1):
                for ix in range(CELL - 1):
                    px(x * (CELL + PAD) + 1 + ix,
                       y * (CELL + PAD) + 1 + iy, rgb)
    counts: Dict[str, int] = {}
    for c in w.creatures:
        counts[c.lineage] = counts.get(c.lineage, 0) + 1
    top = [l for l, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:8]]
    for c in w.creatures:
        rgb = I.color_for(c.genome["hue"]) if c.lineage in top else (90, 96, 110)
        for iy in range(CELL - 2):
            for ix in range(CELL - 2):
                px(c.x * (CELL + PAD) + 1 + ix,
                   c.y * (CELL + PAD) + 1 + iy, rgb)
    pixels = [[tuple(rows[y][x * 3:x * 3 + 3]) for x in range(size)]
              for y in range(size)]
    if mark is not None:
        # A ring around the cell that matters. Two pixels of white with a
        # black inset, because one pixel at this size disappears into the
        # food and a solid block hides the creature it is pointing at.
        mx, my = int(mark[0]), int(mark[1])
        x0, y0 = mx * (CELL + PAD), my * (CELL + PAD)
        x1, y1 = x0 + CELL + PAD - 1, y0 + CELL + PAD - 1
        for x in range(x0, x1 + 1):
            pixels[y0][x] = (240, 244, 252)
            pixels[y1][x] = (240, 244, 252)
        for y in range(y0, y1 + 1):
            pixels[y][x0] = (240, 244, 252)
            pixels[y][x1] = (240, 244, 252)
    path = f"{media_dir(s)}/{name}.png"
    plate = None
    if callout is not None:
        plate = _callout_plate(pixels, size, (callout[0], callout[1]),
                               str(callout[2]), CELL, PAD)
    if plate is not None:
        plate.save(path)
    else:
        write_png(path, pixels, size)
    return path


def render_population_curve_png(s, curve, discovery: dict) -> Optional[str]:
    """The population trace with the discovery window marked.

    curve: list of {"tick", "population"}; pure stdlib chart (no matplotlib).
    """
    pattern = discovery["pattern"].replace("_", "-")
    name = f"curve_{pattern}_{discovery.get('period') or 'plateau'}.png"
    path = f"{media_dir(s)}/{name}"
    if len(curve) < 2:
        return None
    width, height = 480, 200
    margin = 24
    ticks = [c["tick"] for c in curve]
    pops = [c["population"] for c in curve]
    t0, t1 = ticks[0], ticks[-1]
    p0, p1 = 0, max(pops) * 1.05 or 1
    def tx(t): return margin + int((t - t0) / max(1, t1 - t0) * (width - 2 * margin))
    def py(p): return height - margin - int(p / p1 * (height - 2 * margin))
    pixels = [[(18, 20, 26)] * width for _ in range(height)]
    # axes
    for x in range(margin, width - margin):
        pixels[height - margin][x] = (70, 74, 84)
    for y in range(margin, height - margin):
        pixels[y][margin] = (70, 74, 84)
    # the curve
    for i in range(1, len(curve)):
        x0, y0 = tx(ticks[i - 1]), py(pops[i - 1])
        x1, y1 = tx(ticks[i]), py(pops[i])
        steps = max(1, x1 - x0)
        for k in range(steps + 1):
            x = x0 + (x1 - x0) * k // steps
            y = y0 + (y1 - y0) * k // steps
            for dy in (0, 1):
                if margin <= y + dy < height - margin:
                    pixels[y + dy][x] = (120, 220, 130)
    write_png(path, pixels, width)
    return path


def ensure_artifacts(s, discovery: dict, world_dict: dict, curve) -> dict:
    """Render (or skip, if cached) all artifacts for a Codex entry."""
    media = media_dir(s)
    produced = {}
    pattern = discovery["pattern"]
    # discovery stamp + population curve: from the captured evidence
    stamp = render_discovery_stamp_png(s, discovery, world_dict)
    if stamp:
        produced["stamp"] = stamp
    curve_png = render_population_curve_png(s, curve, discovery)
    if curve_png:
        produced["curve"] = curve_png
    # species glyphs for every lineage alive in the snapshot (top 8)
    counts: Dict[str, int] = {}
    for c in W.World.from_dict(world_dict).creatures:
        counts[c.lineage] = counts.get(c.lineage, 0) + 1
    w = W.World.from_dict(world_dict)
    genomes = {}
    for c in w.creatures:
        if c.lineage not in genomes and c.lineage.startswith("Eidos_"):
            genomes[c.lineage] = dict(c.genome)
    for lineage in sorted(counts, key=counts.get, reverse=True)[:8]:
        if not lineage.startswith("Eidos_"):
            continue
        g = genomes.get(lineage)
        if g:
            produced[f"glyph:{lineage}"] = render_glyph_png(s, lineage, g)
    return produced
