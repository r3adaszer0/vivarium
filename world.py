"""World simulation — the heart of Vivarium.

Design notes
------------
* The dish is a square grid (default 48x48). Each cell holds ``food`` (float).
* Terrain is a proper cellular automaton: each tick every cell regrows toward a
  base level with a rate that depends on neighbourhood fertility (clusters are
  fertile -> blooms and barren patches travel like weather fronts), then the
  grid is blurred slightly (food spreads like heat). Deterministic and
  order-independent.
* Creatures are agents on top of the CA: genome (evolvable floats), energy,
  age. Each tick: sense food via local scan, move, eat, pay metabolism,
  maybe reproduce (child genome = parent + gaussian mutation), maybe die.
* Four founder strains (amber, violet, jade, ember) picked by genome hue, so
  narration has names from tick one.
* Fully deterministic for a given (seed, actions): one ``random.Random(seed)``
  drives every stochastic decision, so the Gauntlet can re-run a genome and
  reproduce its score.
* Zero third-party dependencies.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ── Tunables (module-level so tests and the Gauntlet can override) ───────────
GRID_W = 48
GRID_H = 48
BASE_REGROWTH = 0.009       # food per tick a cell regrows toward saturation.
                            # Was 0.018, which refilled a grazed dish in one
                            # afternoon: 102 ticks of agent activity took the
                            # mean from 0.18 to 1.28 of MAX_FOOD. At 0.009 the
                            # same 102 ticks reach about 0.75 with grazing, so a
                            # famine you can see is still there an hour later.
                            # (retuned under LIVE metabolism: K ~ 93 creatures;
                            #  0.003 was tuned while the drain was a dead gene)
FERTILITY_SPREAD = 0.6     # how much neighbours' food boosts regrowth
DIFFUSION = 0.04           # blur weight of the 4-neighbour average
MAX_FOOD = 3.0             # saturation cap per cell
EAT_RATE = 0.9             # food units a creature can eat per tick
METABOLISM = 0.30           # energy burned per tick (live drain; retuned 2026-11-05)
MOVE_COST = 0.06           # extra energy for a purposeful move
REPRODUCE_COST = 0.65      # parent energy cost of one child
REPRODUCE_MIN = 3.00       # energy needed to attempt reproduction
REPRO_CHANCE = 0.25         # per-tick probability of reproducing when eligible
MIN_MATURITY_AGE = 15      # newborns can't reproduce until this age (boom-bust delay)
MUTATION_SCALE = 0.12      # genome jitter per generation
MAX_AGE = 900              # ticks; die of old age around here

# ── newborns ────────────────────────────────────────────────────────────────
# A child used to inherit half its parent's energy minus the birth cost, so
# a parent breeding at the old REPRODUCE_MIN (1.35) produced a child with
# 0.35: less than one tick of metabolism. Every pod was stillborn, and the
# arrival card showed a face that was already extinct. These two constants
# give a newborn a real start without minting energy from nothing: breeding
# now requires enough energy to fund a viable child, and a juvenile burns
# at a reduced rate while it learns to find food.
NEWBORN_FLOOR = 1.20       # energy a child is guaranteed at birth
JUVENILE_TICKS = 30        # ticks a newborn counts as juvenile
JUVENILE_DRAIN = 0.55      # fraction of metabolism paid while juvenile
START_CREATURES = 26
FOOD_ENERGY = 1.0          # energy gained per food unit eaten
FLEDGE_AGE = 120           # ticks a newborn pod is shielded (grace window)
FLEDGE_BURST = 8           # extra reproduction headroom RESERVED for fledgling parents
# Dispersal tuning, measured over 700 ticks on seed 7 (pop / max-per-cell /
# mean gene):  crowd 2, cost x1  -> 28 pop, 1 per cell, 0.69 mean: too eager,
# it scatters the dish into the desert.  crowd 3, cost x2, upkeep 0.02 ->
# 137 pop, 3 per cell, 0.56 mean: crowding survives, the gene stays mixed
# instead of fixing at 1.0.  crowd 4 -> 62 pop: too shy to matter.
DISPERSE_MIN_CROWD = 3    # sharing a cell with this many others makes leaving pay
DISPERSE_COST_MULT = 2.0  # energy multiplier on MOVE_COST when dispersing
DISPERSE_UPKEEP = 0.02    # per-tick energy cost of the gene itself
POP_CAP = 200               # emergency brake only (K is the real limiter);
                            # at 4x founders it pinned the dish and killed the Pulse

FOUNDER_STRAINS = ("amber", "violet", "jade", "ember")
GENOME_KEYS = ("forage", "aggression", "metabolism_mult", "sense", "mutate",
               "hue", "dispersal")
# evolvable ranges (lo, hi) — the contract genome_from_bytes samples within.
# New genes are appended so existing byte slots never move. HUE IS NOT
# EVOLVABLE: it is a species tag derived from the lineage id at birth and
# inherited exactly (see lineage_hue). It stays in the genome because the
# export code, the Codex and the face hash all read it, but no child ever
# changes it, so one lineage is one colour by construction.
GENOME_RANGES = {
    "forage": (0.2, 2.0), "aggression": (0.05, 2.0), "metabolism_mult": (0.7, 1.6),
    "sense": (1.0, 4.0), "mutate": (0.5, 2.0), "hue": (0.0, 1.0),
    "dispersal": (0.0, 1.0),
}
GENOME_BYTES = 4 * len(GENOME_RANGES)   # 28: four bytes per gene
FIXED_GENES = ("hue",)                  # inherited exactly, never jittered


class ByteStream:
    """Deterministic byte stream from a seed (hash chain) — RNG-free world genesis.

    block_0 = H(seed); block_n = H(block_{n-1} || seed). Every take() is a pure
    function of the seed and consumption order; two worlds built from the same
    digest are bit-identical, from different digests diverge everywhere.
    """

    def __init__(self, seed: bytes):
        self._seed = seed
        self._block = b""
        self._pos = 0

    def take(self, n: int) -> bytes:
        out = bytearray()
        while len(out) < n:
            if self._pos >= len(self._block):
                self._block = (hashlib.sha256(self._block + self._seed).digest()
                               if self._block else hashlib.sha256(self._seed).digest())
                self._pos = 0
            chunk = self._block[self._pos:self._pos + (n - len(out))]
            out.extend(chunk)
            self._pos += len(chunk)
        return bytes(out)

    def uint(self, nbytes: int, mod: int) -> int:
        return int.from_bytes(self.take(nbytes), "big") % mod


def _uint(b: bytes) -> int:
    """Big-endian unsigned int of a byte string (position derivation helper)."""
    return int.from_bytes(b, "big")


def genome_from_bytes(b: bytes) -> Dict[str, float]:
    """Four bytes per gene -> a genome, uniform in each range.

    Short input is zero-padded rather than rejected: genomes recorded before
    a gene existed (older export codes, older checkpoints) then decode to
    that gene's floor instead of failing.
    """
    b = bytes(b).ljust(GENOME_BYTES, b"\x00")
    genome = {}
    for i, (trait, (lo, hi)) in enumerate(GENOME_RANGES.items()):
        v = int.from_bytes(b[i * 4:(i + 1) * 4], "big") / 2**32
        genome[trait] = round(lo + (hi - lo) * v, 3)
    return genome


def with_defaults(g: Dict[str, float]) -> Dict[str, float]:
    """A stored genome, completed with each gene's floor.

    Genomes recorded before a gene existed must keep loading, and must not
    silently behave as if they had it: a missing dispersal is 0, which is
    the old dish exactly.
    """
    out = dict(g)
    for key, (lo, _hi) in GENOME_RANGES.items():
        out.setdefault(key, lo)
    return out


def clamp_gene(name: str, value: float) -> float:
    lo, hi = GENOME_RANGES[name]
    return round(min(hi, max(lo, value)), 3)


def tag_hue(genome: Dict[str, float], lineage: str,
            salt: str = "") -> Dict[str, float]:
    """Stamp the lineage's colour onto a genome. The species tag, not a trait.

    `salt` keeps the four FOUNDER strains distinct per universe without
    letting their colours drift: the same strain name in another universe is
    another palette entry, and within one universe a name is one colour.
    Born species need no salt, their id already carries the universe.
    """
    genome["hue"] = lineage_hue(lineage, salt)
    return genome


def lineage_hue(eidos: str, salt: str = "") -> float:
    """A species' colour, from its id. Constant for the life of the lineage.

    Hue used to mutate with the rest of the genome: the dish showed 135
    distinct colours for 3 lineages, because colour was painted from each
    creature's own drifted hue (and hue is hashed into the face, so every
    child also re-rolled its crest). A species tag that drifts is not a tag.
    """
    key = f"vivarium:hue:{eidos}|{salt}"
    h = hashlib.sha256(key.encode()).digest()
    return round(int.from_bytes(h[:4], "big") / 2**32, 3)


def new_world_from_digest(digest: bytes, founders_extra: Optional[List[Creature]] = None) -> World:
    """Genesis world: terrain AND founders derived purely from a digest.

    The Big Bang path — no seed RNG anywhere. The digest is typically
    HMAC(universe_key, first_skill_content): the universe literally begins
    from the first thing the agent learned.
    """
    bs = ByteStream(digest)
    food = [[0.0] * GRID_W for _ in range(GRID_H)]
    for _ in range(3):  # fertile blooms, as in new_world but hash-placed
        cx, cy = bs.uint(2, GRID_W), bs.uint(2, GRID_H)
        for _ in range(GRID_W * GRID_H // 10):
            x, y = bs.uint(2, GRID_W), bs.uint(2, GRID_H)
            dist = min((x - cx) % GRID_W, (cx - x) % GRID_W) \
                 + min((y - cy) % GRID_H, (cy - y) % GRID_H)
            food[y][x] = max(food[y][x], max(0.0, 2.2 - dist * 0.08))
    creatures: List[Creature] = []
    for i in range(24):  # 4 strains x 6 founders, genomes straight from the digest
        genome = genome_from_bytes(bs.take(GENOME_BYTES))
        creatures.append(Creature(
            gid=i + 1, genome=genome,
            x=bs.uint(2, GRID_W), y=bs.uint(2, GRID_H),
            energy=0.9 + 0.5 * (bs.uint(2, 65536) / 65536),
            lineage=tag_hue(genome, _strain_for(genome["hue"]),
                            digest[:8].hex()) and
            _strain_for(genome["hue"])))
    if founders_extra:
        creatures.extend(founders_extra)
        for j, c in enumerate(creatures, start=1):  # renumber cleanly
            c.gid = j
    return World(w=GRID_W, h=GRID_H, tick=0, food=food, creatures=creatures,
                 rng=random.Random(0),  # placeholder; tick dynamics de-RNG in M2
                 next_gid=len(creatures) + 1, peak_population=len(creatures))


@dataclass
class Creature:
    gid: int
    genome: Dict[str, float]
    x: int
    y: int
    energy: float
    age: int = 0
    lineage: str = "wild"

    def alive(self) -> bool:
        return self.energy > 0.0 and self.age < MAX_AGE


@dataclass
class World:
    w: int
    h: int
    tick: int
    food: List[List[float]]
    creatures: List[Creature]
    rng: random.Random = field(repr=False)
    next_gid: int = 1
    born: int = 0
    died: int = 0
    peak_population: int = 0
    seed: int = 0  # RNG root: per-tick reseeding makes snapshots resumable
    fledge: Dict[str, int] = field(default_factory=dict)  # lineage -> landed tick (fledge grace)

    def _roll_rng(self) -> random.Random:
        """Deterministic dice for THIS tick: seed + tick -> fresh stream.

        The RNG state is never serialized; any snapshot (even one that
        crossed a JSON round-trip) resumes with the identical stream for
        its tick. This is the VIV-12 foundation: state + (seed, tick)
        fully determine the future.
        """
        return random.Random((self.seed + self.tick * 7919) % (2**31))

    # -- serialization --------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "v": 1,
            "seed": self.seed,   # VIV-12: the decision-hash root must persist
            "w": self.w, "h": self.h, "tick": self.tick,
            # full float precision: a snapshot must be EXACTLY the state
            # (VIV-12 — quantized snapshots drifted on resume)
            "food": [[float(v) for v in row] for row in self.food],
            "next_gid": self.next_gid,
            "born": self.born, "died": self.died,
            "fledge": dict(self.fledge),
            "peak": self.peak_population,
            "creatures": [
                {
                    "gid": c.gid, "g": {k: float(v) for k, v in c.genome.items()},
                    "x": c.x, "y": c.y, "e": float(c.energy), "a": c.age,
                    "l": c.lineage,
                }
                for c in self.creatures
            ],
        }

    @classmethod
    def from_dict(cls, d: dict, seed: int = 0) -> "World":
        creatures = [
            Creature(
                gid=c["gid"], genome=with_defaults(c["g"]), x=c["x"], y=c["y"],
                energy=c["e"], age=c["a"], lineage=c.get("l", "wild"),
            )
            for c in d["creatures"]
        ]
        return cls(
            w=d["w"], h=d["h"], tick=d["tick"], food=[list(r) for r in d["food"]],
            creatures=creatures, rng=random.Random((seed + d["tick"] * 7919) % (2**31)),
            next_gid=d.get("next_gid", 1),
            born=d.get("born", 0),
            died=d.get("died", 0), peak_population=d.get("peak", len(creatures)),
            fledge=dict(d.get("fledge", {})),
            seed=d.get("seed", seed),
        )


# ── terrain helpers ──────────────────────────────────────────────────────────
def _neighbours(x: int, y: int, w: int, h: int):
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        yield (x + dx) % w, (y + dy) % h  # toroidal — no edges on a dish


# ── hash-driven decisions (VIV-12) ───────────────────────────────────────────
# The Four Rules demand "not random": every in-tick decision derives from a
# state hash instead of an RNG stream. h(seed, tick, gid, purpose) is a pure
# function of state — same state, same outcome, on any machine, forever.

def _h(seed: int, tick: int, gid: int, purpose: bytes, salt: int = 0) -> bytes:
    return hashlib.sha256(
        seed.to_bytes(8, "big") + tick.to_bytes(8, "big")
        + gid.to_bytes(8, "big") + purpose + salt.to_bytes(4, "big")).digest()


def _u(seed: int, tick: int, gid: int, purpose: bytes,
       salt: int = 0) -> float:
    """Uniform float in [0,1) from the decision hash."""
    return int.from_bytes(_h(seed, tick, gid, purpose, salt)[:4], "big") / 2**32


def _gauss6(seed: int, tick: int, gid: int, purpose: bytes) -> float:
    """Approximate standard normal via Irwin–Hall (6 uniforms − 3): variance
    1/2 — multiply by sqrt(2) for unit variance. Pure function of state."""
    s = sum(_u(seed, tick, gid, purpose, salt=i) for i in range(6)) - 3.0
    return s * (2 ** 0.5)


def _random_cell(rng: random.Random, w: int, h: int) -> Tuple[int, int]:
    return rng.randrange(w), rng.randrange(h)


def _strain_for(hue: float) -> str:
    return FOUNDER_STRAINS[int(hue * 4) % 4]


# ── lifecycle ────────────────────────────────────────────────────────────────
def new_world(seed: int = 0, w: int = GRID_W, h: int = GRID_H) -> World:
    """Create a fresh dish: a few fertile blooms + a founding population.

    Founders spawn AROUND the blooms (not uniformly at random): under live
    metabolism a founder far from food starves before it can reach a bloom.
    The blooms are the cradles; the desert between them is the challenge.
    """
    rng = random.Random(seed)
    food = [[0.0] * w for _ in range(h)]
    blooms = []
    for _ in range(3):
        cx, cy = _random_cell(rng, w, h)
        blooms.append((cx, cy))
        for _ in range(w * h // 10):
            x, y = _random_cell(rng, w, h)
            dist = min((x - cx) % w, (cx - x) % w) + min((y - cy) % h, (cy - y) % h)
            food[y][x] = max(food[y][x], max(0.0, 2.2 - dist * 0.08))
    creatures: List[Creature] = []
    for i in range(START_CREATURES):
        bx, by = blooms[i % len(blooms)]
        ox, oy = rng.randrange(-3, 4), rng.randrange(-3, 4)
        genome = {
            "forage": rng.uniform(0.2, 1.0),
            "aggression": rng.uniform(0.0, 0.5),
            "metabolism_mult": rng.uniform(0.8, 1.2),
            "sense": rng.uniform(1.0, 3.0),
            "mutate": rng.uniform(0.5, 1.5),
            "hue": rng.random(),
            # hash-derived, not rng: drawing it from the rng stream would
            # shift every later draw and silently rewrite the founding dish
            "dispersal": round(_u(seed, 0, i + 1, b"disp") * 0.4, 3),
        }
        _lineage = _strain_for(genome["hue"])
        creatures.append(Creature(
            gid=i + 1,
            genome=tag_hue(genome, _lineage, f"seed:{seed}"),
            x=(bx + ox) % w, y=(by + oy) % h,
            energy=rng.uniform(0.9, 1.4),
            lineage=_lineage,
        ))
    return World(w=w, h=h, tick=0, food=food, creatures=creatures,
                 rng=random.Random(seed * 2654435761 % (2**31)),
                 next_gid=len(creatures) + 1, peak_population=START_CREATURES,
                 seed=seed)


def _terrain_tick(world: World) -> None:
    """The food CA: fertility-weighted regrowth, then a slight blur."""
    w, h, food = world.w, world.h, world.food
    new = [[0.0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            nb_avg = sum(food[ny][nx] for nx, ny in _neighbours(x, y, w, h)) / 4.0
            here = food[y][x]
            rate = BASE_REGROWTH * (1.0 + FERTILITY_SPREAD * nb_avg)
            grew = here + rate * (1.0 - here / MAX_FOOD)
            blurred = grew * (1.0 - DIFFUSION) + nb_avg * DIFFUSION
            new[y][x] = min(MAX_FOOD, max(0.0, blurred))
    world.food = new


def _is_fledgling(world: World, c: Creature) -> bool:
    """True while c's lineage is inside its fledge grace window.

    The grace starts at the lineage's landing tick (world.fledge registry,
    written at pod release) and lasts FLEDGE_AGE of the creature's own
    age — so CHILDREN BORN during the window are fledglings too until
    they age past FLEDGE_AGE themselves.
    """
    landed = world.fledge.get(c.lineage)
    if landed is None:
        return False
    return c.age < FLEDGE_AGE


def _prune_fledge(world: World) -> None:
    """Drop fledge entries whose window is long past (bounded state)."""
    if world.fledge:
        world.fledge = {ln: t for ln, t in world.fledge.items()
                        if world.tick - t < FLEDGE_AGE * 4}


def _creature_tick(world: World, nutrients: float) -> None:
    """One tick of creature life, in three deterministic phases.

    Phase 1 (per creature, gid order): age, metabolic drain, movement.
    Phase 2 (per cell): the cell's food goes to the strongest claimant —
    ``aggression * energy``, ties to the lower gid. A gene must matter or not
    exist: this is the rule that makes ``aggression`` real (cell contest).
    FLEDGE WINDOW (VIV-31): a newborn pod's lineage is 'fledging' for
    FLEDGE_AGE ticks — fledglings never contest adult-held cells, and
    fledgling parents get reserved reproduction headroom above the cap.
    Phase 3 (gid order): reproduction, chance per eligible parent — every
    roll is a hash of (seed, tick, gid, purpose): no RNG anywhere in the
    tick (VIV-12 de-randomization; Rule 1: not random, pure function of
    state).
    """
    w, h = world.w, world.h
    food = world.food
    born_this_tick: List[Creature] = []
    population_after = len(world.creatures)  # cap check includes unborn children
    living = [c for c in sorted(world.creatures, key=lambda c: c.gid) if c.alive()]

    # -- phase 1: age, metabolism, movement --------------------------------------
    for c in living:
        c.age += 1
        _drain = METABOLISM * c.genome["metabolism_mult"]
        if c.age <= JUVENILE_TICKS:
            _drain *= JUVENILE_DRAIN
        c.energy -= _drain
        if not c.alive():
            continue  # starvation during phase 1 skips movement
        # -- sense: best food cell within a square sense radius
        sense = int(round(c.genome["sense"]))
        best_val, best_pos = -1.0, None
        here_val = food[c.y][c.x]
        for dy in range(-sense, sense + 1):
            for dx in range(-sense, sense + 1):
                if dx == 0 and dy == 0:
                    continue
                x, y = (c.x + dx) % w, (c.y + dy) % h
                v = food[y][x]
                if v > best_val:
                    best_val, best_pos = v, (x, y)
        # -- move: toward the best food if it beats staying put, else maybe wander
        if best_pos is not None and best_val > here_val + 0.05:
            tx, ty = best_pos
            step_x = tx - c.x
            if step_x > w // 2:
                step_x -= w
            elif step_x < -w // 2:
                step_x += w
            step_y = ty - c.y
            if step_y > h // 2:
                step_y -= h
            elif step_y < -h // 2:
                step_y += h
            c.x = (c.x + (1 if step_x > 0 else -1 if step_x < 0 else 0)) % w
            c.y = (c.y + (1 if step_y > 0 else -1 if step_y < 0 else 0)) % h
            c.energy -= MOVE_COST
        elif _u(world.seed, world.tick, c.gid, b"wander") < 0.3 * c.genome["forage"]:
            # wander — exploration is an evolved trait (hash-driven: VIV-12)
            c.x = (c.x + int(_u(world.seed, world.tick, c.gid, b"wdx") * 3) - 1) % w
            c.y = (c.y + int(_u(world.seed, world.tick, c.gid, b"wdy") * 3) - 1) % h
            c.energy -= MOVE_COST * 0.5

    # -- phase 1b: dispersal ------------------------------------------------
    # A crowded cell is a shared meal. A creature carrying the dispersal gene
    # may step to the best adjacent cell instead of contesting, paying
    # MOVE_COST to do it: leaving rich food behind is the cost of not
    # sharing it. Hash-driven like every other decision, so 0 dispersal
    # (every creature born before the gene existed) reproduces the old dish
    # exactly.
    occupancy: Dict[tuple, int] = {}
    for c in living:
        if c.alive():
            occupancy[(c.x, c.y)] = occupancy.get((c.x, c.y), 0) + 1
    for c in living:
        if not c.alive():
            continue
        d = c.genome.get("dispersal", 0.0)
        if d <= 0.0:
            continue
        if DISPERSE_UPKEEP:
            c.energy -= DISPERSE_UPKEEP * d
            if not c.alive():
                continue
        here = occupancy.get((c.x, c.y), 0)
        if here < DISPERSE_MIN_CROWD:
            continue
        if _u(world.seed, world.tick, c.gid, b"disp") >= d:
            continue
        best_score, best_xy = None, None
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                x, y = (c.x + dx) % w, (c.y + dy) % h
                score = food[y][x] - 0.35 * occupancy.get((x, y), 0)
                if best_score is None or score > best_score:
                    best_score, best_xy = score, (x, y)
        stay = food[c.y][c.x] - 0.35 * here
        if best_xy is None or best_score <= stay:
            continue
        occupancy[(c.x, c.y)] -= 1
        c.x, c.y = best_xy
        occupancy[best_xy] = occupancy.get(best_xy, 0) + 1
        c.energy -= MOVE_COST * DISPERSE_COST_MULT

    # -- fledge displacement: a fledgling sharing a cell with an adult
    # steps aside to the richest adjacent adult-free cell (hash-picked
    # among ties). Measured: standing there = skipped meals = death
    # spiral; stepping aside to open food = establishment chance.
    if world.fledge:
        fled = [c for c in living if c.alive() and _is_fledgling(world, c)]
        occupied = {}
        for c in living:
            if c.alive():
                occupied.setdefault((c.x, c.y), []).append(c)
        for c in fled:
            mates = occupied.get((c.x, c.y), [])
            if not any(not _is_fledgling(world, o) for o in mates if o is not c):
                continue
            best, best_v = None, -1.0
            for i, (dx, dy) in enumerate(((1, 0), (-1, 0), (0, 1), (0, -1),
                                          (1, 1), (-1, -1), (1, -1), (-1, 1))):
                x, y = (c.x + dx) % w, (c.y + dy) % h
                if any(o.x == x and o.y == y for o in living if o.alive()):
                    continue
                v = food[y][x] + _u(world.seed, world.tick, c.gid,
                                    b"fledge", salt=i) * 0.01
                if v > best_v:
                    best_v, best = v, (x, y)
            if best is not None:
                c.x, c.y = best
                occupied.setdefault(best, []).append(c)

    # -- phase 2: cell contests + eating ------------------------------------------
    at: Dict[Tuple[int, int], List[Creature]] = {}
    for c in living:
        if c.alive():
            at.setdefault((c.x, c.y), []).append(c)
    for (cx, cy), group in sorted(at.items()):
        if len(group) == 1:
            winner = group[0]
        else:
            # FLEDGE GRACE (VIV-31): a fledgling never contests a cell an
            # adult holds — it yields the cell entirely this tick. Honest
            # disturbance dynamics: newcomers establish in open space,
            # not by beating the canopy. Deterministic, state-only.
            adults = [c for c in group if not _is_fledgling(world, c)]
            if adults and len(adults) < len(group):
                group = adults
            winner = max(group, key=lambda c: (c.genome["aggression"] * c.energy, -c.gid))
        cell = food[cy][cx]
        eaten = min(cell, EAT_RATE * min(1.0, winner.genome["forage"]))
        food[cy][cx] = cell - eaten
        winner.energy += eaten * FOOD_ENERGY

    # -- phase 3: reproduction -----------------------------------------------------
    for c in living:
        if not c.alive():
            continue
        # eligible parents get a stochastic chance each tick.
        # (Determinism preserved: reproducibility is per-seed, not per-realtime.)
        # CONSERVATION: the parent splits its body in half, and BOTH halves
        # pay friction (REPRODUCE_COST total, split between them). Total
        # energy after the split is strictly less than before — births
        # consume the surplus instead of printing it (Rule 2).
        # FLEDGE BURST: a fledgling parent gets RESERVED headroom above
        # the cap (adults stay capped at POP_CAP). Without this, at a
        # saturated dish no pod can ever reproduce: incumbents' repro
        # rolls consume any shared headroom first (pods sit last in gid
        # order). Reserved = not a race; the burst belongs to the pod.
        _headroom = (POP_CAP + FLEDGE_BURST if _is_fledgling(world, c)
                     else POP_CAP)
        if (c.energy >= REPRODUCE_MIN and c.age >= MIN_MATURITY_AGE
                and population_after < _headroom
                and _u(world.seed, world.tick, c.gid, b"repro") < REPRO_CHANCE):
            half = c.energy * 0.5
            friction = REPRODUCE_COST * 0.5
            c.energy = max(0.05, half - friction)
            child_energy = max(NEWBORN_FLOOR, half - friction)
            child_genome = {}
            for k, v in c.genome.items():
                if k in FIXED_GENES:
                    child_genome[k] = v          # a species tag does not drift
                    continue
                jitter = _gauss6(world.seed, world.tick, c.gid,
                                 b"mut" + k.encode()) * MUTATION_SCALE
                child_genome[k] = clamp_gene(
                    k, v + jitter * c.genome.get("mutate", 1.0))
            born_this_tick.append(Creature(
                gid=world.next_gid, genome=child_genome, x=c.x, y=c.y,
                energy=child_energy, lineage=c.lineage,
            ))
            world.next_gid += 1
            world.born += 1
            population_after += 1
    # deaths — corpses return a little food (nutrient recycling)
    survivors = []
    for c in world.creatures:
        if c.alive():
            survivors.append(c)
        else:
            world.died += 1
            food[c.y][c.x] = min(MAX_FOOD, food[c.y][c.x] + 0.3)
    world.creatures = survivors + born_this_tick
    world.peak_population = max(world.peak_population, len(world.creatures))
    _prune_fledge(world)
    # nutrient drops from the user's real work land on a hash-picked cell
    # (VIV-12: no RNG — the drop position is a pure function of state)
    if nutrients > 0:
        rx = int(_u(world.seed, world.tick, 0, b"nutx") * w) % w
        ry = int(_u(world.seed, world.tick, 0, b"nuty") * h) % h
        food[ry][rx] = min(MAX_FOOD, food[ry][rx] + nutrients)


def tick_world(world: World, nutrients: float = 0.0) -> dict:
    """Advance the world one tick. Returns a tiny event summary for narration."""
    pre = len(world.creatures)
    world.rng = world._roll_rng()   # kept for genesis/compat consumers only
    _terrain_tick(world)
    _creature_tick(world, nutrients)
    world.tick += 1
    post = len(world.creatures)
    return {
        "tick": world.tick,
        "population": post,
        "born": world.born, "died": world.died,
        "delta": post - pre,
        "avg_energy": round(sum(c.energy for c in world.creatures) / post, 3) if post else 0.0,
    }


def stats(world: World) -> dict:
    """Population snapshot + top lineages by count + age structure."""
    if not world.creatures:
        return {"tick": world.tick, "population": 0, "peak": world.peak_population,
                "lineages": [], "ages": empty_age_stats()}
    counts: Dict[str, int] = {}
    for c in world.creatures:
        counts[c.lineage] = counts.get(c.lineage, 0) + 1
    lineages = sorted(counts.items(), key=lambda kv: -kv[1])[:5]
    avg = lambda key: round(sum(c.genome.get(key, GENOME_RANGES[key][0])
                                for c in world.creatures) / len(world.creatures), 3)
    return {
        "tick": world.tick,
        "population": len(world.creatures),
        "peak": world.peak_population,
        "born": world.born, "died": world.died,
        "avg_energy": round(sum(c.energy for c in world.creatures) / len(world.creatures), 3),
        "avg_genome": {k: avg(k) for k in GENOME_KEYS},
        "lineages": lineages,
        "ages": age_stats(world),
    }


# ── age structure (VIV-9: the dish's thermometer) ─────────────────────────────
def age_stats(world: World) -> dict:
    """Age pyramid: newborns / young / adults / elders, normalized to MAX_AGE.

    Bands (fractions of lifespan): <10% newborn, <35% young, <70% adult,
    else elder. The pyramid diagnoses the ecology at a glance: no newborns
    with many elders = the population is aging out (stall or pre-crash).
    """
    n = len(world.creatures)
    if n == 0:
        return empty_age_stats()
    bands = {"newborns": 0, "young": 0, "adults": 0, "elders": 0}
    oldest = 0
    for c in world.creatures:
        f = c.age / MAX_AGE
        if f < 0.10:
            bands["newborns"] += 1
        elif f < 0.35:
            bands["young"] += 1
        elif f < 0.70:
            bands["adults"] += 1
        else:
            bands["elders"] += 1
        oldest = max(oldest, c.age)
    # birth health: share of population young enough to breed soon
    fertile = bands["newborns"] + bands["young"] + bands["adults"]
    if bands["elders"] > n * 0.5 and bands["newborns"] == 0:
        verdict = "aging out — no births, watch for a crash"
    elif bands["newborns"] == 0 and bands["young"] == 0:
        verdict = "no recent births"
    elif bands["elders"] >= n * 0.3:
        verdict = "maturing population"
    else:
        verdict = "healthy mix"
    return {
        **bands,
        "avg_age": round(sum(c.age for c in world.creatures) / n, 1),
        "oldest": oldest,
        "max_lifespan": MAX_AGE,
        "verdict": verdict,
    }


def empty_age_stats() -> dict:
    return {"newborns": 0, "young": 0, "adults": 0, "elders": 0,
            "avg_age": 0.0, "oldest": 0, "max_lifespan": MAX_AGE,
            "verdict": "the dish is empty"}


CREATURE_GLYPH = "X"          # VIV-28a: creatures read as organisms, not letters


def render_ascii(world: World, cols: int = 64, rows: int = 24) -> str:
    """ASCII map of the dish: X creatures over food-fertility shading.

    VIV-28a redesign: creatures used to render as their lineage's initial
    letter (E/J/V...) — visually lost in the food ramp and misleading as
    text. Now every creature is `X` (alive things look alike; lineage info
    lives in the legend under the map). Pure function of world state.
    """
    cols = max(1, min(cols, world.w))
    rows = max(1, min(rows, world.h))
    sx, sy = world.w / cols, world.h / rows
    shade = " .:-=+*#%@"
    lines = []
    for r in range(rows):
        y0, y1 = int(r * sy), max(int((r + 1) * sy), int(r * sy) + 1)
        line = []
        for c in range(cols):
            x0, x1 = int(c * sx), max(int((c + 1) * sx), int(c * sx) + 1)
            block = max(world.food[y][x] for y in range(y0, min(y1, world.h))
                        for x in range(x0, min(x1, world.w)))
            has = any(x0 <= cr.x < min(x1, world.w) and y0 <= cr.y < min(y1, world.h)
                      for cr in world.creatures)
            line.append(CREATURE_GLYPH if has
                        else shade[min(9, int(block / MAX_FOOD * 9.999))])
        lines.append("".join(line))
    return "\n".join(lines)


def render_ascii_rich(world: World, cols: int = 96, rows: int = 32,
                      color: bool = False) -> str:
    """Dense 'pretty terminal' map: solid-block creatures over ░▒▓ blooms.

    The middle tier of the display ladder (VIV-28): ASCII < rich ASCII <
    terminal graphics (kitty/sixel) < localhost gallery. ~2x the width of
    render_ascii; for terminals (and demo footage) that can afford it.
    Pure function of world state — no RNG.
    """
    cols = max(1, min(cols, world.w))
    rows = max(1, min(rows, world.h))
    sx, sy = world.w / cols, world.h / rows
    ramp = "  ·:░▒▓"          # empty → faint → lush bloom
    colorize = None
    if color:
        try:  # package mode / flat mode
            from . import identity as I
        except ImportError:  # pragma: no cover
            import identity as I

        def colorize(genome):
            r, g, b = I.color_for(genome["hue"])
            return f"\x1b[48;2;{r};{g};{b}m \x1b[0m"   # colored SPACE = block
    lines = []
    for r in range(rows):
        y0, y1 = int(r * sy), max(int((r + 1) * sy), int(r * sy) + 1)
        line = []
        for c in range(cols):
            x0, x1 = int(c * sx), max(int((c + 1) * sx), int(c * sx) + 1)
            block = max(world.food[y][x] for y in range(y0, min(y1, world.h))
                        for x in range(x0, min(x1, world.w)))
            occupant = next((cr for cr in world.creatures
                             if x0 <= cr.x < min(x1, world.w)
                             and y0 <= cr.y < min(y1, world.h)), None)
            if occupant is not None:
                # colored full-width block: a SPACE with a background color
                # keeps the cell exactly 1 column wide (truecolor bg fill)
                line.append(colorize(occupant.genome) if colorize else "█")
            elif block <= 0.01:
                line.append(" ")
            elif block < 0.4:
                line.append("·")
            elif block < 1.0:
                line.append("░")
            elif block < 1.8:
                line.append("▒")
            else:
                line.append("▓")
        lines.append("".join(line))
    return "\n".join(lines)


def run(world: World, ticks: int, nutrients_per_tick: float = 0.0) -> List[dict]:
    """Advance ``ticks`` ticks; return per-tick summaries (Gauntlet harness)."""
    return [tick_world(world, nutrients_per_tick) for _ in range(ticks)]
