"""VIV-10: pattern detectors + the Codex (discovery record).

The Pulse detector: watches the population curve and records the
boom -> stasis -> crash -> recovery oscillation when a full cycle completes
with a measurable period. The Codex lives in plugin state under ``"codex"``
(personal, authoritative); ``export_codex`` renders the shareable artifact.

Honesty rules (constitution): a pattern enters the Codex only when *observed
in the live dish* with its evidence attached; detector thresholds are fixed
constants, not vibes; nothing is ever seeded or invented.
"""
from __future__ import annotations

from typing import Dict, List, Optional

try:  # package context (Hermes plugin) or flat import (tests)
    from . import world as W
except ImportError:  # pragma: no cover
    import world as W

CODEX_KEY = "codex"

# ── Pulse detector constants ─────────────────────────────────────────────────
# A Pulse = a full boom-crash-recovery cycle in the population curve:
#   crash:  pop drops below CRASH_FRACTION * running peak
#   boom:   pop then returns above BOOM_FRACTION * that peak
# The period is the tick distance between successive boom starts.
CRASH_FRACTION = 0.5      # "crash" when pop < 50% of recent peak
BOOM_FRACTION = 0.85      # "recovered" when pop >= 85% of that peak
MIN_PERIOD = 100          # shorter cycles = noise, not a Pulse
MIN_PEAK = 15             # populations this small crash for any reason
MIN_BOOM_RATIO = 2.5      # the boom must reach 2.5x the pre-boom trough
                          # (an extinction spiral is not a Pulse)
STATE_KEY = "pulse_state"  # per-universe detector memory (in plugin state)
STILL_LIFE_TOLERANCE = 0.03   # plateau: pop within 3% of its plateau level
STILL_LIFE_TICKS = 1500       # ...held for at least 1500 ticks


def detect_still_life(curve: List[dict], state: Optional[dict] = None) -> Optional[dict]:
    """Still Life: population pinned at the cap for a long stretch.

    Fires when the population stays within STILL_LIFE_TOLERANCE of the
    running maximum for at least STILL_LIFE_TICKS (sampled ticks). This is
    the ecological plateau — the live dish's actual steady state — and the
    raw signal for the stale-universe suggestion (VIV-11).
    """
    if state is None:
        state = {}
    start = state.get("plateau_start_tick", None)
    plateau_pop = state.get("plateau_pop", None)
    fired = False
    for sample in curve:
        tick, pop = sample["tick"], sample["population"]
        if plateau_pop is None or abs(pop - plateau_pop) > STILL_LIFE_TOLERANCE * plateau_pop:
            # plateau broken (or never started): reset the window
            start, plateau_pop = tick, pop
            state["plateau_start_tick"], state["plateau_pop"] = start, plateau_pop
            continue
        if start is not None and tick - start >= STILL_LIFE_TICKS and not fired:
            fired = True
            state["plateau_start_tick"] = tick  # re-arm for the next plateau
            return {
                "pattern": "still_life",
                "period": None,
                "evidence": {
                    "population": plateau_pop,
                    "from_tick": start,
                    "to_tick": tick,
                    "duration_ticks": tick - start,
                },
            }
        state["plateau_start_tick"], state["plateau_pop"] = start, plateau_pop
    return None


# ── VIV-11: curve sampling, staleness, cause attribution ─────────────────────
CURVE_KEY = "curve"        # bounded population curve in plugin state
SAMPLE_EVERY = 10          # sample the curve at least this often (ticks)
CURVE_MAX = 2000           # ~20k ticks of history; tiny vs the 10MB quota
SCAN_KEY = "scanned_through"  # detector memory: last tick already scanned
PLATEAU_END_WINDOW = 300   # a birth within this window before the end counts


