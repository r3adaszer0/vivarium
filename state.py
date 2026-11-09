"""State + persistence for Vivarium.

World state lives in the plugin's profile-scoped ``ctx.state`` (atomic JSON on
disk under ``~/.hermes/plugin-data/vivarium/``), so the dish survives restarts
and is shared by tools, hooks and cron. Determinism: the world's RNG seed is
stored once; a loaded world resumes its RNG stream from ``seed + tick*7919``.

Challenge codes: a genome serializes to ``VIV1<urlsafe-base64(json)>`` — small
enough to paste on X/Discord, decodable by anyone running the plugin.
"""

from __future__ import annotations

import base64
import json
import random
from typing import Any, Dict, List, Optional

try:  # package context (Hermes plugin) or flat import (tests)
    from . import world as vworld
    from .world import Creature, World
except ImportError:  # pragma: no cover
    import world as vworld
    from world import Creature, World

_WORLD_KEY = "world"
_SEED_KEY = "seed"
_ACTIVITY_KEY = "activity"
_NARRATION_KEY = "pending_narration"
_EVENTLOG_KEY = "eventlog"

# tool-name prefix → nutrient value dropped per tool call
NUTRIENT_MAP = {
    "terminal": 0.8,
    "write_file": 0.5,
    "patch": 0.5,
    "web_search": 0.4,
    "web_extract": 0.4,
    "browser": 0.4,
    "read_file": 0.2,
    "search_files": 0.2,
}
DEFAULT_NUTRIENT = 0.15

_ctx = None


def bind(ctx) -> None:
    """Bind the PluginContext (called once from register())."""
    global _ctx
    _ctx = ctx


def _state():
    if _ctx is None:
        raise RuntimeError("Vivarium state used before bind(ctx)")
    return _ctx.state


# ── world persistence ────────────────────────────────────────────────────────
def _seed() -> int:
    s = _state()
    seed = s.get(_SEED_KEY)
    if seed is None:
        seed = random.SystemRandom().randrange(2**31)
        s.set(_SEED_KEY, seed)
    return int(seed)


def load_world() -> Optional[World]:
    """Load the dish, creating a fresh one ONLY on a live universe.

    ROOT FIX (era-9 phantom-dish incident): a dormant universe has NO
    world. The old lazy-create materialized a phantom 26-creature dish
    whenever any code path touched the world on a dormant universe
    (status paint, codex, doctor, show), resurrecting the dish after a
    restart. The universe record is the source of truth: dormant +
    missing world = return None, save nothing. Live + missing world =
    create (the post-Big-Bang case).
    """
    rec = _state().get("universe") or {}
    d = _state().get(_WORLD_KEY)
    if d is None:
        if rec.get("status") != "live":
            return None
        w = vworld.new_world(seed=_seed())
        save_world(w)
        return w
    if rec.get("status") != "live":
        # Self-heal: a world file on a DORMANT universe is a phantom
        # left by pre-law code. Purge it and report none.
        _state().set(_WORLD_KEY, None)
        return None
    return World.from_dict(d, seed=_seed())


def save_world(w: World) -> None:
    _state().set(_WORLD_KEY, w.to_dict())


# ── VIV-7 helpers: skill lifecycle → species birth ───────────────────────────
def state():
    """The raw plugin-state object (for birth.registry access)."""
    return _state()


def universe_record() -> dict:
    """The universe record via the bound state (thin wrapper for hooks)."""
    try:
        from . import universe as vuniverse
    except ImportError:  # pragma: no cover
        import universe as vuniverse
    return vuniverse.universe_record(_state())


def skill_content(skill_name: str) -> Optional[str]:
    """Full SKILL.md bytes of a learned skill, or None when not found.

    Resolves like Hermes does: frontmatter name match across the local
    skills dir (flat or nested) plus the bundled catalog.
    """
    from pathlib import Path
    bases = []
    home = Path.home() / ".hermes" / "skills"
    if home.exists():
        bases.append(home)
    bundled = Path("/usr/local/lib/hermes-agent/skills")
    if bundled.exists():
        bases.append(bundled)
    for base in bases:
        for p in list(base.glob(f"{skill_name}/SKILL.md")) \
                + list(base.glob(f"*/{skill_name}/SKILL.md")):
            try:
                return p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
    return None


