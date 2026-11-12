"""VIV-21: scenario protocol — deterministic, shareable ecology experiments.

A scenario is a sealed, self-contained experiment: a fixed genesis digest
(terrain + neutral founders), a fixed lineup of contestant strains (from
challenge codes), and a fixed run length. Everyone who runs the same
scenario code gets a bit-identical dish — same weather, same food, same
starting field — so results are comparable across machines, profiles and
time. The Gauntlet (VIV-13) is built directly on this: scenarios are the
races, imported strains are the entrants.

Design rules honored:
- Rule 1 (not random): the scenario's hash chain derives everything from
  (seed label, ticks, contestants) — no RNG anywhere.
- Rule 2 (mathematically sound): the scorer is survival-weighted;
  a strain that goes extinct early cannot win late.
- Rule 4 (private): scenario codes carry only genome JSON + a public
  seed label — no universe keys, no skill names, no skill content.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Callable, Dict, List, Optional, Tuple

try:  # package mode (Hermes plugin)
    from . import world as W
    from . import state as S
except ImportError:  # flat mode (tests)
    import world as W
    import state as S

# domain separation for the scenario hash chain
SCENARIO_DOMAIN = b"VIVARUM-SCENARIO-v1"

# default match length — long enough for selection to act, short enough
# to run interactively (48x48 grid, bounded population)
SCENARIO_TICKS = 1200
SCENARIO_FOUNDERS = 24            # neutral local founders (the "field")
MAX_CONTESTANTS = 8               # keep contests legible (<=8 strains)
POD_PER_CONTESTANT = 4            # each entrant lands a pod of 4
FEE_TICKS = 15                    # pre-release settle: natives germinate,
                                  # contestants land co-equal (measured: with a
                                  # long settle the cap-bound incumbents squeeze
                                  # every newcomer to extinction — establishment
                                  # becomes arrival luck, not genome quality.
                                  # Early release makes the race about fitness
                                  # from tick one; verified: a strong strain
                                  # holds ~1/3 of a capped dish for 1000+ ticks)


# ── code format ──────────────────────────────────────────────────────────────
def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _b64d(s: str) -> Optional[bytes]:
    try:
        return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
    except Exception:
        return None


def scenario_hash(seed_label: str, ticks: int) -> bytes:
    """Public, versioned, domain-separated scenario seed.

    Deterministic and shareable BY CONSTRUCTION: anyone with the same
    (seed_label, ticks) derives the same genesis. No secret material —
    scenario hashes never touch the universe key (Rule 4).
    """
    header = SCENARIO_DOMAIN + b"|" + str(int(ticks)).encode() + b"|"
    return hashlib.sha256(header + seed_label.encode("utf-8")).digest()


def encode_scenario(seed_label: str, ticks: int = SCENARIO_TICKS,
                    contestants: Optional[List[str]] = None) -> str:
    """Scenario code: SCEN1 + b64(json{seed, ticks, contestants[]}).

    Contestants are challenge codes (VIV1...) — genome-only, so a scenario
    code leaks nothing about who bred the strain or where it came from.
    """
    payload = {"seed": seed_label, "ticks": int(ticks),
               "contestants": list(contestants or [])}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "SCEN1" + _b64e(blob.encode())


def decode_scenario(code: str) -> Optional[dict]:
    """Parse a scenario code; None on any malformed input."""
    code = code.strip()
    if not code.startswith("SCEN1"):
        return None
    raw = _b64d(code[5:])
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    seed = payload.get("seed")
    ticks = payload.get("ticks", SCENARIO_TICKS)
    contestants = payload.get("contestants", [])
    if not isinstance(seed, str) or not seed.strip():
        return None
    if not isinstance(ticks, int) or not (10 <= ticks <= 20000):
        return None
    if not isinstance(contestants, list) or \
            not all(isinstance(c, str) for c in contestants) or \
            len(contestants) > MAX_CONTESTANTS:
        return None
    return {"seed": seed.strip(), "ticks": ticks, "contestants": contestants}


# ── building the dish ────────────────────────────────────────────────────────
def entry_digests(spec: dict) -> List[Tuple[str, bytes]]:
    """(label, digest) per valid contestant; invalid codes are skipped.

    Label = a 7-char hex tag derived from the genome digest itself
    (collision-free across contestants, stable everywhere, no PII).
    The digest hashes the genome JSON — same genome, same label+digest,
    on every machine. B64 codes share long prefixes (same JSON keys),
    so code prefixes are NOT safe labels.
    """
    out: List[Tuple[str, bytes]] = []
    seen = set()
    for code in spec.get("contestants", []):
        try:
            genome = S.decode_genome(code)
        except ValueError:
            continue          # a hostile (non-finite) code is not a contestant
        if genome is None:
            continue
        # Name the contestant by its species id when the code carries one;
        # otherwise the genome hash stands in (X + 6 hex). A scoreboard
        # row should say who ran, not make the reader decode hex.
        label = S.decode_code_label(code) or ("X" + hashlib.sha256(
            json.dumps({k: round(v, 4) for k, v in genome.items()},
                       sort_keys=True).encode()).digest()[:3].hex())
        digest = hashlib.sha256(
            json.dumps({k: round(v, 4) for k, v in genome.items()},
                       sort_keys=True).encode()).digest()
        if label in seen:            # identical genome listed twice — skip
            continue
        seen.add(label)
        out.append((label, digest))
    return out


def build_dish(spec: dict) -> W.World:
    """Assemble the scenario dish: digest genesis + settling + contestant pods.

    Order of operations (each step hash-driven, no RNG):
      1. genesis world from scenario_hash(seed, ticks) — terrain + 24
         neutral local founders (the "field" every entrant must beat)
      2. settling phase: a SHORT FEE_TICKS advance — natives germinate but
         the cap is far away, so contestants land co-equal (no incumbency
         advantage; measured: late arrivals under a pinned cap always die)
      3. contestant pods: each valid contestant lands POD_PER_CONTESTANT
         members via the standard digest-spread landing rule (top-8 fertile
         cells, digest-ordered) — the same rule a skill-birth uses, so
         scenario results speak to the same dynamics
    """
    digest = scenario_hash(spec["seed"], spec["ticks"])
    w = W.new_world_from_digest(digest)

    # settling phase
    if FEE_TICKS:
        W.run(w, FEE_TICKS, nutrients_per_tick=0.0)

    # contestant pods — same digest-driven spread landing as birth.py
    for label, edigest in entry_digests(spec):
        cells = sorted(((w.food[y][x], x, y) for y in range(w.h)
                        for x in range(w.w)), key=lambda t: -t[0])
        top = cells[:min(8, len(cells))]
        genome = genome_for_label(spec, label)
        assert genome is not None  # entry labels only exist for valid codes
        for i in range(POD_PER_CONTESTANT):
            _, x, y = top[int.from_bytes(edigest[24 + i:26 + i], "big") % len(top)]
            w.creatures.append(W.Creature(
                gid=w.next_gid, genome=dict(genome),
                x=x, y=y, energy=2.5, lineage=label,
            ))
            w.next_gid += 1

    w.peak_population = len(w.creatures)
    return w


def genome_for_label(spec: dict, label: str) -> Optional[Dict[str, float]]:
    """The genome a contestant label refers to.

    Labels come from the code's own id when it carries one, else the
    genome hash (X + 6 hex) - match either.
    """
    import hashlib as _h
    for code in spec.get("contestants", []):
        if S.decode_code_label(code) == label and label is not None:
            try:
                g = S.decode_genome(code)
            except ValueError:
                continue
            if g is not None:
                return g
        try:
            genome = S.decode_genome(code)
        except ValueError:
            continue
        if genome is None:
            continue
        blob = json.dumps({k: round(v, 4) for k, v in genome.items()},
                          sort_keys=True).encode()
        if "X" + _h.sha256(blob).digest()[:3].hex() == label:
            return genome
    return None


def run_scenario(spec: dict,
                 progress: Optional[Callable[[int, dict], None]] = None) -> dict:
    """Run the scenario to completion; return the full results dict.

    ``progress`` (optional) is called as progress(tick, stats) after each
    advance chunk — the Gauntlet renderer uses it to draw progress bars.
    """
    w = build_dish(spec)
    census: Dict[str, List[int]] = {}
    summaries = []
    while w.tick < spec["ticks"]:
        summaries.append(W.tick_world(w, 0.0))
        counts: Dict[str, int] = {}
        for c in w.creatures:
            counts[c.lineage] = counts.get(c.lineage, 0) + 1
        for name in list(census) + list(counts):
            curve = census.setdefault(name, [])
            while len(curve) < w.tick:
                curve.append(0)          # fill extinct/prenatal gaps
        for name, n in counts.items():
            census[name].append(n)
        if w.tick % 60 == 0 and progress:
            progress(w.tick, W.stats(w))
    return results(w, summaries, census)


# ── scoring ──────────────────────────────────────────────────────────────────
def results(w: W.World, summaries: List[dict],
            census: Dict[str, List[int]]) -> dict:
    """Score the finished dish.

    Scorer (Rule 2: survival-weighted, simple to explain, hard to game):
      score = Σ over ticks of (strain's alive count) — the area under the
      strain's population curve. Late extinction still scores; early
      extinction doesn't; a strain that cannot hold territory cannot fake
      fitness. The native field lineages score too — beating the field is
      the meaningful comparison.
    """
    curves = {k: v for k, v in census.items() if any(v)}

    scores = {name: sum(curve) for name, curve in curves.items()}
    ranking = sorted(scores, key=lambda k: (-scores[k], k))

    return {
        "ticks": w.tick,
        "population": len(w.creatures),
        "peak": w.peak_population,
        "curves": curves,
        "scores": scores,
        "ranking": ranking,
    }


def format_results(res: dict) -> str:
    """Plain-language scoreboard."""
    lines = [f"Scenario finished — {res['ticks']} ticks, "
             f"{res['population']} creatures alive."]
    for i, name in enumerate(res["ranking"], start=1):
        curve = res["curves"].get(name, [])
        peak = max(curve) if curve else 0
        final = curve[-1] if curve else 0
        lines.append(
            f"  {i}. {name:<14} score {res['scores'][name]:>7,}"
            f"   peak {peak:>3}   final {final:>3}"
        )
    return "\n".join(lines)