def observe(s, w, summaries, day: Optional[str] = None) -> List[str]:
    """The wiring point: sample the curve, run detectors, record discoveries.

    Called from ``state.advance`` on every real advance (tool calls, cron).
    Keeps detector memory per-universe in plugin state; feeds detectors only
    the NEW samples since the last scan so discoveries never double-count.
    Returns narration lines for anything new (queued into the next turn).
    """
    if day is None:
        from datetime import date
        day = date.today().isoformat()
    curve = s.get(CURVE_KEY, []) or []
    for sm in summaries:
        if sm["tick"] % SAMPLE_EVERY == 0:
            curve.append({"tick": sm["tick"], "population": sm["population"],
                          "born": sm["born"]})
    if not curve:
        return []
    curve[:] = curve[-CURVE_MAX:]
    s.set(CURVE_KEY, curve)

    pulse_state = s.get(STATE_KEY, {}) or {}
    sl_state = s.get("still_life_state", {}) or {}
    narrations: List[str] = []

    # plateau state BEFORE the detectors run (they reset it on a break)
    plateau_before = sl_state.get("plateau_pop", None)
    plateau_end_tick = None

    for state_key, detector, label in ((STATE_KEY, detect_pulse, "Pulse"),
                                       ("still_life_state", detect_still_life,
                                        "Still life")):
        state = pulse_state if state_key == STATE_KEY else sl_state
        cut = state.get(SCAN_KEY, 0)
        fresh = [c for c in curve if c["tick"] > cut]
        if not fresh:
            continue
        found = detector(fresh, state)
        state[SCAN_KEY] = fresh[-1]["tick"]
        if state_key == STATE_KEY:
            pulse_state = state
        else:
            sl_state = state
        if found:
            record_discovery(s, found, day)
            ev = found.get("evidence", {})
            narrations.append(
                f"📖 Codex entry: {label} confirmed — "
                + (f"period ~{found['period']} ticks" if found.get("period")
                   else f"population {ev.get('population')} held "
                        f"{ev.get('duration_ticks')} ticks")
                + ". The dish has a new pattern.")

    # plateau break → cause attribution (the Codex becomes a linked history)
    end_pop = curve[-1]["population"]
    if plateau_before is not None and abs(end_pop - plateau_before) \
            > STILL_LIFE_TOLERANCE * plateau_before:
        plateau_end_tick = curve[-1]["tick"]
    s.set(STATE_KEY, pulse_state)
    s.set("still_life_state", sl_state)
    if plateau_end_tick is not None:
        _close_still_life(s, plateau_end_tick)

    return narrations


def _close_still_life(s, end_tick: int) -> None:
    """Append the ending chapter (tick + cause) to the open Still Life entry."""
    codex = codex_all(s)
    for entry in codex:
        if entry.get("pattern") == "still_life" and "ended" not in entry:
            cause = attribute_still_life_end(s, end_tick)
            entry["ended"] = {"tick": end_tick, "cause": cause}
            s.set(CODEX_KEY, codex)
            return


def staleness(curve: List[dict], w=None) -> dict:
    """Is this universe going stale? Evidence-based, plain-language.

    Pure function of the sampled curve + the live world (no state reads, so
    tests can pass fixtures directly). Signals:
    - population flat within STILL_LIFE_TOLERANCE for >= 2000 ticks
    - zero births in the window while creatures are alive
    - half the population is elders with no newborns (aging out)
    - <= 2 lineages alive (diversity drained)

    Returns {"verdict", "detail", "suggestion"}: a nudge, never an action —
    restarts are always the user's explicit call.
    """
    window = curve[-200:] if len(curve) >= 200 else curve
    if len(window) < 20:
        return {"verdict": "young",
                "detail": "not enough history to judge (need ~2000 ticks)",
                "suggestion": None}
    pops = [c["population"] for c in window]
    span = window[-1]["tick"] - window[0]["tick"] + 10  # +1 sample spacing
    pmax, pmin = max(pops), min(pops)
    flat = (pmax - pmin) <= STILL_LIFE_TOLERANCE * max(1, pmax)
    reasons = []
    if flat and span >= 2000:
        reasons.append(f"population flat at {pmax} for {span} ticks")
    births = window[-1].get("born", 0) - window[0].get("born", 0)
    if births <= 0 and pmax > 0:
        reasons.append(f"no births in the last {span} ticks")
    if w is not None and w.creatures:
        a = W.age_stats(w)
        if a.get("elders", 0) > 0.5 * len(w.creatures) and a.get("newborns") == 0:
            reasons.append("population aging out with no newborns")
        lineages = len({c.lineage for c in w.creatures})
        if lineages <= 2:
            reasons.append(f"only {lineages} lineages alive")
    if not reasons:
        return {"verdict": "healthy",
                "detail": "population and diversity look alive",
                "suggestion": None}
    return {
        "verdict": "stale",
        "detail": "; ".join(reasons),
        "suggestion": ("/vivarium restart — end this era and let the next "
                       "skill trigger a new Big Bang (fossils and Codex carry "
                       "over)"),
    }


def attribute_still_life_end(s, end_tick: int,
                             window: int = PLATEAU_END_WINDOW) -> Optional[str]:
    """Why did a plateau end? Cross-reference the birth registry by tick.

    Returns a cause string (Eidos ID only — skill names never leave the
    machine), or None when no speciation event explains the break.
    """
    births = s.get("births", {}) or {}
    best = None
    for name, rec in births.items():
        bt = rec.get("tick")
        if not bt:
            continue
        if end_tick - window <= bt <= end_tick + 50:
            dist = abs(end_tick - bt)
            if best is None or dist < best[0]:
                best = (dist, rec.get("eidos", "?"))
    if best is None:
        return None
    return f"speciation event — {best[1]}"