def advance(w: World, ticks: int = 1, nutrients: float = 0.0) -> List[dict]:
    """Advance the dish ``ticks`` ticks, persist, and remember the summary.

    VIV-11: every advance also samples the population curve and runs the
    pattern detectors — discoveries happen during normal use, not only when
    someone asks. New Codex entries are returned as narration lines.
    """
    before_counts: Dict[str, int] = {}
    for c in w.creatures:
        if c.alive():
            before_counts[c.lineage] = before_counts.get(c.lineage, 0) + 1
    summaries = vworld.run(w, ticks=ticks, nutrients_per_tick=nutrients)
    save_world(w)
    # VIV-31 act-death: a lineage that was alive before and is gone now.
    try:
        from . import acts as vacts
    except ImportError:  # pragma: no cover
        import acts as vacts
    if before_counts:
        after: set = {c.lineage for c in w.creatures if c.alive()}
        for lineage in before_counts:
            if lineage not in after and lineage.startswith("Eidos_"):
                line = (f"🪦 The {lineage} lineage has died out "
                        f"(last seen tick {w.tick}).")
                queue_narration(
                    vacts.death_narration(_state(), line, lineage))
    try:
        from . import codex as vcodex
    except ImportError:  # pragma: no cover
        import codex as vcodex
    try:
        from . import acts as vacts
    except ImportError:  # pragma: no cover
        import acts as vacts
    try:
        for line in vcodex.observe(_state(), w, summaries):
            # VIV-31: first discovery carries the act-codex walkthrough
            label = "pattern"
            if "Codex entry:" in line:
                seg = line.split("Codex entry:", 1)[1].split("confirmed", 1)[0]
                label = seg.strip(" :") or label
            queue_narration(vacts.codex_narration(_state(), line, label))
    except Exception:
        pass  # detection is best-effort; the dish must never stop ticking
    if summaries:
        s = vworld.stats(w)
        _append_event(f"tick {w.tick}: pop {s['population']} "
                      f"({summaries[-1]['delta']:+d}), born {s.get('born', 0)}, "
                      f"died {s.get('died', 0)}")
    return summaries


def _append_event(line: str, keep: int = 30) -> None:
    log = _state().get(_EVENTLOG_KEY, [])
    log.append(line)
    _state().set(_EVENTLOG_KEY, log[-keep:])


# ── activity mirror ──────────────────────────────────────────────────────────
def record_activity(tool_name: str, nutrients: float) -> None:
    """Count one real tool call and the food it dropped (the 'mirror' stats)."""
    act = _state().get(_ACTIVITY_KEY, {})
    act[tool_name] = act.get(tool_name, 0) + 1
    act["__nutrients__"] = round(act.get("__nutrients__", 0.0) + nutrients, 2)
    _state().set(_ACTIVITY_KEY, act)


def activity_summary() -> dict:
    return _state().get(_ACTIVITY_KEY, {})


# ── narration queue (hooks → next LLM turn) ──────────────────────────────────
# VIV-31 lesson (user machine, 2026-11-09): the slot used to be a single
# string, so a routine tick report queued one tool call later OVERWROTE
# the Big Bang narration before any turn popped it — the milestone story
# silently vanished. Now: a bounded two-tier queue. Milestones (Big Bang,
# births, acts, Codex, deaths) are never dropped and always deliver
# before routine reports; routine reports are capped (older ones drop).
_NARRATION_MILESTONE_KEY = "pending_narration_milestones"
_ROUTINE_CAP = 2


def queue_narration(line: str, milestone: bool = False) -> None:
    if not line:
        return
    key = _NARRATION_MILESTONE_KEY if milestone else _NARRATION_KEY
    q = _state().get(key, [])
    if isinstance(q, str):        # pre-upgrade shape: migrate
        q = [q] if q else []
    q.append(line)
    if not milestone:
        q = q[-_ROUTINE_CAP:]     # routine noise never accumulates
    _state().set(key, q)


_PAINTED_KEY = "painted_state"


def painted_state():
    """Last dish painted to this terminal: {"era": int, "tick": int}."""
    d = _state().get(_PAINTED_KEY)
    return d if isinstance(d, dict) else None


def mark_painted(era, tick) -> None:
    _state().set(_PAINTED_KEY, {"era": int(era or 0), "tick": int(tick or 0)})


def already_painted(w) -> bool:
    """True when this exact (era, tick) has already been painted."""
    if w is None:
        return False
    rec = _state().get("universe") or {}
    last = painted_state()
    return bool(last and last.get("era") == int(rec.get("era") or 0)
                and last.get("tick") == int(getattr(w, "tick", -1)))


