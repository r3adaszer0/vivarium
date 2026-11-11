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
            vtrace.log("no_content", skill=skill_name)
            return
        result = vbirth.birth_species(
            vstate.state(), skill_name, content,
            save_world=vstate.save_world,
            load_world=vstate.load_world,
        )
        vtrace.log("birth_result", ok=bool(result))
        if not result:
            # Same content, same species (VIV-46). Saying nothing here reads
            # as a broken plugin, so say the true thing in one line. No dish:
            # nothing was born.
            known = vbirth.find_existing(vstate.state(), content)
            vtrace.log("duplicate_lookup", hit=bool(known))
            if known:
                eidos = known.get("eidos") or "?"
                day = known.get("day") or "an earlier day"
                _deliver_beat(
                    f"Already in the dish: {eidos}, born {day} from this "
                    f"same skill. No new species.")
            return
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
        _TURN_OPEN["open"] = True        # VIV-79: cards must not paint mid-turn
        try:
            import time as _t
            # VIV-81: bracket the turn in SHARED state — the TUI's poller
            # runs in another process and must see this turn too.
            vstate.state().set("agent_turn_open", True)
            vstate.state().set("agent_turn_open_at", _t.time())
        except Exception:
            pass
        if vstate.peek_milestone() is not None:
            line = vstate.pop_milestone() or ""
            tail = ""
            try:
                from . import media_policy as vmp
            except ImportError:  # pragma: no cover
                import media_policy as vmp
            if vmp.media_pref(vstate.state()) == "auto":
                tail = ("\n\n(Vivarium layout: AFTER you have answered the "
                        "user, append this card at the very end of your "
                        "reply, never before your own words, then call "
                        "the vivarium_render tool with image=true in this "
                        "same turn so the dish image is attached.)")
            # VIV-79b: the relay gets CLEAN text (no SGR, no <<ART>> block
            # — a chat surface cannot use either); the poller keeps the
            # raw card and paints the face itself.
            try:
                from . import acts as vacts
            except ImportError:  # pragma: no cover
                import acts as vacts
            clean = vacts.strip_art(_strip_sgr(line))
            return {"context": (
                "🧬 [vivarium] STORY BEAT — relay this card to the user at "
                "the END of your reply (after your own words), verbatim and "
                "complete. Do not summarize, do not drop it, do not treat it "
                "as internal context:\n" + clean + tail)}
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
    # VIV-49: post_llm_call fires ONCE PER TURN, after the tool loop
    # (agent/turn_finalizer._apply_output_hooks). on_stream_end fires per
    # assistant message — arming on it printed the beat between the
    # skill call and the reply.
    ctx.register_hook("post_llm_call", _on_stream_end)

_PICTURE_PENDING = {"armed": False, "quiet_at": 0.0, "worker": False}


def _on_stream_end(**_):
    """VIV-49: end-of-TURN signal (post_llm_call) for the quiet clock.

    The picture must be painted when the TURN is over, not when the skill
    hook fires — the model still has reasoning and a reply to print. Each
    stream end pushes the quiet deadline forward; the worker paints once
    the stream has been quiet for a moment (or after a hard cap, so a
    missing hook never leaves the dish unpainted).
    """
    import time as _t
    _TURN_OPEN["open"] = False   # VIV-79: the turn closed; cards may paint
    try:
        vstate.state().set("agent_turn_open", False)   # VIV-81: clear the shared gate
    except Exception:
        pass
    _capture_pt_app()
    if _PICTURE_PENDING.get("armed"):
        # a little slack: the TUI is still painting the final message
        _PICTURE_PENDING["quiet_at"] = _t.time() + 1.2
        try:
            try:
                from . import delivery_trace as vtrace
            except ImportError:  # pragma: no cover
                import delivery_trace as vtrace
            vtrace.log("turn_end", at=_t.time())
        except Exception:
            pass


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


_PAINT_RELAY: dict = {"started": False}
_TURN_OPEN: dict = {"open": False}   # VIV-79: a turn is streaming; cards wait
_TURN_STALE_S = 300.0                # VIV-81: a crashed turn must not wedge cards


def _card_claim_allowed(vst) -> bool:
    """VIV-81: the card gate is CROSS-PROCESS now.

    The skill turn runs in the gateway; the TUI's poller lives in another
    process whose own _TURN_OPEN is always False — so the TUI claimed and
    painted cards while the gateway's reply was still streaming (the
    exact "vivarium fires before Hermes finishes" the user kept hitting).
    pre_llm_call/post_llm_call now bracket the turn in SHARED state
    (agent_turn_open), and every process's poller consults it. A stale
    open flag (a crashed turn that never closed) yields after the cap so
    a wedge can never strand the queue forever.
    """
    if _TURN_OPEN.get("open"):
        return False
    try:
        st = vst.state()
        if st.get("agent_turn_open"):
            import time as _t
            opened_at = float(st.get("agent_turn_open_at") or 0.0)
            if _t.time() - opened_at < _TURN_STALE_S:
                return False
    except Exception:
        pass
    return True