def detect_pulse(curve: List[dict], state: Optional[dict] = None) -> Optional[dict]:
    """Scan the population curve; return a Pulse discovery when one completes.

    ``curve`` = list of {"tick": t, "population": p} samples (oldest first,
    uniformly sampled). ``state`` = persistent detector memory across calls
    (peak, in_crash, crash_start_tick, boom_start_tick). Returns
    {"pattern": "pulse", "period": ..., "evidence": {...}} or None.
    """
    if state is None:
        state = {}
    peak = state.get("peak", 0)
    in_crash = state.get("in_crash", False)
    crash_start = state.get("crash_start_tick", None)
    boom_start = state.get("boom_start_tick", None)
    last_pop = state.get("last_pop", None)
    baseline = state.get("baseline", None)
    trough = state.get("trough", None)

    for sample in curve:
        tick, pop = sample["tick"], sample["population"]
        peak = max(peak, pop)
        trough = pop if trough is None else min(trough, pop)
        state["trough"] = trough
        if last_pop is not None:
            # entering a crash: fall below half of the recent peak.
            # The peak must ALSO be a real boom (>= 2.5x the lowest trough
            # seen before this cycle) — an extinction spiral is not a Pulse.
            if (not in_crash and pop < CRASH_FRACTION * peak
                    and peak >= MIN_PEAK
                    and (trough is None or peak >= MIN_BOOM_RATIO * trough)):
                in_crash = True
                crash_start = tick
            # exiting the crash: climb back to most of the peak
            elif in_crash and pop >= BOOM_FRACTION * peak:
                if boom_start is not None:
                    period = tick - boom_start
                    if period >= MIN_PERIOD:
                        result = {
                            "pattern": "pulse",
                            "period": period,
                            "evidence": {
                                "peak_population": peak,
                                "crash_start_tick": crash_start,
                                "recovery_tick": tick,
                                "min_fraction": CRASH_FRACTION,
                            },
                        }
                        # reset tracker AFTER a completed cycle
                        state.update(peak=pop, in_crash=False,
                                     crash_start_tick=None, boom_start_tick=tick,
                                     last_pop=pop)
                        return result
                boom_start = tick
                in_crash = False
                state.update(peak=pop, in_crash=False, crash_start_tick=None,
                             boom_start_tick=boom_start, last_pop=pop)
                peak = pop
                continue
            elif (not in_crash and boom_start is None
                  and pop >= BOOM_FRACTION * peak):
                # arm: this boom is the cycle's starting gun
                boom_start = tick
        last_pop = pop
        state.update(peak=peak, in_crash=in_crash, crash_start_tick=crash_start,
                     boom_start_tick=boom_start, last_pop=last_pop)
    return None


# ── Codex storage ─────────────────────────────────────────────────────────────
def codex_all(s) -> List[dict]:
    return s.get(CODEX_KEY, [])


def record_discovery(s, discovery: dict, day: str) -> dict:
    """Append a discovery with its first-seen day; dedupe by pattern+period."""
    codex = codex_all(s)
    for entry in codex:
        if entry["pattern"] == discovery["pattern"] and \
                entry.get("period") == discovery.get("period"):
            # same pattern, same period: extend the observation count instead
            entry["times_observed"] = entry.get("times_observed", 1) + 1
            entry["last_seen"] = day
            s.set(CODEX_KEY, codex)
            return entry
    entry = {**discovery, "first_seen": day, "times_observed": 1}
    codex.append(entry)
    s.set(CODEX_KEY, codex)
    return entry


def export_codex(s) -> str:
    """The shareable artifact: markdown, no key material, no skill names."""
    codex = codex_all(s)
    if not codex:
        return "# Vivarium Codex\n\nNo discoveries recorded yet. Keep watching the dish."
    lines = ["# Vivarium Codex", "",
             "Patterns discovered in a live universe. One physics, many dishes.", ""]
    for e in codex:
        title = e["pattern"].replace("_", " ").capitalize()
        lines.append(f"## {title}")
        if e.get("period") is not None:
            lines.append(f"- Period: ~{e['period']} ticks")
        else:
            lines.append("- Pattern type: steady state")
        ev = e.get("evidence", {})
        if "population" in ev:
            lines.append(f"- Population: {ev['population']}")
        if "duration_ticks" in ev:
            lines.append(f"- Held for: {ev['duration_ticks']} ticks")
        if "peak_population" in ev:
            lines.append(f"- Peak population: {ev['peak_population']}")
        lines.append(f"- First observed: {e.get('first_seen', '?')}"
                     f" (seen {e.get('times_observed', 1)}x)")
        lines.append("")
    return "\n".join(lines)
