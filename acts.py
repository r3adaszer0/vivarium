"""The walkthrough acts (VIV-31) — the story that teaches the dish.

Four timed acts + two event-driven acts, each shown ONCE per universe:

  act 1  dormant      first turn on a dormant universe (survives narration off)
  act 2  big bang     the first skill: what the dish is, DNA-from-skills,
                      the loop (your work feeds it; the next skill births
                      a new species)
  act 3  first hermi  the second birth: meet one species by name (show),
                      watch life happen (clip), the competitive horizon
  act 4  multiplayer  the third birth: export -> share -> race
  act-codex           first Codex discovery: the Codex introduces itself
                      (this IS the genetics-deep lesson, live)
  act-death           first lineage extinction: extinctions are how this
                      world selects; the record stays in the Codex

Narration-off mode ("/vivarium narration off"): acts 2-4, codex and
death walkthroughs are suppressed; bare birth lines (name + ID only)
still fire, and the dormant brief (act 1) stays — it IS the minimum.

All copy is em-dash-free by design (user rule: remove unless needed).
"""
from __future__ import annotations

import re

from typing import Dict, Optional

try:  # package context (Hermes plugin) or flat import (tests)
    from . import identity as vident
except ImportError:  # pragma: no cover
    import identity as vident

ACTS_KEY = "acts"            # {act_id: day} — each act fires once
NARRATION_KEY2 = "narration"  # "on" | "off" (prose mode; NOT media_pref)

ACT1 = "dormant"
ACT2 = "big_bang"
ACT3 = "first_hermi"
ACT4 = "multiplayer"
ACT_CODEX = "codex"
ACT_DEATH = "death"


def _acts(s) -> Dict[str, str]:
    return s.get(ACTS_KEY, {}) or {}


def _seen(s, act: str) -> bool:
    return act in _acts(s)


def _mark(s, act: str) -> None:
    from datetime import date
    acts = _acts(s)
    acts[act] = date.today().isoformat()
    s.set(ACTS_KEY, acts)


def narration_on(s) -> bool:
    """True unless the voice is off, read from the state passed in."""
    try:
        from . import state as vstate
    except ImportError:  # pragma: no cover
        import state as vstate
    raw = s.get(vstate._VOICE_KEY, vstate._VOICE_DEFAULT)
    raw = vstate._LEGACY_VOICE.get(raw, raw)
    return raw != "off"


def set_narration(s, mode: str) -> str:
    """Legacy shim: write the voice mode on the state passed in."""
    try:
        from . import state as vstate
    except ImportError:  # pragma: no cover
        import state as vstate
    mode = "milestones" if mode == "on" else mode
    s.set(vstate._VOICE_KEY, mode)
    return mode


# ── act copy ─────────────────────────────────────────────────────────────────
# Placeholder where the dish picture belongs. The plugin's own printer
# splits the narration on it (headline above the image, the explanation
# below); surfaces that cannot paint strip it.
DISH_MARKER = "\n\n[[vivarium:dish]]\n\n"

ACT2_TEXT = (
    "\n\nThis dish is your Vivarium universe. Green is food: pale green is "
    "a rich patch, dark green is sparse, and the empty cells have already "
    "been eaten. The colored squares are artificial lifeforms: your Hermi. "
    "They move, eat and evolve by DNA taken from your skills. Each species "
    "is a fingerprint of one thing your agent learned.\n"
    "Your work feeds it. Using Hermes drops food into the dish: a busy day "
    "is a feast, a quiet day is a famine. Every skill Hermes learns births "
    "a new species. Teach one more and I'll bring the newborn up close: its "
    "name, its DNA, and the first ticks of its life.")


def act2_for(result: dict) -> str:
    """Act 2 appended to the Big Bang narration (em-dash-free)."""
    return ACT2_TEXT


_ART_RE = re.compile(r"<<ART:([^>]*)>>\n(.*?)\n<</ART>>", re.S)

ART_OPEN = "<<ART:"
ART_CLOSE = "<</ART>>"


def strip_art(text: str) -> str:
    """Drop the portrait block: chat surfaces relay text, not pictures."""
    return _ART_RE.sub("", text or "")


def art_block(eidos: str, genome: dict | None = None) -> str:
    """The face, in the text stream.

    The card lifts this out and sets it above the copy. It travels in the
    text because the text is what survives the queue, the state file and
    the relay; a second channel would be one more thing to get wrong.
    """
    try:
        from . import portrait as vport
    except ImportError:  # pragma: no cover - flat-import mode
        import portrait as vport
    lines = vport.sprite_lines(genome=genome, eidos=eidos)
    return f"\n{ART_OPEN}{eidos}>>\n" + "\n".join(lines) + f"\n{ART_CLOSE}\n"