def _ensure_paint_relay() -> None:
    """VIV-77b: slash commands can execute in a fully headless process
    (gateway-side session: no TERM, no tty anywhere in the ancestry — the
    doctor trace proved it). No env fix can make that process paint; the
    dish must be painted by whichever process sits on the terminal. This
    poller (one per process, started at import) claims paint requests
    dropped in state and overlays the current dish. Headless processes
    fail _can_paint() and just idle; requests expire if no surface shows
    up, so a closed TUI degrades to the whitespace fallback, never to a
    stranded queue."""
    if _PAINT_RELAY["started"]:
        return
    _PAINT_RELAY["started"] = True

    def _poll():
        import time as _t
        while True:
            _t.sleep(1.0)
            try:
                if not _can_paint():
                    continue
                try:
                    from . import state as vst
                except ImportError:  # pragma: no cover
                    import state as vst
                # Paint requests claim IMMEDIATELY (the reserved rows sit
                # in a reply that is already on screen; waiting for the
                # turn to close would let the 12s expiry eat them). Only
                # CARD beats wait for the turn gap.
                req = vst.pop_paint_request()
                if req is not None:
                    # VIV-80: a show request carries its own glyph path and
                    # the reserved geometry; a status request re-renders the
                    # current dish. One claim point, two payloads.
                    if req.get("kind") == "show" and req.get("path"):
                        _paint_show_relay(req)
                    else:
                        _paint_status_relay()
                # VIV-79: claim a CARD beat too. A headless drain queued it
                # for agent relay; a terminal-owning process can deliver it
                # BETTER: card+image as one payload between turns, no
                # one-turn delay, nothing lost. Never mid-turn: the agent's
                # reply is still streaming; the beat waits for the gap.
                # VIV-81: "mid-turn" is now judged cross-process.
                if not _card_claim_allowed(vst):
                    continue
                line = vst.pop_milestone()
                if line:
                    try:
                        from . import delivery_trace as vtrace
                    except ImportError:  # pragma: no cover
                        import delivery_trace as vtrace
                    vtrace.log("card_claim", chars=len(line))
                    _emit_card(line)
            except Exception:
                continue

    import threading as _threading
    _threading.Thread(target=_poll, daemon=True,
                      name="vivarium-paint-relay").start()


def _paint_show_relay(req: dict) -> None:
    """VIV-80: overlay the glyph a headless /vivarium show reserved.

    The request carries the exact PNG path and the geometry the worker
    computed (rows reserved, lines printed after the block) — the relay
    paints THAT file over THOSE rows; it never re-renders, so the face
    the user asked for is the face that arrives.
    """
    try:
        try:
            from . import termrender as vterm
        except ImportError:  # pragma: no cover
            import termrender as vterm
        import os as _os
        path = str(req.get("path") or "")
        if not path or not _os.path.exists(path):
            return
        rows = int(req.get("res_rows") or 1)
        trail = int(req.get("trail") or 0)
        vterm.paint_over(path, rows, trail, delay=0.0)
    except Exception:
        pass


def _paint_status_relay() -> None:
    """Overlay the CURRENT dish for a request a headless slash worker
    dropped. The worker already reserved the rows in its returned text;
    by the time this fires (>=1 poll tick after the reply rendered) the
    rectangle sits in the TUI's scrollback — land the picture on it."""
    try:
        try:
            from . import artifacts as vart
            from . import termrender as vterm
        except ImportError:  # pragma: no cover - flat-import mode
            import artifacts as vart
            import termrender as vterm
        import math as _math
        w = vstate.load_world()
        if w is None:
            return
        path = vart.render_dish_png(
            vstate.state(), w, f"status_{w.tick}")
        if not path:
            return
        size = vterm.png_size(path) or (342, 339)
        res_rows = max(1, _math.ceil(size[1] / vterm.CELL_H))
        vterm.paint_over(path, res_rows, 0, delay=0.0)
    except Exception:
        pass



_PT_APP = None


