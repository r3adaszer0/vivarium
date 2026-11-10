"""Species identity: glyph + name, both derived deterministically (VIV-8).

Every species gets a stable visual face (7x7 glyph, 4 shades, mirrored
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

GLYPH_SIZE = 7
SHADES = " .o@"          # darkest -> brightest (matches dish render shading)
SHADE_LEVELS = 4

# Fixed bit-allocation: 2 bits per cell, 28 independent cells (center column
# plus three mirror pairs of a 7x7 grid) = 56 bits from the genome stream.
# 56 bits is 65,536 times the old 5x5 face; it costs two rows of height and
# nothing in width once the portrait draws two characters per cell.
# Cell order: center column top->bottom, then column pairs outward.
_CELL_ORDER: Tuple[Tuple[int, int], ...] = tuple(
    (y, 3) for y in range(GLYPH_SIZE)
) + tuple(
    (y, x)
    for x in (2, 1, 0)       # mirror pair columns, inner pair first
    for y in range(GLYPH_SIZE)
)

# ── glyph ─────────────────────────────────────────────────────────────────────
def _genome_stream(g: Dict[str, float]) -> bytes:
    """Genome -> stable byte stream (rounded floats, key order = GENOME_KEYS)."""
    parts = []
    for k in W.GENOME_KEYS:
        parts.append(f"{k}={round(float(g[k]), 4).hex() if False else round(float(g[k]), 4)!r}")
    return "|".join(parts).encode("utf-8")


def glyph_cells(g: Dict[str, float]) -> List[List[int]]:
    """Genome -> 7x7 shade matrix (0..3), mirrored left-right."""
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
    """The glyph as GLYPH_SIZE lines of shade characters."""
    cells = glyph_cells(g)
    return "\n".join("".join(SHADES[v] for v in row) for row in cells)


def glyph_ansi(g: Dict[str, float], rgb=None) -> str:
    """The face as coloured blocks, one cell per two columns.

    `/vivarium show` printed the face in the plain shade characters, which
    on a dark terminal reads as a grey smudge next to a dish where the same
    species is bright. Same genome, same face, same colour: the show card
    now uses the hue the dish uses.
    """
    cells = glyph_cells(g)
    if rgb is None:
        rgb = color_for(g["hue"])
    mat = glyph_rgb_cells(g, rgb)
    out = []
    for row, mrow in zip(cells, mat):
        line = ""
        for v, c in zip(row, mrow):
            if v == 0:
                line += "  "
            else:
                line += f"\x1b[38;2;{c[0]};{c[1]};{c[2]}m██"
        out.append(line + "\x1b[0m")
    return "\n".join(out)


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


_BAR = 12
# Every gene gets a bar, scaled to its own evolvable range: a full bar means
# "as high as this gene can go", so two species are comparable at a glance
# and a 1.21 forage is not silently read as a third of a bar.
_TRAITS = (
    ("forage", "forage", (118, 214, 120)),
    ("sense", "sense", (110, 170, 235)),
    ("metabolism", "metabolism_mult", (232, 168, 90)),
    ("aggression", "aggression", (226, 110, 110)),
    ("mutate", "mutate", (186, 140, 235)),
)
_RANGES = {
    "forage": (0.2, 2.0), "aggression": (0.05, 2.0),
    "metabolism_mult": (0.7, 1.6), "sense": (1.0, 4.0), "mutate": (0.5, 2.0),
}


def trait_bars(g: Dict[str, float], pod=None, tick=None) -> List[str]:
    """Every gene as a bar. One genome, one panel, everywhere.

    The arrival card and `/vivarium show` printed the same genes in two
    different formats (comma list, pipe list), and one of them listed
    aggression and mutate as bare numbers. Bars read in one pass, and the
    panel is identical on both cards.
    """
    out = []
    if pod is not None and tick is not None:
        out.append(f"  \x1b[2mpod of {pod} · hatch tick {tick}\x1b[0m")
    for label, key, rgb in _TRAITS:
        try:
            v = float(g[key])
        except (KeyError, TypeError, ValueError):
            continue
        lo, hi = _RANGES[key]
        frac = max(0.0, min(1.0, (v - lo) / (hi - lo)))
        filled = max(0, min(_BAR, int(round(frac * _BAR))))
        bar = (f"\x1b[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m" + "█" * filled
               + f"\x1b[38;2;64;70;84m" + "░" * (_BAR - filled) + "\x1b[0m")
        # non-breaking padding: the card collapses runs of spaces
        lab = label.ljust(10).replace(" ", "\u00a0")
        out.append(f"  {lab} {bar} {v:.2f}")
    return out


def species_card(eidos: str, g: Dict[str, float], rgb: Tuple[int, int, int],
                 lineage_count: int = 1, founding_skill: str = "",
                 colored: bool = False, face: bool = True) -> str:
    """One glanceable card: face + name + stats. Pure text; renderers draw it."""
    genus, epithet, common = name_of(g)
    title = f"{genus} {epithet}"
    lines = [f"{title} ({common}) · {eidos}"]
    if face:
        lines.append(glyph_ansi(g, rgb) if colored else glyph_ascii(g))
    lines += [
        *trait_bars(g),
        f"  living members {lineage_count}",
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
