"""Field-view demo: how Eidos lifeforms actually look in the 48x48 dish,
plus the biography proof: two clones, same DNA, different lives -> different bodies.

Pure functions over the sim state; deterministic; no LLM calls.
"""
from __future__ import annotations
import hashlib, hmac, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import world as W
from world import Creature
from demo_lifeform import derive, RANGES, TEX, portrait

# ── 1. the dish, seeded from invoice-parsing, three species released ─────────
SKILLS = [
    ("invoice-parsing", "Parse PDF invoices into structured line items with totals, tax, "
     "and currency normalization; validate against ledger schema."),
    ("email-triage", "Classify inbox threads by urgency and topic; draft three-line replies "
     "for routine items; escalate anything with a deadline inside 48h."),
    ("chess-opening", "Maintain an opening repertoire; after each game, compare moves to "
     "theory and suggest one improvement."),
]

digest0, genome0, eid0, glyph0, *_ = derive(*SKILLS[0])
w = W.new_world(seed=int.from_bytes(digest0[:4], "big"))

species = {}   # gid -> glyph for the three Eidos founders
for name, text in SKILLS:
    _, g, e, gl, *_ = derive(name, text)
    for _ in range(6):   # a founding pod, not a lone pioneer
        c = Creature(gid=w.next_gid, genome=dict(g), x=w.rng.randrange(w.w),
                     y=w.rng.randrange(w.h), energy=1.6, lineage=e)
        w.creatures.append(c); w.next_gid += 1
        species[c.gid] = gl

W.run(w, ticks=60)

SHADE = " .:-=+*#%@"
def field_map(world, species_glyphs):
    """1:1 view: one cell = one char. Creature glyphs win over food shading."""
    lines = []
    for y in range(world.h):
        row = []
        occ = {}
        for c in world.creatures:
            occ.setdefault((c.x, c.y), []).append(c)
        for x in range(world.w):
            ch = SHADE[min(9, int(world.food[y][x] / W.MAX_FOOD * 9.999))]
            for c in occ.get((x, y), []):
                if c.gid in species_glyphs:
                    ch = species_glyphs[c.gid].upper()
                else:
                    ch = c.lineage[0].lower()
            row.append(ch)
        lines.append("".join(row))
    return "\n".join(lines)

print("FIELD VIEW - the Hermi dish, tick", w.tick, f"({len(w.creatures)} creatures, 1 cell = 1 char)")
print("glyphs: *=Mutabilis(invoice) ,=Vivax(email) ~=Oculata(chess) a/v/j/e=founder strains")
print(field_map(w, species))

# ── 2. zoom: 12x12 neighbourhood around one Oculata founder ──────────────────
oc = next(c for c in w.creatures if c.gid in species and species[c.gid] == "~")
cx, cy = oc.x, oc.y
print(f"\nZOOM 12x12 around an Oculata at ({cx},{cy}) - digits = food density, letters = creatures:")
occ = {}
for c in w.creatures:
    occ.setdefault((c.x, c.y), []).append(c)
for y in range(cy - 6, cy + 6):
    row = []
    for x in range(cx - 6, cx + 6):
        xx, yy = x % w.w, y % w.h
        ch = str(min(9, int(w.food[yy][xx] / W.MAX_FOOD * 9.999)))
        for c in occ.get((xx, yy), []):
            ch = species[c.gid].upper() if c.gid in species else c.lineage[0].lower()
        row.append(ch)
    print("".join(row))

# ── 3. biography proof: two clones, same DNA, different lives ────────────────
_, chess_g, chess_e, chess_gl, *_ = derive(*SKILLS[2])
clones = []
for _ in range(2):
    c = Creature(gid=w.next_gid, genome=dict(chess_g), x=w.rng.randrange(w.w),
                 y=w.rng.randrange(w.h), energy=1.3, lineage=chess_e)
    w.creatures.append(c); w.next_gid += 1
    clones.append(c)

lives = {c.gid: {"age": 0, "moved": 0, "cells": set()} for c in clones}
for t in range(240):
    W.tick_world(w)
    for c in clones:
        if c.alive():
            lives[c.gid]["age"] = c.age
            lives[c.gid]["cells"].add((c.x, c.y))
            lives[c.gid]["energy"] = c.energy

print("\nBIOGRAPHY PROOF - two clones, IDENTICAL DNA (same genome dict):")
for c in clones:
    lv = lives[c.gid]
    print(f"  clone gid={c.gid}: alive={c.alive()} age={lv['age']} "
          f"cells visited={len(lv['cells'])} energy={lv.get('energy', 0):.2f}")

def lived_portrait(g, life):
    """v1 morphology: bulk and texture come from the LIVED life, not the hash."""
    g2 = dict(g)
    g2["metabolism_mult"] = RANGES["metabolism_mult"][0] + \
        0.13 * min(4, life["moved"] // 12)          # roamers grow long
    tex_shift = life["moved"] % len(TEX)
    body = portrait(g2, "~")
    # re-texture with the shifted char (cheap stand-in for grown-CA texture in M2)
    tex = TEX[(int(g["hue"] * len(TEX)) + tex_shift) % len(TEX)]
    return body.replace(TEX[int(g["hue"] * len(TEX)) % len(TEX)], tex)

for c in clones:
    lv = lives[c.gid]
    print(f"\n  body of clone {c.gid} (lived {lv['age']} ticks, roamed {len(lv['cells'])} cells):")
    print(lived_portrait(chess_g, {"age": lv["age"], "moved": len(lv["cells"]),
                                   "energy": lv.get("energy", 0.0)}))
