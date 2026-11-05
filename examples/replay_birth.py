"""Replay your universe's birth — deterministically, from real state.

Recomputes the Big Bang (canon kit digest + per-private-skill HMACs using the
REAL universe key), rebuilds the exact birth world, runs it to --ticks, and
renders. Proves: same inputs -> same world, forever.

Usage: /usr/local/lib/hermes-agent/venv/bin/python3 replay_birth.py --ticks 90
"""
from __future__ import annotations

import argparse
import colorsys
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import discovery as vdisc   # noqa: E402
import seeding as S         # noqa: E402
import universe as U        # noqa: E402
import world as W           # noqa: E402

STRAIN_RGB = {"amber": (222, 170, 60), "violet": (150, 96, 200),
              "jade": (64, 178, 122), "ember": (214, 92, 58)}
TAIL_RGB = (52, 58, 66)   # long-tail lineages: dim slate, visible but recessive


def real_state():
    from hermes_cli.plugins_state import PluginState
    return PluginState("vivarium")


def rebuild_birth_world(s):
    """Reconstruct the exact seeded birth world (deterministic replay)."""
    skills = vdisc.discover()
    canon = [sk for sk in skills if sk["is_canon"]]
    priv = [sk for sk in skills if not sk["is_canon"]]
    kit = b"\x00".join(sorted(sk["name"].encode() + b"\x01" + sk["bytes"]
                              for sk in canon))
    bang = W.ByteStream(S.canon_digest(kit) if canon
                        else U.skill_digest(s, "no-canon-kit"))
    w = W.new_world_from_digest(bang.take(32))
    species = {}
    for sk in canon:
        d = S.canon_digest(sk["bytes"])
        for c in S._release_pod(w, d, S.eidos_id(d), bang):
            species[c.gid] = (sk["name"], S.eidos_id(d))
    for sk in priv:
        d = U.skill_digest(s, sk["bytes"].decode("utf-8", errors="replace"))
        for c in S._release_pod(w, d, S.eidos_id(d), bang):
            species[c.gid] = (sk["name"], S.eidos_id(d))
    return w, species


def hue_rgb(h, l=0.58, s=0.8):
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return int(r * 255), int(g * 255), int(b * 255)


def write_png(w, out_path):
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
    counts = {}
    for c in w.creatures:
        counts[c.lineage] = counts.get(c.lineage, 0) + 1
    top = [l for l, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:8]]
    oldest = {}
    for c in sorted(w.creatures, key=lambda c: c.gid):
        if c.lineage not in oldest:
            oldest[c.lineage] = c.genome["hue"]
    lcolor = {l: (STRAIN_RGB.get(l) or hue_rgb(oldest[l])) for l in top}

    for y in range(w.h):
        for x in range(w.w):
            f = w.food[y][x] / W.MAX_FOOD
            x0, y0 = PAD + x * (CELL + PAD), PAD + y * (CELL + PAD)
            cs = occ.get((x, y), [])
            if cs:
                dom = cs[0]
                rgb = lcolor.get(dom.lineage, TAIL_RGB)
                hi = tuple(min(255, v + 70) for v in rgb)
                for dy in range(CELL):
                    for dx in range(CELL):
                        edge = dx in (0, CELL - 1) or dy in (0, CELL - 1)
                        set_px(x0 + dx, y0 + dy, hi if edge else rgb)
            elif f > 0.015:            # show even sparse food
                dot = 4
                cx0, cy0 = x0 + (CELL - dot) // 2, y0 + (CELL - dot) // 2
                g = int(80 + 150 * f)
                for dy in range(dot):
                    for dx in range(dot):
                        set_px(cx0 + dx, cy0 + dy, (30, g, 36))

    raw = b"".join(b"\x00" + r for r in rows_data)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    open(out_path, "wb").write(png)
    return lcolor


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=int, default=90)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    s = real_state()
    w, species = rebuild_birth_world(s)
    gid_name = {gid: name for gid, (name, eid) in species.items()}
    W.run(w, ticks=args.ticks)
    st = W.stats(w)
    counts = {}
    for c in w.creatures:
        counts[c.lineage] = counts.get(c.lineage, 0) + 1
    out = args.out or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "docs", "birth_replay.png")
    lcolor = write_png(w, out)
    print(f"REPLAY of your universe's birth at tick {st['tick']} "
          f"({len(w.creatures)} creatures, {len(counts)} lineages alive)")
    print("Top lineages:")
    for lin, n in sorted(counts.items(), key=lambda kv: -kv[1])[:8]:
        name = next((nm for nm, e in species.values() if e == lin), lin)
        print(f"  {lin} ({name}): {n}")
    print(f"PNG: {out}")
    print("\nLEGEND: " + ", ".join(
        f"{next((nm for nm, e in species.values() if e == l), l)}={rgb}"
        for l, rgb in lcolor.items()))


if __name__ == "__main__":
    main()