def _capture_pt_app() -> None:
    """Remember the prompt_toolkit app while we are on its thread.

    get_app() is thread-local: called from the printer's daemon thread it
    returns nothing, which is why the beat fell back to a raw write and
    landed under the input prompt. Capture it during post_llm_call, which
    runs on the app's own thread.
    """
    global _PT_APP
    try:
        from prompt_toolkit.application import get_app
        app = get_app()
        if app is not None and getattr(app, "is_running", False):
            _PT_APP = app
    except Exception:
        pass


def _emit_via_terminal(write_fn) -> bool:
    """Print through prompt_toolkit's run_in_terminal when the TUI owns the screen.

    Raw writes from a daemon thread land in the middle of the prompt and
    get erased by the next repaint: that is why the beat "printed" yet was
    never visible. run_in_terminal is the TUI's own mechanism for output
    from outside a turn (see hermes_cli/cli_modal_mixin.py): it clears the
    prompt, prints, and redraws. It must be scheduled on the app loop.
    """
    try:
        from prompt_toolkit.application import get_app, run_in_terminal
    except Exception:
        return False
    app = _PT_APP
    if app is None or not getattr(app, "is_running", False):
        try:
            app = get_app()
        except Exception:
            return False
    if app is None or not getattr(app, "is_running", False):
        return False
    try:
        import functools
        app.loop.call_soon_threadsafe(
            functools.partial(run_in_terminal, write_fn))
        return True
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


def _strip_sgr(text: str) -> str:
    """VIV-79: chat surfaces relay text, not terminal colour codes.

    The card's SGR sequences render fine on a tty and arrive as literal
    garbage everywhere else (the user's Matrix paste showed raw
    ESC[38;2;...m runs). The relay path strips them; the terminal paint
    keeps the colour.
    """
    import re as _re
    return _re.sub(r"\x1b\[[0-9;]*m", "", text or "")


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
        # Chat / gateway: the beat stays queued for the agent to relay.
        # VIV-79b: the text queues RAW — the <<ART>> face block and the
        # SGR colours are part of the card and must survive to a
        # terminal-claiming poller. Stripping happens at the consumers:
        # the agent relay strips in the pre_llm wrapper, the poller
        # paints the block as-is.
        vstate.queue_narration(text, milestone=True, kind="birth")


def _arm_print() -> None:
    """Start the worker, but do NOT start the clock.

    arming here used to set quiet_at = now + 1s, so any turn where the
    model took longer than a second to compose its reply printed the beat
    mid-turn (observed live: beat on screen while the TUI still showed
    "reflecting..."). The clock starts only when the turn actually ends
    (post_llm_call -> _on_stream_end). The cap is a safety net for turns
    that never emit that hook.
    """
    import time as _t
    _PICTURE_PENDING["armed"] = True
    _PICTURE_PENDING["quiet_at"] = None
    _PICTURE_PENDING["cap_at"] = _t.time() + 120.0
    if _PICTURE_PENDING.get("worker"):
        return                      # one worker handles the burst
    _PICTURE_PENDING["worker"] = True

    def _work():
        import time as _t
        while True:
            _t.sleep(0.15)
            if not _PICTURE_PENDING["armed"]:
                return
            quiet_at = _PICTURE_PENDING.get("quiet_at")
            if quiet_at is not None and _t.time() >= quiet_at:
                break
            if _t.time() >= _PICTURE_PENDING.get("cap_at", 0):
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
        _emit_card(body)

    import threading
    threading.Thread(target=_work, daemon=True).start()


