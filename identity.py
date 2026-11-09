"""Species identity: glyph + name, both derived deterministically (VIV-8).

Every species gets a stable visual face (5x5 glyph, 4 shades, mirrored
left-right) and a binomial name, both pure functions of its genome — no RNG,
no lookup tables keyed by anything but the genome itself. Two renderers with
this module produce identical species art: the spec is the genome.

Collision budget (see compendium): 15 mirrored cells x 4 shades ~ 10^9 faces
(< 0.01% collision at 10,000 species).

Design: which trait paints which part is FIXED by this spec (not derived),
so faces are comparable across universes: same genome -> same face everywhere.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

try:  # package context (Hermes plugin) or flat import (tests)
    from . import world as W
except ImportError:  # pragma: no cover
    import world as W

GLYPH_SIZE = 5
SHADES = " .o@"          # darkest -> brightest (matches dish render shading)
SHADE_LEVELS = 4

# Fixed bit-allocation: 2 bits per pixel-cell, 15 cells (left half + center
# column of a 5x5 grid, mirrored) = 30 bits consumed from the genome stream.
# Pixel order: center column top->bottom, then column pairs outward.
_CELL_ORDER: Tuple[Tuple[int, int], ...] = tuple(
    (y, 2) for y in range(5)
) + tuple(
    (y, x)
    for x in (1, 0)          # mirror pair columns, inner pair first
    for y in range(5)
)

# ── glyph ─────────────────────────────────────────────────────────────────────
def _genome_stream(g: Dict[str, float]) -> bytes:
    """Genome -> stable byte stream (rounded floats, key order = GENOME_KEYS)."""
    parts = []
    for k in W.GENOME_KEYS:
        parts.append(f"{k}={round(float(g[k]), 4).hex() if False else round(float(g[k]), 4)!r}")
    return "|".join(parts).encode("utf-8")


def glyph_cells(g: Dict[str, float]) -> List[List[int]]:
    """Genome -> 5x5 shade matrix (0..3), mirrored left-right."""
    import hashlib
    stream = hashlib.sha256(_genome_stream(g)).digest()
    cells = [[0] * GLYPH_SIZE for _ in range(GLYPH_SIZE)]
    for i, (y, x) in enumerate(_CELL_ORDER):
        byte = stream[i // 4]
        level = (byte >> (2 * (i % 4))) & 0b11
        cells[y][x] = level
        cells[y][GLYPH_SIZE - 1 - x] = level   # mirror
    return cells


def glyph_ascii(g: Dict[str, float]) -> str:
    """The glyph as 5 lines of shade characters."""
    cells = glyph_cells(g)
    return "\n".join("".join(SHADES[v] for v in row) for row in cells)


def glyph_rgb_cells(g: Dict[str, float], rgb: Tuple[int, int, int]) -> List[List[Tuple[int, int, int]]]:
    """Shade matrix -> RGB matrix, tinted by the species color (hue-derived).

    Shade 0 is background-dark (nearly black); shades 1..3 blend toward the
    species color with increasing brightness, so the glyph reads at a glance
    like the creature's color in the dish.
    """
    import colorsys
    r, gr, b = rgb
    cells = glyph_cells(g)
    out = []
    for row in cells:
        line = []
        for v in row:
            if v == 0:
                line.append((16, 18, 22))          # background dark
            else:
                f = v / 3.0
                line.append((int(r * f), int(gr * f), int(b * f)))
        out.append(line)
    return out


# ── name ──────────────────────────────────────────────────────────────────────
_GENUS = {
    "aggression": "Venefica",       # the striker
    "forage": "Foragia",            # the grazer
    "sense": "Oculata",             # the watcher
    "metabolism_mult": "Vivax",     # the enduring
    "mutate": "Mutabilis",          # the shifter
    "hue": "Chroma",                # the painter
}
_GENUS_COMMON = {
    "Venefica": "the striker",
    "Foragia": "the grazer",
    "Oculata": "the watcher",
    "Vivax": "the enduring",
    "Mutabilis": "the shifter",
    "Chroma": "the painter",
}
_EPITHETS = ("gracilis", "robusta", "vagans", "velox", "minor", "major",
             "serena", "ferox", "tenuis", "pinguis")


def _norm(g: Dict[str, float], key: str) -> float:
    lo, hi = W.GENOME_RANGES[key]
    return (g[key] - lo) / (hi - lo)


def name_of(g: Dict[str, float]) -> Tuple[str, str, str]:
    """Genome -> (genus, epithet, common name).

    Genus = the creature's dominant trait (normalized share of its range).
    Epithet = a stable 10-way pick from the remaining trait profile, so two
    species with the same genus usually differ in epithet.
    """
    import hashlib
    shares = {k: _norm(g, k) for k in W.GENOME_KEYS}
    dom = max(shares, key=lambda k: shares[k])
    genus = _GENUS[dom]
    # epithet from the ordered profile of the OTHER traits (stable, 10-way)
    profile = "".join(f"{k}{shares[k]:.2f}" for k in W.GENOME_KEYS if k != dom)
    idx = int(hashlib.sha256(profile.encode()).hexdigest()[:8], 16) % len(_EPITHETS)
    epithet = _EPITHETS[idx]
    return genus, epithet, _GENUS_COMMON[genus]


def species_card(eidos: str, g: Dict[str, float], rgb: Tuple[int, int, int],
                 lineage_count: int = 1, founding_skill: str = "") -> str:
    """One glanceable card: face + name + stats. Pure text; renderers draw it."""
    genus, epithet, common = name_of(g)
    title = f"{genus} {epithet}"
    lines = [
        f"{title} ({common}) — {eidos}",
        glyph_ascii(g),
        f"  forage {g['forage']:.2f} | aggression {g['aggression']:.2f} | "
        f"metabolism {g['metabolism_mult']:.2f}",
        f"  sense {g['sense']:.2f} | mutate {g['mutate']:.2f} | "
        f"living members {lineage_count}",
    ]
    if founding_skill:
        lines.append(f"  hatched from: {founding_skill}")
    return "\n".join(lines)


def display_hue(hue: float) -> float:
    """Genome hue (0..1) -> rendered hue, skipping the food palette.

    Food renders as dark green; a green creature reads as food to the
    eye. The display hue compresses the wheel into the 65% that excludes
    the yellow-green/green family [0.15, 0.50): cyan-anchored, injective,
    deterministic, pure function of the genome. The genome hue itself is
    untouched (heritable) — only its RENDERING changes.
    """
    h = min(1.0, max(0.0, hue))
    return (0.5 + h * 0.65) % 1.0


def color_for(hue: float) -> Tuple[int, int, int]:
    """Hue (0..1) -> bright RGB, same recipe the dish render uses.

    Routes through display_hue so no species ever renders green (the
    food palette's territory).
    """
    import colorsys
    r, gr, b = colorsys.hls_to_rgb(display_hue(hue), 0.58, 0.8)
    return int(r * 255), int(gr * 255), int(b * 255)
