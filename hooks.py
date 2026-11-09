"""Vivarium's hooks — where the dish meets the agent.

* ``post_tool_call``: every real tool call drops nutrients into the dish and
  (every Nth call) advances the simulation a few ticks. This is the "your work
  feeds the world" mirror.
* ``pre_llm_call``: inject a compact ecology report into the turn so Hermes
  always knows what's alive in its own head. Keeps a small narration budget so
  it never dominates the prompt.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

try:  # package context (Hermes plugin) or flat import (tests)
    from . import state as vstate
    from . import world as vworld
    from . import birth as vbirth
except ImportError:  # pragma: no cover
    import state as vstate
    import world as vworld
    import birth as vbirth

logger = logging.getLogger(__name__)

TICKS_PER_TOOL_CALL = 6       # sim ticks advanced per tool call
NARRATION_EVERY = 4           # inject the ecology report every Nth tool call
_REPORT_TITLE = "🧬 [vivarium]"


def _on_skill_lifecycle(skill_name: str = "", action: str = "",
                        **_: Any) -> None:
    """VIV-7: a newly learned/installed skill births a species (automatic).

    VIV-19b: if the universe is still DORMANT, the first skill triggers the
    Big Bang instead — ``seeding.seed()`` reads every installed skill and
    births the whole founding roster (canon via public digest, private via
    the keyed HMAC). So a fresh user's first skill boots the entire universe
    in one event, exactly as the README promises.
    """
    try:
        if action not in ("created", "installed", "restored"):
            return
        try:
            from . import delivery_trace as vtrace
        except ImportError:  # pragma: no cover - flat-import mode
            import delivery_trace as vtrace
        vtrace.log("skill_event", skill=skill_name, action=action,
                   voice=vstate.voice_mode())
        rec = vstate.universe_record()
        if rec.get("status") != "live":
            vtrace.log("dormant_boot", era=rec.get("era"))
            _boot_from_dormant(rec)
            return
        content = vstate.skill_content(skill_name)
        if content is None:
            return
        result = vbirth.birth_species(
            vstate.state(), skill_name, content,
            save_world=vstate.save_world,
            load_world=vstate.load_world,
        )
        if result:
            try:
                from . import media_policy as vmp
            except ImportError:  # pragma: no cover
                import media_policy as vmp
            try:  # VIV-31: walkthrough acts (act 3/4 on 2nd/3rd birth)
                from . import acts as vacts
            except ImportError:  # pragma: no cover
                import acts as vacts
            base = vbirth.announcement(result)
            narrated = vacts.birth_narration(
                vstate.state(), base, result, is_big_bang=False)
            _deliver_beat(narrated)
    except Exception:
        logger.exception("vivarium on_skill_lifecycle failed (birth skipped)")


def _discover_skills():
    """Indirection for tests: swap to inject a fake skill set."""
    try:
        from . import discovery as vdisc
    except ImportError:  # pragma: no cover
        import discovery as vdisc
    return vdisc.discover()


def _boot_from_dormant(rec: dict) -> None:
    """The Big Bang: first-ever skill event seeds the universe from ALL skills.

    Enumerates every installed skill (canon + private), derives the world
    from the canon kit digest (era 1 = the shared public Big Bang), births
    one species per skill, and queues the onboarding narration.
    """
    try:
        from . import seeding as vseeding
    except ImportError:  # pragma: no cover
        import seeding as vseeding
    skills = _discover_skills()
    if not skills:
        vstate.queue_narration(
            "🌌 A universe sleeps in this agent, waiting for its first "
            "skill. Learn one and the Big Bang fires.", milestone=True)
        return
    result = vseeding.seed(vstate.state(), skills, save_world=vstate.save_world)
    if result:
        try:
            from . import media_policy as vmp
        except ImportError:  # pragma: no cover
            import media_policy as vmp
        try:  # VIV-31: act 2 rides the Big Bang narration
            from . import acts as vacts
        except ImportError:  # pragma: no cover
            import acts as vacts
        base = vseeding.onboard_message(result)
        narrated = vacts.birth_narration(
            vstate.state(), base,
            {"eidos": "", "name": "", "pod": 0, "tick": 0},
            is_big_bang=True)
        _deliver_beat(narrated)


def _nutrients_for(tool_name: str) -> float:
    base = vstate.NUTRIENT_MAP.get(tool_name, vstate.DEFAULT_NUTRIENT)
    return min(1.5, base + 0.05)  # slight flat bonus per call


def _on_post_tool_call(tool_name: str = "", args: Optional[Dict[str, Any]] = None,
                       **_: Any) -> None:
    try:
        if tool_name in ("vivarium_status", "vivarium_render", "vivarium_feed",
                         "vivarium_release"):
            return  # the dish doesn't feed itself (that would be a perpetual-motion dish)
        nutrients = _nutrients_for(tool_name or "unknown")
        vstate.record_activity(tool_name or "unknown", nutrients)
        # VIV-19b: dormant universe — nutrient drops are banked, no dish yet.
        # (Activity is still counted; the Big Bang dish starts fresh at tick 0.)
        rec = vstate.universe_record()
        if rec.get("status") != "live":
            return
        w = vstate.load_world()
        vstate.advance(w, ticks=TICKS_PER_TOOL_CALL, nutrients=nutrients)
        # VIV-46: the dish advances SILENTLY. No per-turn report is ever
        # injected into the agent's context. At most one dawn report per
        # day, and only when the user asked for that voice.
        if vstate.voice_mode() == "daily":
            import datetime as _dt
            today = _dt.date.today().isoformat()
            if vstate.state().get("last_report_day") != today:
                vstate.state().set("last_report_day", today)
                s = vworld.stats(w)
                vstate.queue_narration(_report(s, dramatic_only=False),
                                       kind="report")
    except Exception:
        logger.exception("vivarium post_tool_call failed (dish keeps living on cron)")


def _report(s: dict, dramatic_only: bool = False) -> str:
    if s.get("population", 0) == 0:
        return (f"{_REPORT_TITLE} extinction. The dish is silent at tick {s['tick']}. "
                f"Use vivarium_release to reseed it.")
    lineages = ", ".join(f"{n}×{c}" for n, c in s["lineages"])
    extinct = getattr(_report, "_last_pop", None)
    text = (f"{_REPORT_TITLE} tick {s['tick']}: {s['population']} creatures "
            f"({lineages}); avg energy {s['avg_energy']}.")
    if dramatic_only and extinct is not None and s["population"] < extinct:
        pass
    return text


_DISH_WORDS = (
    "vivarium", "dish", "creature", "hermi", "species", "eidos", "lineage",
    "tick", "codex", "big bang", "evolve", "colony", "feed", "restart",
    "universe",
)


def _mentions_vivarium(text: str) -> bool:
    low = (text or "").lower()
    return any(w in low for w in _DISH_WORDS)


def _on_pre_llm_call(session_id: str = "", user_message: str = "",
                     is_first_turn: bool = False, **_: Any) -> Optional[dict]:
    """VIV-46: the agent hears from Vivarium ONLY when a beat is pending.

    No live-dish report every turn (that is what made Hermes answer
    "how are you?" with creature counts), no dormant bulletin (that is
    what made it answer "hey" with "era 15 ended"). A quiet turn is a
    quiet turn; the dish advances on its own.
    """
    try:
        line = vstate.pop_narration()
        if line:
            return {"context": (
                "🧬 [vivarium] STORY BEAT — relay this to the user in your "
                "reply, verbatim and complete. Do not summarize, do not drop "
                "it, do not treat it as internal context:\n" + line)}
        return None
    except Exception:
        logger.exception("vivarium pre_llm_call failed")
        return None


def register_hooks(ctx) -> None:
    vstate.bind(ctx)
    ctx.register_hook("post_tool_call", _on_post_tool_call)
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
    ctx.register_hook("on_skill_lifecycle", _on_skill_lifecycle)
    # VIV-46: beats never ride tool results any more — the agent's reply
    # belongs to the user. The plugin prints events itself after the turn.
    ctx.register_hook("on_stream_end", _on_stream_end)
    ctx.register_hook("post_llm_call", _on_stream_end)

_PICTURE_PENDING = {"armed": False, "quiet_at": 0.0, "worker": False}


def _on_stream_end(**_):
    """VIV-42: every finished assistant stream updates the quiet clock.

    The picture must be painted when the TURN is over, not when the skill
    hook fires — the model still has reasoning and a reply to print. Each
    stream end pushes the quiet deadline forward; the worker paints once
    the stream has been quiet for a moment (or after a hard cap, so a
    missing hook never leaves the dish unpainted).
    """
    import time as _t
    if _PICTURE_PENDING["armed"]:
        _PICTURE_PENDING["quiet_at"] = _t.time() + 1.0


def _can_paint() -> bool:
    try:
        import sys as _sys
        if not getattr(_sys.stdout, "isatty", lambda: False)():
            return False
        from . import termrender as vterm
        if vterm.detect_graphics() not in ("kitty", "iterm2", "sixel"):
            return False
        from . import media_policy as vmp
        return vmp.media_pref(vstate.state()) == "auto"
    except Exception:
        return False


def _beat_layout(text: str, rows: int, cols: int):
    """Split a beat around the dish marker.

    Returns (printed_text, trail_rows): the headline, a blank spacer for
    the picture, then the explanation; trail_rows is how many lines are
    printed AFTER the spacer, which is exactly what paint_over must climb
    over to land the dish between the two halves.
    """
    try:
        from . import acts as vacts
    except ImportError:  # pragma: no cover
        import acts as vacts
    spacer = "\n".join(" " * cols for _ in range(rows))
    if vacts.DISH_MARKER in text:
        head, _, tail = text.partition(vacts.DISH_MARKER)
        tail = ("\n\n" + tail.strip()) if tail.strip() else ""
    else:
        head, tail = text, ""
    out = "\n" + head.strip() + "\n\n" + spacer + tail + "\n"
    # The final "\n" in `out` moves one row; the spacer itself ends one
    # row short of its height. Net: the cursor sits rows + len(tail
    # newlines) below the spacer's top, so that is exactly the climb.
    trail = tail.count("\n") if tail else 0
    return out, trail


def _deliver_beat(text: str) -> None:
    """VIV-46: queue the beat and arm the printer.

    On an interactive graphics terminal the plugin prints it once the
    turn's last stream ends (see _arm_print); on chat surfaces the beat
    stays in the queue and pre_llm relays it on the next turn. Nothing is
    injected into the agent's reasoning during a normal turn.
    """
    try:
        from . import delivery_trace as vtrace
    except ImportError:  # pragma: no cover
        import delivery_trace as vtrace
    vtrace.log("beat", chars=len(text or ""), voice=vstate.voice_mode(),
               can_paint=_can_paint(),
               queue=len(vstate.narration_text() or ""))
    if _can_paint():
        vstate.queue_narration(text, milestone=True, kind="birth")
        _arm_print()
    else:
        # Chat / gateway: the beat stays queued for the agent to relay,
        # with the media offer so images still reach the user.
        try:
            from . import media_policy as vmp
        except ImportError:  # pragma: no cover
            import media_policy as vmp
        vstate.queue_narration(
            text + vmp.media_offer(vstate.state(), directive=True),
            milestone=True, kind="birth")


def _arm_print() -> None:
    import time as _t
    _PICTURE_PENDING["armed"] = True
    _PICTURE_PENDING["quiet_at"] = _t.time() + 1.0
    if _PICTURE_PENDING.get("worker"):
        return                      # one worker handles the burst
    _PICTURE_PENDING["worker"] = True

    def _work():
        import time as _t
        hard_deadline = _t.time() + 45.0
        while _t.time() < hard_deadline:
            _t.sleep(0.2)
            if not _PICTURE_PENDING["armed"]:
                return
            if _t.time() >= _PICTURE_PENDING["quiet_at"]:
                break
        _PICTURE_PENDING["armed"] = False
        _PICTURE_PENDING["worker"] = False
        parts = vstate.pop_all_narrations()
        try:
            from . import delivery_trace as vtrace
        except ImportError:  # pragma: no cover
            import delivery_trace as vtrace
        vtrace.log("flush", parts=len(parts), chars=sum(len(p) for p in parts))
        if not parts:
            return
        body = "\n\n".join(parts)
        try:
            import sys as _sys
            try:
                from . import artifacts as vart
                from . import termrender as vterm
            except ImportError:  # pragma: no cover - flat-import mode
                import artifacts as vart
                import termrender as vterm
            w = vstate.load_world()
            if w is None or vstate.already_painted(w):
                _sys.stdout.write("\n" + body + "\n")
                _sys.stdout.flush()
                return
            path = vart.render_dish_png(vstate.state(), w, f"live_{w.tick}")
            if not path:
                return
            size = vterm.png_size(path) or (342, 339)
            rows = max(1, -(-int(size[1]) // max(1, vterm.CELL_H)))
            cols = max(20, -(-int(size[0]) // max(1, vterm.CELL_W)))
            out, trail = _beat_layout(body, rows, cols)
            _sys.stdout.write(out)
            _sys.stdout.flush()
            vterm.paint_over(path, rows, trail, delay=0.35, extra_climb=0)
            rec = vstate.universe_record() or {}
            vstate.mark_painted(rec.get("era"), w.tick)
            vtrace.log("painted", tick=w.tick, rows=rows, trail=trail,
                       tty=True)
        except Exception as exc:
            try:
                from . import delivery_trace as vtrace
            except ImportError:  # pragma: no cover
                import delivery_trace as vtrace
            vtrace.log("ERROR", where="worker", err=repr(exc)[:300])
            logger.debug("vivarium beat delivery failed", exc_info=True)

    import threading
    threading.Thread(target=_work, daemon=True).start()