def _emit_card(body: str) -> None:
    """Render a card body and deliver text+picture as ONE payload.

    Shared by the quiet worker (post-turn flush) and the paint relay
    (VIV-79: a headless drain's card claimed by the terminal-owning
    process). One code path so the card can never diverge between them.
    """
    vtrace = None
    try:
        import sys as _sys
        try:
            from . import artifacts as vart
            from . import termrender as vterm
        except ImportError:  # pragma: no cover - flat-import mode
            import artifacts as vart
            import termrender as vterm
        try:
            from . import card as vcard
            from . import acts as vacts
        except ImportError:  # pragma: no cover - flat-import mode
            import card as vcard
            import acts as vacts
        try:
            from . import delivery_trace as vtrace
        except ImportError:  # pragma: no cover
            import delivery_trace as vtrace
        import shutil as _shutil
        # The width has to come from the app we captured, not from
        # shutil: inside this worker thread shutil reports whatever
        # the fd says, and one live run read a narrow value, fell back
        # to the stacked card, and dropped the dish. The app knows.
        term_cols = 0
        try:
            _app = _PICTURE_PENDING.get("app")
            if _app is not None:
                term_cols = int(_app.output.get_size().columns)
        except Exception:
            term_cols = 0
        if term_cols < 40:
            term_cols = _shutil.get_terminal_size((100, 40)).columns
        w = vstate.load_world()
        live = None
        if w is not None:
            try:
                st = vworld.stats(w)
                live = {"tick": w.tick,
                        "alive": st.get("population", 0),
                        "lineages": len(st.get("lineages") or []),
                        "lineages_total": st.get("lineages_total", 0),
                        "coloured": st.get("coloured", 0),
                        "grey": st.get("grey", 0)}
            except Exception:
                live = {"tick": w.tick}
        path = ""
        rows = 23
        dish_cols = 24
        # No "already painted" guard here. It existed when the agent
        # could also call vivarium_render for the same beat; the agent
        # no longer paints, and the guard is stateful across runs — a
        # restart that lands on the same (era, tick) then silently
        # drops the picture, which is exactly how the dish vanished
        # twice. The beat always paints.
        if w is not None:
            # An arrival beat carries the newborn's eidos; ring its pod
            # and plate it with the name. VIV-80 correction: the user
            # wants the RING AND THE NAME ON THE IMAGE — only the
            # "white ring = the pod" legend LINE was the duplication
            # (the picture shows the ring; a sentence explaining it
            # repeated what the eye already sees). The legend stays
            # gone; the ring stays.
            mark = None
            callout = None
            import re as _re
            _m = _re.search(r"<<ART:([^>]*)>>", body)
            if _m:
                _eidos = _m.group(1)
                for _c in getattr(w, "creatures", []) or []:
                    if getattr(_c, "lineage", "") == _eidos:
                        mark = (_c.x, _c.y)
                        break
                if mark is not None:
                    callout = (mark[0], mark[1], _eidos)
            path = vart.render_dish_png(vstate.state(), w, f"live_{w.tick}",
                                        mark=mark, callout=callout) or ""
            if path:
                size = vterm.png_size(path) or (342, 339)
                rows = max(1, -(-int(size[1]) // max(1, vterm.CELL_H)))
                # Reserve generously: the dish is ~339px wide and a
                # narrow font cell is as little as 9px, so assume 9
                # and add one column of gutter. Wasting two columns
                # is invisible; overlapping the text is not.
                dish_cols = max(12, -(-int(size[0]) // 9) + 1)
        _rec = vstate.universe_record() or {}
        rendered = vcard.render(body, term_cols, vacts.DISH_MARKER,
                                live=live, dish_rows=rows,
                                dish=bool(path), dish_cols=dish_cols,
                                legend=None,
                                era=_rec.get("era"))
        out = rendered["text"]

        def _write(_out=out, _path=path, _climb=rendered["climb"]):
            # One write for text and picture. prompt_toolkit's stdout
            # proxy eats ESC, so the card goes to /dev/tty; and because
            # the renderer never learns these rows exist, the picture
            # must ride in the same bytes — a later deferred paint is
            # measured against a cursor it no longer controls.
            payload = _out.encode("utf-8")
            if _path and _climb:
                payload += vterm.overlay_bytes(_path, _climb)
            wrote = False
            try:
                import os as _os
                fd = _os.open("/dev/tty", _os.O_WRONLY)
                try:
                    _os.write(fd, payload)
                    wrote = True
                finally:
                    _os.close(fd)
            except OSError:
                wrote = False
            if not wrote:
                buf = getattr(_sys.stdout, "buffer", None)
                if buf is not None:
                    buf.write(payload)
                    buf.flush()
                else:
                    _sys.stdout.write(payload.decode("utf-8", "replace"))
                    _sys.stdout.flush()

        via_pt = _emit_via_terminal(_write)
        if not via_pt:
            _write()
        vtrace.log("emit", via="run_in_terminal" if via_pt else "raw_stdout",
                   chars=len(out), dish=bool(path))
        # Only claim a paint when the bytes actually carried the image.
        # climb == 0 means the card had no reserved rows for it, so
        # nothing was painted; logging "painted" there sent me looking
        # for an overlap bug that did not exist.
        if path and rendered["climb"]:
            rec = vstate.universe_record() or {}
            vstate.mark_painted(rec.get("era"), w.tick if w else 0)
            vtrace.log("painted", tick=w.tick if w else 0, rows=rows,
                       climb=rendered["climb"], tty=True)
    except Exception as exc:
        if vtrace is not None:
            vtrace.log("ERROR", where="card_emit", err=repr(exc)[:300])
        logger.debug("vivarium card delivery failed", exc_info=True)


# VIV-77b: the paint relay starts in EVERY process at import — the TUI
# process must be listening before its first slash command ever runs.
_ensure_paint_relay()