def act3_for(result: dict) -> str:
    eidos = result.get("eidos", "?")
    name = result.get("name", "")
    return (
        art_block(eidos, result.get("genome"))
        + f"\nRemember the promise? A new skill, a new species. Meet your "
        f"newest arrival, born from the skill you just taught me: {eidos}"
        + (f" (from '{name}')" if name else "") + ".\n"
        "One honesty: it is not your first. The Big Bang seeded a whole "
        "founding roster from everything Hermes knew at birth. This one is "
        "just the first you will meet by name.\n"
        f"/vivarium show {eidos} introduces it properly: its face, its "
        "genes, its story.\n"
        "Want to watch life happen? /vivarium clip shows your world as a "
        "short video, the dish frame by frame.\n"
        "Keep using Hermes, your world will keep evolving. When you have "
        "species that survived, I will show you how to compete with your "
        "friends.")


def act4_text() -> str:
    return (
        "\n\nYour dish has been running for a while now. Some lineages "
        "thrived, some are gone. Survival was the filter; what remains is "
        "strong.\n"
        "Time to meet the neighbors. /vivarium export turns any species "
        "into a challenge code: a sealed capsule carrying its genome, never "
        "your skills (those stay yours). Send a code to a friend running "
        "Vivarium; when they release it, your creature competes in their "
        "world.\n"
        "/vivarium race settles any match in a neutral jar: same start, "
        "same rules, deterministic. The scoreboard can be re-run by anyone "
        "to verify. Winners take the bragging rights; the Codex keeps the "
        "record.")


def act_codex_text(discovery_label: str) -> str:
    return (
        f"\n\nThat Codex entry is the first pattern your dish has ever "
        f"revealed: a {discovery_label}. Patterns like this are "
        "discoveries, your creatures' genes made this happen without any "
        "hand of yours. The Codex remembers every pattern the dish shows, "
        "with the evidence. /vivarium codex shows the collection so far.")


def act_death_text(lineage: str) -> str:
    return (
        f"\n\nThe {lineage} lineage has gone extinct. Extinctions are how "
        "this world selects: what survives is what fits. The dish carries "
        "on, and the Codex keeps the record of what was.")


def bare_birth_line(result: dict) -> str:
    """Narration-off mode: name + ID only, no ceremony."""
    return (f"🧬 New species: {result.get('eidos', '?')} "
            f"(from '{result.get('name', '')}'), "
            f"pod of {result.get('pod', '?')} at tick {result.get('tick', '?')}.")


# ── gating ───────────────────────────────────────────────────────────────────
def birth_narration(s, base: str, result: dict, is_big_bang: bool) -> str:
    """The single wiring point for birth narrations.

    Big Bang (act 2), second birth (act 3), third birth (act 4); later
    births get the plain announcement. narration-off: bare line only.
    """
    acts = _acts(s)
    after_bang = acts.get("_births_since_bang", 0)

    def _save():
        s.set(ACTS_KEY, acts)

    def _fire(act: str) -> None:
        from datetime import date
        acts[act] = date.today().isoformat()

    if is_big_bang:
        acts["_births_since_bang"] = 0
        fresh_act2 = ACT2 not in acts
        if fresh_act2:
            _fire(ACT2)
        _save()
        if fresh_act2 and narration_on(s):
            return base + DISH_MARKER + act2_for(result)
        return base
    if not narration_on(s):
        acts["_births_since_bang"] = after_bang + 1
        _save()
        return bare_birth_line(result)
    if after_bang == 0 and ACT3 not in acts:
        _fire(ACT3)
        acts["_births_since_bang"] = 1
        _save()
        return base + DISH_MARKER + act3_for(result)
    if after_bang == 1 and ACT4 not in acts:
        _fire(ACT4)
        acts["_births_since_bang"] = 2
        _save()
        return base + act4_text()
    acts["_births_since_bang"] = after_bang + 1
    _save()
    return base


def codex_narration(s, line: str, label: str) -> str:
    """First discovery: append act-codex once."""
    if narration_on(s) and not _seen(s, ACT_CODEX):
        _mark(s, ACT_CODEX)
        return line + act_codex_text(label)
    return line


def death_narration(s, line: str, lineage: str) -> str:
    """First extinction of a TRACKED lineage: append act-death once."""
    if narration_on(s) and not _seen(s, ACT_DEATH):
        _mark(s, ACT_DEATH)
        return line + act_death_text(lineage)
    return line


def dormant_line(base: str) -> str:
    """Act 1: the dormant brief. Always shown (survives narration-off)."""
    return base
