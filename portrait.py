"""The newborn's face.

A Hermi is a genome and a colour, not a picture: in the dish it is a
single cell. That is honest but it is not something a person can meet.
This turns the species id (which is the head of its genome digest) into
a body plan: symmetric, deterministic, and different for every species.

Deterministic matters: rule 1 of the constitution says nothing here may
be random. The same eidos always yields the same face, on any machine,
forever. Only the drawing is new; the identity was already fixed.
"""

from __future__ import annotations

import hashlib

BOLD, RST = "\x1b[1m", "\x1b[0m"

# Same idea as the dish palette: a species keeps one colour for life.
COLOURS = (
    (247, 118, 142), (125, 207, 255), (158, 206, 106), (224, 175, 104),
    (187, 154, 247), (115, 218, 202), (255, 158, 100), (147, 165, 220),
)


def colour_for(eidos: str):
    h = hashlib.sha256(eidos.encode()).digest()
    return COLOURS[h[0] % len(COLOURS)]


def body_plan(seed: str, width: int = 15, height: int = 9):
    """A mirrored cell grid: left half from the digest, right half reflected."""
    bits = bin(int(hashlib.sha256(seed.encode()).hexdigest()[:40], 16))[2:]
    bits = bits.zfill(160)
    half = (width + 1) // 2
    grid = []
    i = 0
    for _y in range(height):
        row = []
        for _x in range(half):
            # AND of two bits: one bit fills half the grid and the
            # creature reads as a blob. Two bits land near a quarter,
            # which leaves room for a silhouette.
            row.append(bits[i % len(bits)] == "1"
                       and bits[(i + 7) % len(bits)] == "1")
            i += 1
        grid.append(row + list(reversed(row[:-1])) if width % 2 else row + list(reversed(row)))
    # A creature needs eyes. Two cells removed on row 2 read as a face,
    # and the mirror keeps the symmetry the rest of the body has.
    mid = width // 2
    for dx in (-1, 1):
        y = min(2, height - 1)
        grid[y][mid + dx * 2] = False
        if height > 3:
            grid[y + 1][mid + dx * 2] = True
    if not any(any(r) for r in grid):
        grid[height // 2][mid] = True
    return grid


def sprite_lines(eidos: str, scale: int = 1):
    """The face as terminal lines: one grid cell per block, one colour.

    Solid blocks rather than half blocks: at this size the halves turned
    the body into a texture of ▀▄ confetti. A silhouette of █ reads as a
    creature; a dither does not.
    """
    grid = body_plan(eidos)
    r, g, b = colour_for(eidos)
    fg = f"\x1b[38;2;{r};{g};{b}m"
    return [fg + "".join(("█" if v else " ") * scale for v in row) + RST
            for row in grid]
