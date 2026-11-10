"""The newborn's face, in the terminal.

One genome, one face. The dish draws a Hermi as a single coloured cell,
`/vivarium show` draws it as a 5x5 shade matrix, and the arrival card
draws that same matrix larger. Anything else would mean one species had
two different faces depending on where you met it.

Deterministic by construction: the matrix comes from identity.glyph_cells,
which is derived from the genome, so the same species has the same face on
any machine, forever. Rule 1 holds; only the size changes.
"""

from __future__ import annotations

import hashlib

# Package import when loaded as a plugin, flat import when run from the
# repo root. Getting this wrong is invisible until the hook fires live:
# a flat-only import raised ModuleNotFoundError inside art_block and the
# whole act-3 beat was swallowed by the lifecycle handler.
try:
    from .identity import color_for, glyph_cells
except ImportError:  # pragma: no cover - flat-import mode
    from identity import color_for, glyph_cells

RST = "\x1b[0m"

# The glyph's four levels exist as shade characters in /vivarium show
# (" .o@"). Widening THOSE characters turns the face into checkerboard
# dither, and painting every cell flat throws the shading away, which makes
# the creature look like a sticker. So the tones move into the COLOUR: every
# cell is a solid block, and the glyph level sets how bright that block is.
BLOCKS = (" ", "█", "█", "█")
LEVEL_LIGHT = (0.0, 0.42, 0.68, 1.0)


def _fallback_genome(eidos: str) -> dict:
    """A full stand-in genome when only the id is known.

    glyph_cells needs every GENOME_KEY, so a partial dict is not an option:
    fill them from the digest, which keeps the face stable per id.
    """
    try:
        from . import world as W
    except ImportError:  # pragma: no cover - flat-import mode
        import world as W
    digest = hashlib.sha256(eidos.encode()).digest()
    out = {}
    for i, key in enumerate(W.GENOME_KEYS):
        out[key] = digest[i % len(digest)] / 255.0
    out["hue"] = digest[0] / 255.0
    return out


def sprite_lines(genome=None, eidos: str = "", scale: int = 3):
    """The face as terminal lines: the glyph matrix, shaded by brightness.

    Every lit cell is a solid block; the glyph's 0..3 level chooses the
    tint, from a dim 42% of the species colour up to full. Solid cells keep
    the silhouette crisp, the tint keeps the relief.
    """
    if genome is None:
        genome = _fallback_genome(eidos or "Eidos_000000")
    try:
        cells = glyph_cells(genome)
    except (KeyError, TypeError):
        # A partial genome (old registry entry, test fixture): the id still
        # fixes a face, so fall back rather than invent one.
        genome = _fallback_genome(eidos or "Eidos_000000")
        cells = glyph_cells(genome)
    r, g, b = color_for(float(genome.get("hue", 0.5)))
    out = []
    for row in cells:
        line = []
        for level in row:
            if not level:
                line.append(" " * scale)
                continue
            k = LEVEL_LIGHT[min(3, int(level))]
            line.append(f"\x1b[38;2;{int(r * k)};{int(g * k)};{int(b * k)}m"
                        + "█" * scale)
        out.append("".join(line) + RST)
    return out
