"""VIV-8b: dish cinematography — zoomed MP4 clips of a tick range.

Renders the dish (full frame or a zoomed region) for every tick in a range
and encodes an MP4 via imageio+ffmpeg. Purely additive; no engine changes.

    from cinematography import render_clip
    render_clip(world, path, tick_end=300, fps=12, region=(x, y, half))

Zoom: region=(cx, cy, half) renders the 2*half x 2*half cell window centered
on (cx, cy), toroidal. At cell_px=8 each creature is an 8x8 block painted
with its species' 7x7 glyph (4 shades, species color) — the family face.

Rendering is pixel-space end to end: a frame is `px` rows of `px` RGB tuples;
food paints each cell block first, then creature glyphs overwrite their own
cell blocks only — draw order is explicit, no double indexing.
"""
from __future__ import annotations

from typing import Optional, Tuple

try:  # package context (Hermes plugin) or flat import (tests)
    from . import world as W
    from . import identity as I
    from . import artifacts as A
except ImportError:  # pragma: no cover
    import world as W
    import identity as I
    import artifacts as A


def _food_rgb(level: float) -> Tuple[int, int, int]:
    """Food shading: the dish's own ramp, not a second one.

    The clip used to carry its own green (darker, and with a different
    curve), so the video and the still dish disagreed on what a rich patch
    looks like. One ramp, one food shade, everywhere food is drawn.
    """
    return A.food_rgb(level)


def render_frame(world, cell_px: int = 8,
                 region: Optional[Tuple[int, int, int]] = None,
                 lineage_colors: Optional[dict] = None) -> list:
    """One dish frame: list of pixel rows (each a list of RGB tuples)."""
    w, h = world.w, world.h
    if region is None:
        xs, ys, span = 0, 0, w
    else:
        cx, cy, half = region
        span = 2 * half
        xs, ys = (cx - half) % w, (cy - half) % h
    px = span * cell_px

    # -- food substrate (pixel space) --
    frame = []
    for ry in range(span):
        wy = (ys + ry) % h
        base_row = []
        for rx in range(span):
            wx = (xs + rx) % w
            base_row.extend([_food_rgb(world.food[wy][wx])] * cell_px)
        for _ in range(cell_px):
            frame.append(list(base_row))

    # -- creatures: stamp the species glyph over its own cell block --
    at = {}
    for c in world.creatures:
        if c.alive():
            at.setdefault((c.x, c.y), []).append(c)
    sub = max(1, cell_px // 5)
    for (ccx, ccy), group in at.items():
        dx, dy = (ccx - xs) % w, (ccy - ys) % h
        if dx >= span or dy >= span:
            continue
        rep = max(group, key=lambda c: (c.genome["aggression"] * c.energy, -c.gid))
        if lineage_colors and rep.lineage in lineage_colors:
            rgb = lineage_colors[rep.lineage]
        else:
            rgb = I.color_for(rep.genome["hue"])
        glyph = I.glyph_rgb_cells(rep.genome, rgb)
        for gy in range(5):
            y0 = dy * cell_px + gy * sub
            y1 = y0 + (sub if gy < 4 else cell_px - 4 * sub)
            for gx in range(5):
                x0 = dx * cell_px + gx * sub
                x1 = x0 + (sub if gx < 4 else cell_px - 4 * sub)
                pr, pg, pb = glyph[gy][gx]
                for y_ in range(y0, min(y1, px)):
                    prow = frame[y_]
                    for x_ in range(x0, min(x1, px)):
                        prow[x_] = (pr, pg, pb)
    return frame


def render_clip(world, path: str, tick_start: int = 0, tick_end: int = 120,
                fps: int = 12, cell_px: int = 8,
                region: Optional[Tuple[int, int, int]] = None,
                lineage_colors: Optional[dict] = None,
                nutrients_per_tick: float = 0.0) -> str:
    """Advance tick-by-tick from the world's current state, writing an MP4."""
    import imageio.v2 as imageio
    writer = imageio.get_writer(path, fps=fps, codec="libx264",
                                quality=8, macro_block_size=None)
    try:
        import numpy
        for _ in range(tick_start, tick_end):
            frame = render_frame(world, cell_px=cell_px, region=region,
                                 lineage_colors=lineage_colors)
            writer.append_data(numpy.asarray(frame, dtype="uint8"))
            W.tick_world(world, nutrients=nutrients_per_tick)
    finally:
        writer.close()
    return path


def render_clip_cinematic(world, path: str, ticks: int = 120, fps: int = 12,
                          half: int = 24, center: Optional[Tuple[int, int]] = None,
                          highlight: Optional[str] = None,
                          lineage_colors: Optional[dict] = None,
                          nutrients_per_tick: float = 1.2,
                          upscale: int = 4) -> str:
    """The dish filmed in the unified lattice look (VIV-73).

    One 15px-equivalent subpixel grid for everything: each dish cell is
    6 native pixels with its own deterministic tint (hash of its world
    coordinates - the same patch always looks the same), rich cells get
    nutrient speckles, and every creature is stamped as its real 7x7
    glyph with a pixel-consistent drop shadow. NEAREST-upscaled 4x, so
    the full 48-cell dish lands at 1152px - crisp 1080-class footage
    with zero flat-cell squares.
    """
    import hashlib as _h
    import os
    import shutil
    import subprocess
    from PIL import Image, ImageDraw
    if shutil.which("ffmpeg") is None:
        raise FileNotFoundError("ffmpeg not on PATH")
    w_, h_ = world.w, world.h
    cx, cy = center if center else (w_ // 2, h_ // 2)
    span = 2 * half
    npx = span * 6
    dim = (lineage_colors or {}).get("__dim__", (70, 74, 84))
    BG_EMPTY = (16, 18, 22)

    def frame() -> Image.Image:
        base = Image.new("RGB", (npx, npx))
        bd = ImageDraw.Draw(base)
        for ry in range(span):
            wy = (cy - half + ry) % h_
            for rx in range(span):
                wx = (cx - half + rx) % w_
                r, g, b = A.food_rgb(world.food[wy][wx])
                hh = _h.sha256(bytes([wx, wy])).digest()
                dr = (hh[0] % 11) - 5
                dg = (hh[1] % 17) - 8
                db = (hh[2] % 11) - 5
                bd.rectangle([rx * 6, ry * 6, rx * 6 + 5, ry * 6 + 5],
                             fill=(max(0, min(255, r + dr)),
                                   max(0, min(255, g + dg)),
                                   max(0, min(255, b + db))))
                if world.food[wy][wx] > 1.4:
                    sx = rx * 6 + (hh[3] % 6)
                    sy = ry * 6 + (hh[5] % 6)
                    bd.point((sx, sy),
                             fill=(int(r * 1.4), int(g * 1.4), int(b * 1.25)))
        at = {}
        for c in world.creatures:
            if c.alive():
                dx = (c.x - (cx - half)) % w_
                dy = (c.y - (cy - half)) % h_
                if dx < span and dy < span:
                    at.setdefault((dx, dy), []).append(c)
        for (dx, dy), group in at.items():
            rep = max(group, key=lambda c: (c.genome["aggression"] * c.energy,
                                            -c.gid))
            if lineage_colors:
                if rep.lineage == highlight:
                    rgb = lineage_colors.get(rep.lineage,
                                             I.color_for(rep.genome["hue"]))
                elif highlight:
                    rgb = dim
                else:
                    rgb = lineage_colors.get(rep.lineage,
                                             I.color_for(rep.genome["hue"]))
            else:
                rgb = I.color_for(rep.genome["hue"])
            glyph = I.glyph_rgb_cells(rep.genome, rgb)
            x0 = dx * 6
            y0 = dy * 6
            for gy in range(7):
                for gx in range(7):
                    if glyph[gy][gx] == BG_EMPTY:
                        continue
                    xx = x0 + gx + 1
                    yy = y0 + gy + 1
                    if 0 <= xx < npx and 0 <= yy < npx:
                        r0, g0, b0 = base.getpixel((xx, yy))
                        base.putpixel((xx, yy),
                                      (int(r0 * 0.6), int(g0 * 0.6),
                                       int(b0 * 0.6)))
            for gy in range(7):
                for gx in range(7):
                    pr, pg, pb = glyph[gy][gx]
                    if (pr, pg, pb) == BG_EMPTY:
                        continue
                    xx = x0 + gx
                    yy = y0 + gy
                    if 0 <= xx < npx and 0 <= yy < npx:
                        bd.point((xx, yy), fill=(pr, pg, pb))
        return base.resize((npx * upscale, npx * upscale), Image.NEAREST)

    size = npx * upscale
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo",
         "-pix_fmt", "rgb24", "-s", f"{size}x{size}", "-r", str(fps),
         "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", path],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE)
    try:
        proc.stdin.write(frame().tobytes())
        for _ in range(ticks - 1):
            W.tick_world(world, nutrients=nutrients_per_tick)
            proc.stdin.write(frame().tobytes())
        proc.stdin.close()
    except BrokenPipeError:
        pass
    proc.wait()
    return path


