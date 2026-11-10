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
                  advance: int = 0) -> Optional[dict]:
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
    # VIV-46: identity is the CONTENT, not the skill name. Learning the
    # same thing under another name must not spawn a twin — the species
    # already exists in this universe.
    fp = digest[:8].hex()
    for known in births.values():
        if isinstance(known, dict) and known.get("digest_fp") == fp:
            return None
    eidos = "Eidos_" + digest[:4].hex()  # 32 bits, 4.3B ids
    genome = W.genome_from_bytes(digest[:24])
    # Landing (VIV-31 fledge): the digest picks among the dish's most
    # fertile cells (top 16 by food, ties in scan order), each pod member
    # on its OWN cell, ties broken toward the LEAST occupied cell — a
    # refuge landing. Newborns should not drop into an incumbent's dining
    # room; the fledge window gives them the rest.
    cells = sorted(((w.food[y][x], x, y) for y in range(w.h) for x in range(w.w)),
                   key=lambda t: -t[0])
    top = cells[:min(64, len(cells))]
    occ: dict = {}
    for c in w.creatures:
        occ[(c.x, c.y)] = occ.get((c.x, c.y), 0) + 1
    # refuge score: food per creature-pressure — cells rich in food AND
    # free of incumbents rank first (a cell with food but zero creatures
    # beats a richer cell that an adult works)
    top.sort(key=lambda t: (-(t[0] / (1.0 + occ.get((t[1], t[2]), 0))),))
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
    w.fledge[eidos] = w.tick   # the fledge grace starts now
    if advance:
        # Advance DEFAULTED to 90 and that was a quiet bug: the pod landed,
        # the world fast-forwarded 90 ticks inside the birth call, and by the
        # time the arrival card painted there was nothing left to point at.
        # The registry even recorded the post-advance tick, so the birth
        # looked like it happened 90 ticks late. A birth is a moment; let the
        # dish keep its own pace.
        W.run(w, advance)

    from datetime import date
    births[name] = {
        "eidos": eidos,
        "day": date.today().isoformat(),
        "tick": w.tick,
        "pod": POD_SIZE,
        "digest_fp": digest[:8].hex(),
        "era": rec.get("era", 1),
        "genome": dict(genome),   # VIV-13: enables challenge-code export
    }
    s.set(BIRTHS_KEY, births)
    save_world(w)
    return {
        "eidos": eidos, "name": name, "genome": genome,
        "tick": w.tick, "pod": POD_SIZE,
    }


def announcement(result: dict) -> str:
    """The line that opens the beat: the id, the name it earned, the skill.

    The traits moved into the card's stat panel (bars, not a comma list):
    a sentence of numbers is read once, a panel is read at a glance.
    """
    g = result["genome"]
    try:  # package context (Hermes plugin) or flat import (tests)
        from . import identity as vident
    except ImportError:  # pragma: no cover
        import identity as vident
    genus, epithet, _common = vident.name_of(g)
    # The id is the one token a reader has to copy, so it gets its own
    # colour instead of disappearing into the white headline. Fixed accent,
    # not the species hue: a red species would otherwise print a red id.
    eidos = f"\x1b[38;2;124;199;255m{result['eidos']}\x1b[0m"
    return (f"New species {eidos} · {genus} {epithet}, "
            f"from your '{result['name']}' skill.")


def find_existing(s: dict, content: str):
    """The species this content already is, or None.

    birth_species returns None for a repeat (same digest, no twin). That
    silence is correct but confusing: the user taught a skill and saw
    nothing. This lets the caller say WHY nothing happened.
    """
    reg = s.get("births") or {}
    digest = U.skill_digest(s, content)
    fp = digest[:8].hex()
    for name, known in reg.items():
        if isinstance(known, dict) and known.get("digest_fp") == fp:
            out = dict(known)
            out.setdefault("name", name)
            return out
    return None
