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


def next_birth_seq(births: dict) -> int:
    """The next monotonic birth sequence number (VIV-104).

    One more than the highest seq already in the registry, so the count
    keeps rising across eras and restarts — it is stamped into every
    birth record at write time and travels with the saved state.
    """
    seqs = []
    for r in (births or {}).values():
        if isinstance(r, dict):
            try:
                seqs.append(int(r.get("seq") or 0))
            except (TypeError, ValueError):
                pass
    return 1 + max(seqs) if seqs else 1


def newest_birth(births: dict):
    """The newest birth EVENT, selected by data — never by dict position.

    A re-birth (VIV-61: a skill with an older-era registry row births
    again) RE-ASSIGNS an existing key, and Python keeps a re-assigned
    key's original position. So ``list(births.items())[-1]`` returns
    whichever new-name skill was inserted last, not the re-birth — the
    featured card pinned the second-to-last birth forever (the reported
    "first skill flips, second doesn't"). Selection is therefore by the
    write-time stamp: (seq, era, insertion order). Legacy records without
    a seq rank below stamped ones and tie-break by era — a re-birth
    updates its record's era, so even pre-VIV-104 data orders correctly.
    Returns (skill_name, record) or None.
    """
    if not isinstance(births, dict):
        return None
    best = None
    best_key = None
    for idx, (name, rec) in enumerate(births.items()):
        if not isinstance(rec, dict):
            continue
        try:
            seq = int(rec.get("seq") or 0)
        except (TypeError, ValueError):
            seq = 0
        try:
            era = int(rec.get("era") or 0)
        except (TypeError, ValueError):
            era = 0
        key = (seq, era, idx)
        if best_key is None or key > best_key:
            best, best_key = (name, rec), key
    return best


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
    era = rec.get("era", 1)
    prior = births.get(name)
    if prior is not None:
        # Deterministic per universe: one birth per skill, ever - but a
        # restart is a NEW universe (new key, new physics, VIV: era N+1
        # replays the walkthrough). A registry row stamped with an older
        # era describes a dead universe, not this one; the skill is free
        # to be born again here.
        if int(prior.get("era") or 1) >= era:
            return None

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
    genome = W.genome_from_bytes(digest[:W.GENOME_BYTES])
    # The colour is the species tag: derived from the id, not sampled from
    # the digest, so it can never be confused with a heritable trait. Older
    # species keep their stored hue until their next record is written.
    W.tag_hue(genome, eidos)
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
    genre = _name_species(genome)
    births[name] = {
        "eidos": eidos,
        "species": genre[0],
        "common": genre[1],
        "day": date.today().isoformat(),
        "tick": w.tick,
        "pod": POD_SIZE,
        "digest_fp": digest[:8].hex(),
        "era": rec.get("era", 1),
        "seq": next_birth_seq(births),   # VIV-104: newest-birth ordering
        "genome": dict(genome),   # VIV-13: enables challenge-code export
    }
    s.set(BIRTHS_KEY, births)
    save_world(w)
    return {
        "eidos": eidos, "name": name, "genome": genome,
        "species": genre[0], "common": genre[1],
        "tick": w.tick, "pod": POD_SIZE,
    }


def _name_species(genome: dict):
    """Genus + epithet + common name, computed once and then frozen."""
    try:
        from . import identity as vident
    except ImportError:  # pragma: no cover
        import identity as vident
    genus, epithet, common = vident.name_of(genome)
    return f"{genus} {epithet}", common


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
    # A species is NAMED ONCE, at birth. Adding a gene later must not rename
    # a creature somebody already met (dispersal turned Oculata robusta into
    # Oculata pinguis for every species born before it existed).
    named = result.get("species")
    if named:
        genus, epithet = named.split(" ", 1)
    else:
        genus, epithet = _name_species(g)[0].split(" ", 1)
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