def render_clip_ffmpeg(world, path: str, ticks: int = 120, fps: int = 12,
                       cell_px: int = 8,
                       region: Optional[Tuple[int, int, int]] = None,
                       lineage_colors: Optional[dict] = None,
                       highlight: Optional[str] = None,
                       nutrients_per_tick: float = 0.0) -> str:
    """Encode an MP4 of ``ticks`` frames via the ffmpeg rawvideo pipe.

    PIL renders each frame (pure python; no numpy/imageio required —
    Hermes runtime ships PIL, ffmpeg ships on PATH). When ``highlight``
    names a lineage, all other creatures render dimmed so the target
    species reads clearly in a mixed dish.
    """
    import os
    import shutil
    import subprocess
    if shutil.which("ffmpeg") is None:
        raise FileNotFoundError("ffmpeg not on PATH")
    from PIL import Image
    dim = (lineage_colors or {}).get("__dim__", (70, 74, 84))

    def frame_bytes():
        pix = render_frame(world, cell_px=cell_px, region=region,
                           lineage_colors=lineage_colors)
        h, w = len(pix), len(pix[0])
        img = Image.new("RGB", (w, h))
        img.putdata([tuple(p) for row in pix for p in row])
        return img.tobytes(), w, h

    first, wpx, hpx = frame_bytes()
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo",
         "-pix_fmt", "rgb24", "-s", f"{wpx}x{hpx}", "-r", str(fps),
         "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", path],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE)
    try:
        proc.stdin.write(first)
        for _ in range(ticks - 1):
            W.tick_world(world, nutrients=nutrients_per_tick)
            data, _, _ = frame_bytes()
            proc.stdin.write(data)
        proc.stdin.close()
    except BrokenPipeError:
        pass
    rc = proc.wait()
    err = proc.stderr.read().decode("utf-8", errors="replace")
    if rc != 0:
        raise RuntimeError(f"ffmpeg clip encode failed: {err[:400]}")
    if not os.path.exists(path):
        raise RuntimeError("ffmpeg produced no output file")
    return path
