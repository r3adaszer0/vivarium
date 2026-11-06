"""Seeding — populate a dormant universe from the user's real skills.

Two derivations (canon vs private), pods, genesis-Eidos naming, onboarding
message, world save. Extends universe.py; does not duplicate it.
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import date
from typing import Callable, Dict, List, Optional

try:  # package context (Hermes plugin) or flat import (tests)
    from . import discovery as vdisc
    from . import universe as U
    from . import world as W
    from .birth import BIRTHS_KEY
except ImportError:  # pragma: no cover
    import discovery as vdisc
    import universe as U
    import world as W
    from birth import BIRTHS_KEY

canon_digest = vdisc.canon_digest   # public derivation lives in discovery.py

POD_SIZE = 4          # creatures released per skill-species
EIDOS_RANGE = (0.6, 1.9)   # founding energy boost for skill-species


def genome_of_digest(digest: bytes) -> dict:
    return W.genome_from_bytes(digest[:24])


def eidos_id(digest: bytes) -> str:
    return "Eidos_" + digest[:3].hex()


def _release_pod(w, digest: bytes, lineage: str, bs) -> List:
    made = []
    for _ in range(POD_SIZE):
        made.append(W.Creature(
            gid=w.next_gid, genome=genome_of_digest(digest),
            x=bs.uint(2, w.w), y=bs.uint(2, w.h),
            energy=EIDOS_RANGE[0] + (EIDOS_RANGE[1] - EIDOS_RANGE[0])
            * bs.uint(2, 65536) / 65536,
            lineage=lineage))
        w.next_gid += 1
    w.creatures.extend(made)
    return made


def _world_stream_digest(s, kit_digest: bytes, era: int) -> bytes:
    """Keyed, era-salted Big Bang for worlds that must NOT replay.

    Era 1 with a canon kit stays PUBLIC (canon_digest) so every fresh user's
    first dish is the same Big Bang. Any later era is keyed by the (rotated)
    universe key and salted with the era: the same skill kit can never
    regenerate the same world twice.
    """
    key = U.get_or_create_key(s)
    return hmac.new(key, b"vivarium-world-v1\x00" + era.to_bytes(4, "big")
                    + b"\x00" + kit_digest, hashlib.sha256).digest()


def seed(s, skills: List[dict],
         save_world: Callable[[object], None]) -> Optional[dict]:
    """Seed a dormant universe from discovered skills.

    Each skill -> one Eidos species (POD_SIZE creatures) + its ID. Canon
    skills use the public domain-separated digest; private skills use the
    keyed HMAC. The world is born from the digest of ALL canon skill bytes
    (the Big Bang = the user's actual starting kit, same for everyone who
    runs the same stock set — and nobody's private skills touch it).

    Era 1 with a canon kit: public Big Bang (shared mythology). Era >= 2:
    the stream is keyed + era-salted, so restart never replays the same
    world — the species roster stays comparable, the arena does not.
    """
    rec = U.universe_record(s)
    if rec["status"] != "dormant":
        return None
    if not skills:
        return None
    era = rec.get("era", 1)
    canon = [sk for sk in skills if sk["is_canon"]]
    priv = [sk for sk in skills if not sk["is_canon"]]

    # Big Bang: canonical kit hash (domain-separated, public, order-sorted)
    kit = b"\x00".join(sorted(sk["name"].encode() + b"\x01" + sk["bytes"]
                              for sk in canon))
    kit_digest = canon_digest(kit) if canon else hashlib.sha256(
        b"no-canon-kit").digest()
    if era == 1 and canon:
        bang = W.ByteStream(kit_digest)          # public: the shared Big Bang
    else:
        bang = W.ByteStream(_world_stream_digest(s, kit_digest, era))
    w = W.new_world_from_digest(bang.take(32))

    # canon species: plain-hash derivation (public namespace)
    canon_species = []
    births = s.get(BIRTHS_KEY, {}) or {}
    for sk in canon:
        d = canon_digest(sk["bytes"])
        _release_pod(w, d, eidos_id(d), bang)
        canon_species.append({"name": sk["name"], "eidos": eidos_id(d)})
        births[sk["name"]] = {"eidos": eidos_id(d), "day": date.today().isoformat(),
                              "pod": POD_SIZE, "digest_fp": d[:8].hex(),
                              "era": era}

    # private species: keyed derivation (unique per universe)
    priv_species = []
    for sk in priv:
        d = U.skill_digest(s, sk["bytes"].decode("utf-8", errors="replace"))
        _release_pod(w, d, eidos_id(d), bang)
        priv_species.append({"name": sk["name"], "eidos": eidos_id(d)})
        births[sk["name"]] = {"eidos": eidos_id(d), "day": date.today().isoformat(),
                              "pod": POD_SIZE, "digest_fp": d[:8].hex(),
                              "era": era}
    s.set(BIRTHS_KEY, births)

    U.save_seed_record(s, {
        "day": date.today().isoformat(),
        "canon": [sp["eidos"] for sp in canon_species],
        "private": [sp["eidos"] for sp in priv_species],
        "bang_hex": bang.take(8).hex(),
    })
    rec["status"] = "live"
    rec["genesis"] = {"skill": f"seed:{len(canon_species)}+{len(priv_species)}",
                      "day": date.today().isoformat()}
    s.set(U.UNIVERSE_REC, rec)
    save_world(w)
    return {"world": w, "record": rec,
            "canon_species": canon_species, "private_species": priv_species}


def onboard_message(result: dict) -> str:
    """The dormant-state prompt / birth announcement."""
    if not result:
        return ("Your universe awaits. No skills to seed and no spark yet — "
                "the next skill this agent learns will be the Big Bang.")
    r = result["record"]
    cs, ps = result["canon_species"], result["private_species"]
    lines = [f"🌌 Universe born (era {r.get('era', 1)}). "
             f"Seeded {len(cs) + len(ps)} species from your skills."]
    if cs:
        lines.append(f"  • {len(cs)} canon founders — the stock kit every "
                     f"Hermes starts with (the Founding Forty).")
    if ps:
        lines.append(f"  • {len(ps)} private species — derived from YOUR skills, "
                     f"unlike anyone else's.")
    lines.append("  The Hadean die-off begins: only lineages that fit the "
                 "ecology survive. I'll report at dawn.")
    return "\n".join(lines)
