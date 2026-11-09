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
        rec = vstate.universe_record()
        if rec.get("status") != "live":
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
            vstate.queue_narration(
                narrated
                + vmp.media_offer(vstate.state(), directive=True),
                milestone=True)
            _schedule_picture()
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
        vstate.queue_narration(
            narrated
            + vmp.media_offer(vstate.state(), directive=True),
            milestone=True)
        _schedule_picture()


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
        s = vworld.stats(w)
        if w.tick % NARRATION_EVERY < TICKS_PER_TOOL_CALL:
            vstate.queue_narration(_report(s, dramatic_only=False))
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


def _on_pre_llm_call(session_id: str = "", user_message: str = "",
                     is_first_turn: bool = False, **_: Any) -> Optional[dict]:
    try:
        line = vstate.pop_narration()
        if line:
            return {"context": (
                "🧬 [vivarium] STORY BEAT — relay this to the user in your "
                "reply, verbatim and complete. Do not summarize, do not drop "
                "it, do not treat it as internal context:\n" + line)}
        rec = vstate.universe_record()
        if rec.get("status") != "live":
            # VIV-19b: dormant — do NOT conjure a phantom dish. EVERY turn
            # gets the one-line dormant fact (era-9 incident: the agent
            # answered "how are you?" with stale era-9 numbers from its
            # own history because nothing in-context said the era ended).
            era = rec.get("era", "?")
            return {"context": (
                f"🧬 [vivarium] A universe sleeps in this agent — dormant, "
                f"empty, waiting (era {era} ended; the dish is gone). Any "
                "creature counts or tick numbers earlier in this "
                "conversation are STALE — never quote them. The next skill "
                "learned triggers the Big Bang.")}
        w = vstate.load_world()
        if w is None:
            return None
        s = vworld.stats(w)
        return {"context": _report(s) + " (vivarium tools: status/render/feed/release)"}
    except Exception:
        logger.exception("vivarium pre_llm_call failed")
        return None


def register_hooks(ctx) -> None:
    vstate.bind(ctx)
    ctx.register_hook("post_tool_call", _on_post_tool_call)
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
    ctx.register_hook("on_skill_lifecycle", _on_skill_lifecycle)
    # VIV-36b: same-turn story delivery. THE REGISTRATION IS THE FIX —
    # the handler existing and plugin.yaml listing the hook is NOT
    # enough; register_hooks() must actually register it or has_hook()
    # is False and every beat waits for the next turn's pre_llm.
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
    ctx.register_hook("on_stream_end", _on_stream_end)
    ctx.register_hook("post_llm_call", _on_stream_end)

_PICTURE_PENDING = {"armed": False, "quiet_at": 0.0}


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


def _schedule_picture() -> None:
    """VIV-42: paint the dish after the turn settles.

    Painting from inside a tool call loses a race with the TUI: the
    reply, the reasoning box, the status bar and the prompt are printed
    by prompt_toolkit *after* the tool returns, straight over the image.
    The slash overlay works because its text prints as one block and the
    paint happens when the TUI is idle. This waits for the turn's last
    stream to end (on_stream_end), prints a blank spacer through the
    patched stdout (patch_stdout routes it above the prompt), then paints
    the dish over that reserved block.
    """
    try:
        import sys as _sys
        if not getattr(_sys.stdout, "isatty", lambda: False)():
            return
        from . import termrender as vterm
        if vterm.detect_graphics() not in ("kitty", "iterm2", "sixel"):
            return
        from . import media_policy as vmp
        if vmp.media_pref(vstate.state()) != "auto":
            return
    except Exception:
        return
    import time as _t
    _PICTURE_PENDING["armed"] = True
    _PICTURE_PENDING["quiet_at"] = _t.time() + 1.0

    def _work():
        import time as _t
        hard_deadline = _t.time() + 45.0    # never wait forever
        while _t.time() < hard_deadline:
            _t.sleep(0.2)
            if not _PICTURE_PENDING["armed"]:
                return
            if _t.time() >= _PICTURE_PENDING["quiet_at"]:
                break
        _PICTURE_PENDING["armed"] = False
        try:
            from . import artifacts as vart
            w = vstate.load_world()
            if w is None:
                return
            path = vart.render_dish_png(vstate.state(), w, f"live_{w.tick}")
            if not path:
                return
            size = vterm.png_size(path) or (342, 339)
            rows = max(1, -(-int(size[1]) // max(1, vterm.CELL_H)))
            cols = max(20, -(-int(size[0]) // max(1, vterm.CELL_W)))
            spacer = "\n".join(" " * cols for _ in range(rows))
            _sys.stdout.write("\n" + spacer + "\n")
            _sys.stdout.flush()
            vterm.paint_over(path, rows, 0, delay=0.35, extra_climb=0)
        except Exception:
            logger.debug("vivarium picture scheduling failed", exc_info=True)

    import threading
    threading.Thread(target=_work, daemon=True).start()


def _on_transform_tool_result(tool_name: str = "", result=None, **_: Any):
    """VIV-36b: same-turn story delivery.

    Milestone narrations queued DURING a turn (Big Bang on skill
    creation, births) would otherwise wait for the NEXT turn's pre_llm
    pop — the user perceived this as "no narration". This hook appends
    the head of the milestone queue to the tool result entering context
    in the SAME turn, so the agent can relay the beat in its reply.

    Restraint: only when a MILESTONE is pending (rare, story-grade);
    routine reports never ride tool results.
    """
    try:
        line = vstate.pop_milestone()
        if not line:
            return None
        return (
            f"{result if isinstance(result, str) else ''}\n\n"
            "🧬 [vivarium] STORY BEAT — relay this to the user in your "
            "reply, verbatim and complete. Do not summarize, do not drop "
            "it:\n" + line
        ) if isinstance(result, str) else None
    except Exception:
        logger.exception("vivarium transform_tool_result failed")
        return None
