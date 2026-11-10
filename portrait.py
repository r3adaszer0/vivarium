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

from identity import color_for, glyph_cells

RST = "\x1b[0m"

# The glyph's four levels exist as shade characters in /vivarium show
# (" .o@"). At 3x that shading turns into checkerboard dither and reads as
# noise, so the portrait keeps the glyph's SHAPE and drops the tones: same
# face, one solid colour.
BLOCKS = (" ", "█", "█", "█")


def _fallback_genome(eidos: str) -> dict:
    """A full stand-in genome when only the id is known.

    glyph_cells needs every GENOME_KEY, so a partial dict is not an option:
    fill them from the digest, which keeps the face stable per id.
    """
    import world as W
    digest = hashlib.sha256(eidos.encode()).digest()
    out = {}
    for i, key in enumerate(W.GENOME_KEYS):
        out[key] = digest[i % len(digest)] / 255.0
    out["hue"] = digest[0] / 255.0
    return out


def sprite_lines(genome=None, eidos: str = "", scale: int = 3):
    """The face as terminal lines: the glyph matrix, each cell widened.

    Solid blocks, not shade characters: at this size four shade levels read
    as noise, while the silhouette plus the species colour matches what the
    same creature looks like in the dish.
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
    fg = f"\x1b[38;2;{r};{g};{b}m"
    out = []
    for row in cells:
        line = "".join(BLOCKS[min(3, int(v))] * scale for v in row)
        out.append(fg + line + RST)
    return out


def sprite_width(scale: int = 3) -> int:
    return 5 * scale
