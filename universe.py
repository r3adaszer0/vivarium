"""Universe lifecycle — genesis, status, restart, fossils.

Design contract (the Four Rules, applied to identity):

* Rule 1 (not random): the *dynamics* contain no randomness. The universe key
  is the single entropy event in the whole system — it happens once, at
  universe creation, OUTSIDE the simulation. It is not part of the dynamics;
  it is the choice of which universe you inhabit (physical constants). After
  key creation, every value this module produces is a pure function of
  (key, skill content).
* Rule 4 (private): the key never leaves the machine (plugin state is written
  0600 by Hermes). Only key *fingerprints* (8 hex) are ever stored alongside
  records, and only day-granularity dates.
* Lifecycle: dormant (awaiting first skill) -> live (Big Bang happened)
  -> [stale/dead are judgments the tools layer makes] -> restart -> dormant,
  with the old universe's champions archived as fossils (cross-universe).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import date
from typing import Any, Callable, Dict, List, Optional

try:  # package context (Hermes plugin) or flat import (tests)
    from . import world as vworld
except ImportError:  # pragma: no cover
    import world as vworld

UNIVERSE_KEY = "universe_key"     # secret, b64 — never rendered, never synced
UNIVERSE_REC = "universe"         # public record (fingerprint only)
FOSSILS = "fossils"               # cross-universe champion archive
FOSSIL_CAP = 50


def _fp(key: bytes) -> str:
    """8-hex fingerprint of a universe key — safe to store and display."""
    return hashlib.sha256(key).hexdigest()[:8]


def get_or_create_key(s) -> bytes:
    """The one entropy event. Generated once per universe, kept in plugin state."""
    raw = s.get(UNIVERSE_KEY)
    if not raw:
        raw = base64.b64encode(secrets.token_bytes(32)).decode()
        s.set(UNIVERSE_KEY, raw)
    return base64.b64decode(raw)


def universe_record(s) -> dict:
    """Ensure a record exists (dormant until the first skill triggers genesis)."""
    rec = s.get(UNIVERSE_REC)
    if not rec:
        rec = {
            "v": 1,
            "status": "dormant",          # dormant | live
            "key_fp": _fp(get_or_create_key(s)),
            "genesis": None,              # {"skill", "digest_hex", "eidos", "day"}
            "era": 1,
            "previous_fp": None,
        }
        s.set(UNIVERSE_REC, rec)
    return rec


def skill_digest(s, skill_content: str) -> bytes:
    """HMAC-SHA256(universe_key, skill_content) — deterministic per universe,
    different across universes (privacy: see compendium Part 4/7)."""
    return hmac.new(get_or_create_key(s), skill_content.encode("utf-8"),
                    hashlib.sha256).digest()


def genesis(s, skill_name: str, skill_content: str,
            save_world: Callable[[Any], None]) -> Optional[dict]:
    """Big Bang: the first skill ever learned creates the universe.

    Returns {"world", "record", "eidos", "digest"} or None when already live
    (subsequent skills go through the perturbation operator, part 2).
    """
    rec = universe_record(s)
    if rec["status"] == "live":
        return None
    digest = skill_digest(s, skill_content)
    eidos = "Eidos_" + digest[:3].hex()
    # the genesis species itself: genome straight from the first 24 digest bytes
    founder_genome = vworld.genome_from_bytes(digest[:24])
    founder = vworld.Creature(
        gid=1, genome=founder_genome, x=vworld._uint(digest[:4]) % vworld.GRID_W,
        y=vworld._uint(digest[4:8]) % vworld.GRID_H, energy=1.4, lineage=eidos)
    w = vworld.new_world_from_digest(digest, founders_extra=[founder])
    save_world(w)
    rec.update({
        "status": "live",
        "genesis": {"skill": skill_name, "digest_hex": digest.hex(),
                    "eidos": eidos, "day": date.today().isoformat()},
    })
    s.set(UNIVERSE_REC, rec)
    return {"world": w, "record": rec, "eidos": eidos, "digest": digest}


def add_fossil(s, lineage: str, genome: dict, universe_fp: str) -> None:
    """Archive a champion genome (deduped by lineage, capped)."""
    fossils = s.get(FOSSILS, [])
    if any(f["lineage"] == lineage for f in fossils):
        return
    fossils.append({"lineage": lineage, "genome": genome,
                    "universe": universe_fp, "day": date.today().isoformat()})
    s.set(FOSSILS, fossils[-FOSSIL_CAP:])


SEED_REC = "seed_record"


def save_seed_record(s, payload: dict) -> None:
    """Day-granularity record of the seeding event (privacy: no timestamps)."""
    s.set(SEED_REC, payload)


def get_seed_record(s) -> Optional[dict]:
    return s.get(SEED_REC)


def restart(s, load_world: Optional[Callable[[], Any]] = None,
            clear_world: Optional[Callable[[], None]] = None,
            reason: str = "") -> dict:
    """End this universe, archive its champions as fossils, begin a new one.

    A restart is a NEW universe: fresh key (new physics), dormant status,
    era+1. Fossils persist across universes by design — extinction becomes
    archaeology, and old champions can be re-released into any new dish.
    """
    rec = universe_record(s)
    old_fp = rec.get("key_fp")
    if rec["status"] == "live" and load_world is not None:
        try:
            w = load_world()
            for lineage, _count in vworld.stats(w).get("lineages", []):
                champ = next((c for c in w.creatures if c.lineage == lineage), None)
                if champ is not None:
                    add_fossil(s, lineage, dict(champ.genome), old_fp or "")
        except Exception:
            pass  # archiving is best-effort; the restart itself must not fail
    if clear_world is not None:
        clear_world()
    new_rec = {
        "v": 1,
        "status": "dormant",
        "key_fp": _fp(get_or_create_key(s)),
        "genesis": None,
        "era": rec.get("era", 1) + 1,
        "previous_fp": old_fp,
        "restart_reason": reason,
    }
    # rotate the key BEFORE regenerating the fingerprint: new universe = new physics
    s.set(UNIVERSE_KEY, base64.b64encode(secrets.token_bytes(32)).decode())
    new_rec["key_fp"] = _fp(get_or_create_key(s))
    s.set(UNIVERSE_REC, new_rec)
    return new_rec
