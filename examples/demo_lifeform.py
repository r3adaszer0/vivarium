"""M2 preview: derive a real lifeform from skill text, exactly as the plugin will.

Pure functions only (rule 1 preview): digest -> genome -> glyph -> portrait -> dish.
Demo universe key is hardcoded here; the real plugin uses the machine-local secret.
"""
from __future__ import annotations
import hashlib, hmac, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import world as W

DEMO_KEY = b"demo-universe-key-not-a-real-secret"
RANGES = {  # trait: (lo, hi)
    "forage": (0.2, 2.0), "aggression": (0.05, 2.0), "metabolism_mult": (0.7, 1.6),
    "sense": (1.0, 4.0), "mutate": (0.5, 2.0), "hue": (0.0, 1.0),
}
TEX = "oO0#@*+=~x%&"   # body texture by hue

def derive(skill_text: str, skill_name: str):
    digest = hmac.new(DEMO_KEY, skill_text.encode(), hashlib.sha256).digest()
    genome = {}
    for i, (trait, (lo, hi)) in enumerate(RANGES.items()):
        v = int.from_bytes(digest[i*4:i*4+4], "big") / 2**32
        genome[trait] = round(lo + (hi - lo) * v, 3)
    eid = "Eidos_" + digest[:3].hex()          # 6 hex chars
    glyph = glyph_of(genome)
    genus, epithet, common = name_of(genome, skill_name)
    return digest, genome, eid, glyph, genus, epithet, common

def glyph_of(g):
    dom = max(g, key=lambda k: g[k] / (RANGES[k][1] - RANGES[k][0]))
    return {"aggression": "^", "forage": "o", "sense": "~",
            "metabolism_mult": ",", "mutate": "*", "hue": "%"}[dom]

def name_of(g, skill_name):
    dom = max(g, key=lambda k: g[k] / (RANGES[k][1] - RANGES[k][0]))
    genus = {"aggression": "Venefica", "forage": "Foragia", "sense": "Oculata",
             "metabolism_mult": "Vivax", "mutate": "Mutabilis", "hue": "Chroma"}[dom]
    epithet = ("gracilis" if g["metabolism_mult"] < 1.0 else
               "robusta" if g["forage"] > 1.2 else
               "vagans" if g["sense"] > 2.5 else "velox")
    common = ({"Venefica": "the striker", "Foragia": "the grazer", "Oculata": "the watcher",
               "Vivax": "the quick-lived", "Mutabilis": "the shifter",
               "Chroma": "the painter"}[genus])
    return genus, epithet, common

def portrait(g, glyph):
    """Pure-function ASCII portrait: body from metabolism, texture from hue,
    spikes from aggression, eyes from sense, grazers get a mouth."""
    w, h = 17, 9
    rx = 3 + int(round((1.7 - g["metabolism_mult"]) * 3))   # slower = bulkier
    ry = 2 + rx // 3
    cx, cy = w // 2, h // 2
    tex = TEX[int(g["hue"] * len(TEX)) % len(TEX)]
    grid = [[" "] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            dx, dy = (x - cx) / rx, (y - cy) / ry
            if dx*dx + dy*dy <= 1.0:
                grid[y][x] = tex
    eyes = min(4, max(1, int(round(g["sense"]))))
    for i in range(eyes):
        ex = cx - (eyes - 1) + 2 * i
        if 0 <= ex < w and cy - ry - 1 >= 0 and grid[cy - ry][ex] != " ":
            grid[cy - ry][ex] = "."          # sensory dots along the back
    spikes = int(round(g["aggression"] * 3))
    for i in range(min(spikes, w)):
        sx = 2 + i * (w - 5) // max(1, spikes - 1) if spikes > 1 else cx
        if 0 <= sx < w and cy - ry - 1 >= 0:
            grid[cy - ry - 1][sx] = "^" if grid[cy - ry][sx] != " " else grid[cy - ry - 1][sx]
    if g["forage"] > 1.0:
        mx = cx + rx - 1
        if mx < w:
            grid[cy][mx] = "o"               # grazing mouth
    return "\n".join("".join(row) for row in grid)

SKILLS = [
    ("invoice-parsing", "Parse PDF invoices into structured line items with totals, tax, "
     "and currency normalization; validate against ledger schema."),
    ("email-triage", "Classify inbox threads by urgency and topic; draft three-line replies "
     "for routine items; escalate anything with a deadline inside 48h."),
    ("chess-opening", "Maintain an opening repertoire; after each game, compare moves to "
     "theory and suggest one improvement."),
]

def _main():
    for skill_name, skill_text in SKILLS:
        digest, genome, eid, glyph, genus, epithet, common = derive(skill_name, skill_text)
        print("=" * 62)
        print(f"SKILL: {skill_name}")
        print(f"  digest(head) : {digest[:8].hex()}")
        print(f"  genome       : {genome}")
        print()
        print(f"  PORTRAIT ({eid}, glyph '{glyph}')")
        print(portrait(genome, glyph))
        print(f"  {genus} {epithet} ({eid}) — \u201c{common}\u201d")

    # dish born from the FIRST skill's digest, with all three species released
    first = SKILLS[0]
    digest, genome, eid, glyph, *_ = derive(*first)
    seed = int.from_bytes(digest[:4], "big")
    w = W.new_world(seed=seed)
    from world import Creature
    for name, text in SKILLS:
        _, g2, e2, gl2, *_ = derive(name, text)
        w.creatures.append(Creature(
            gid=w.next_gid, genome=dict(g2),
            x=w.rng.randrange(w.w), y=w.rng.randrange(w.h),
            energy=1.3, lineage=e2.split("_")[1]))
        w.next_gid += 1
    W.run(w, ticks=150)
    print("=" * 62)
    print(f"DISH seeded from '{first[0]}' digest, +3 imported species, 150 ticks:")
    print(f"population {len(w.creatures)}")
    print(W.render_ascii(w, cols=56, rows=16))


if __name__ == "__main__":
    _main()