def narration_text() -> str:
    """All pending narrations as one string (tests / debug views)."""
    s = _state()
    parts = []
    for key in (_NARRATION_MILESTONE_KEY, _NARRATION_KEY):
        q = s.get(key, [])
        if isinstance(q, str):
            q = [q] if q else []
        parts.extend(q)
    return "\n".join(parts)


def peek_milestone() -> Optional[str]:
    """Head of the milestone queue WITHOUT popping (same-turn relay)."""
    s = _state()
    mq = s.get(_NARRATION_MILESTONE_KEY, [])
    if isinstance(mq, str):
        mq = [mq] if mq else []
    return mq[0] if mq else None


def pop_milestone() -> Optional[str]:
    """Pop the head of the milestone queue (same-turn relay ownership)."""
    s = _state()
    mq = s.get(_NARRATION_MILESTONE_KEY, [])
    if isinstance(mq, str):
        mq = [mq] if mq else []
    if not mq:
        return None
    line = mq.pop(0)
    s.set(_NARRATION_MILESTONE_KEY, mq)
    return line


def pop_narration() -> Optional[str]:
    s = _state()
    mq = s.get(_NARRATION_MILESTONE_KEY, [])
    if isinstance(mq, str):
        mq = [mq] if mq else []
    if mq:                        # milestones first, one per turn
        line = mq.pop(0)
        s.set(_NARRATION_MILESTONE_KEY, mq)
        return line
    q = s.get(_NARRATION_KEY, [])
    if isinstance(q, str):
        q = [q] if q else []
    if q:
        line = q.pop(0)
        s.set(_NARRATION_KEY, q)
        return line
    return None


# ── challenge codes ──────────────────────────────────────────────────────────
def encode_genome(genome: Dict[str, float]) -> str:
    blob = json.dumps({k: round(v, 4) for k, v in genome.items()}, sort_keys=True)
    return "VIV1" + base64.urlsafe_b64encode(blob.encode()).decode().rstrip("=")


def decode_genome(code: str) -> Optional[Dict[str, float]]:
    code = code.strip()
    if not code.startswith("VIV1"):
        return None
    b64 = code[4:]
    b64 += "=" * (-len(b64) % 4)
    try:
        genome = json.loads(base64.urlsafe_b64decode(b64))
    except Exception:
        return None
    if not isinstance(genome, dict) or not all(k in genome for k in vworld.GENOME_KEYS):
        return None
    return genome


def best_genome() -> Optional[Dict[str, float]]:
    """Genome of the most numerous lineage's oldest member (Gauntlet seed)."""
    w = load_world()
    if not w.creatures:
        return None
    counts: Dict[str, int] = {}
    for c in w.creatures:
        counts[c.lineage] = counts.get(c.lineage, 0) + 1
    top = max(counts, key=counts.get)
    champ = min((c for c in w.creatures if c.lineage == top), key=lambda c: c.gid)
    return dict(champ.genome)


# ── releasing creatures ──────────────────────────────────────────────────────
def release_creatures(w: World, genomes: Optional[List[Dict[str, float]]] = None,
                      count: int = 4, lineage: str = "released") -> List[Creature]:
    """Add creatures. ``genomes`` pins exact genomes (imports); otherwise fresh
    random founders with strain names from their hue."""
    made: List[Creature] = []
    if genomes:
        for genome in genomes:
            made.append(Creature(
                gid=w.next_gid, genome=dict(genome),
                x=w.rng.randrange(w.w), y=w.rng.randrange(w.h),
                energy=1.2, lineage=lineage,
            ))
            w.next_gid += 1
    else:
        for _ in range(max(1, min(10, count))):
            genome = {
                "forage": w.rng.uniform(0.2, 1.0),
                "aggression": w.rng.uniform(0.0, 0.5),
                "metabolism_mult": w.rng.uniform(0.8, 1.2),
                "sense": w.rng.uniform(1.0, 3.0),
                "mutate": w.rng.uniform(0.5, 1.5),
                "hue": w.rng.random(),
            }
            made.append(Creature(
                gid=w.next_gid, genome=genome,
                x=w.rng.randrange(w.w), y=w.rng.randrange(w.h),
                energy=w.rng.uniform(0.9, 1.4),
                lineage=vworld._strain_for(genome["hue"]),
            ))
            w.next_gid += 1
    w.creatures.extend(made)
    save_world(w)
    return made
