"""Skill-birth: the moment a learned skill becomes a species (VIV-7 core).

Used by the ``on_skill_lifecycle`` hook (automatic) and can be driven
manually for ceremonies. Deterministic per (universe key, skill content): the
same skill can only ever birth one species per universe. Derivation uses
``U.skill_digest`` — the same HMAC as seeding — so a skill's species is the
same no matter which path births it.
"""
from __future__ import annotations

from typing import Callable, Optional

try:  # package context (Hermes plugin) or flat import (tests)
    from . import universe as U
    from . import world as W
except ImportError:  # pragma: no cover
    import universe as U
    import world as W


BIRTHS_KEY = "births"          # registry: skill name -> birth record (shared with seeding.py)
POD_SIZE = 4                   # landing party per birth


def birth_species(s, name: str, content: str,
                  save_world: Callable[[object], None],
                  load_world: Optional[Callable[[], object]] = None,
                  advance: int = 90) -> Optional[dict]:
    """Birth the species for one skill into the live universe.

    Returns the announcement dict, or None when nothing should happen:
    universe not live / no world / already born / empty content.
    """
    content = content or ""
    if not content.strip():
        return None
    rec = U.universe_record(s)
    if rec.get("status") != "live":
        return None
    births = s.get(BIRTHS_KEY, {})
    if isinstance(births, list):  # pre-VIV-7 registry (manual ceremony era)
        births = {b["skill"]: {"eidos": b["eidos"], "day": b["day"],
                               "pod": 4, "digest_fp": "", "era": 1}
                  for b in births if isinstance(b, dict) and "skill" in b}
    if name in births:
        return None  # deterministic per universe: one birth per skill, ever

    w = load_world() if load_world is not None else None
    if w is None:
        return None

    digest = U.skill_digest(s, content)
    eidos = "Eidos_" + digest[:3].hex()
    genome = W.genome_from_bytes(digest[:24])
    # Landing: the digest picks among the dish's most fertile cells (top 8
    # by food value, ties in scan order) and the pod SPREADS — each member
    # gets its own fertile cell (i-th of the top cells, digest-ordered), so
    # the landing party doesn't contest itself into starvation. Deterministic,
    # digest-driven, and a birth always lands where life can take hold.
    cells = sorted(((w.food[y][x], x, y) for y in range(w.h) for x in range(w.w)),
                   key=lambda t: -t[0])
    top = cells[:min(8, len(cells))]
    pod = []
    for i in range(POD_SIZE):
        _, x, y = top[int.from_bytes(digest[24 + i:26 + i], "big") % len(top)]
        pod.append(W.Creature(
            gid=w.next_gid, genome=dict(genome),
            x=x, y=y, energy=2.5,
            lineage=eidos,
        ))
        w.next_gid += 1
    w.creatures.extend(pod)
    if advance:
        W.run(w, advance)

    from datetime import date
    births[name] = {
        "eidos": eidos,
        "day": date.today().isoformat(),
        "tick": w.tick,
        "pod": POD_SIZE,
        "digest_fp": digest[:8].hex(),
        "era": rec.get("era", 1),
    }
    s.set(BIRTHS_KEY, births)
    save_world(w)
    return {
        "eidos": eidos, "name": name, "genome": genome,
        "tick": w.tick, "pod": POD_SIZE,
    }


def announcement(result: dict) -> str:
    """The narration line queued into the agent's next turn."""
    g = result["genome"]
    return (f"🧬 New skill banked — a new species crawled out of the dish: "
            f"{result['eidos']}, hatched from your '{result['name']}' skill "
            f"(forage {g['forage']:.2f}, sense {g['sense']:.2f}, "
            f"metabolism {g['metabolism_mult']:.2f}). A pod of {result['pod']} "
            f"was released at tick {result['tick']}.")
