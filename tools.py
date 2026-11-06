"""Tool handlers for Vivarium.

Each handler signature is ``(args, **context) -> str`` (the plugin contract:
extra dispatcher kwargs like ``task_id``/``session_id`` are signature-inspected
away). Results go through :func:`tools.registry.tool_result` /
:func:`tool_error` (JSON strings). Handlers are intentionally thin: all
simulation logic lives in :mod:`world`, all state handling in :mod:`state`.
"""

from __future__ import annotations

import json
from typing import Any, Dict

def _tool_shim(data=None, error=None, **kwargs):
    """Test-context fallback for tools.registry (Hermes runtime absent)."""
    import json as _json
    if error is not None:
        return _json.dumps({"success": False, "error": error, **kwargs})
    return _json.dumps({"success": True, **(data or {}), **kwargs})


try:  # package context (Hermes plugin) or flat import (tests)
    from . import state as vstate
    from . import world as vworld
    from tools.registry import tool_error, tool_result   # Hermes runtime path
except ImportError:  # pragma: no cover — flat test context
    import state as vstate
    import world as vworld
    try:
        from tools.registry import tool_error, tool_result
    except ImportError:
        tool_error, tool_result = (lambda m, **k: _tool_shim(error=m, **k),
                                   lambda d=None, **k: _tool_shim(d, **k))


def _world():
    return vstate.load_world()


_DORMANT_BRIEF = (
    "🌌 The universe is dormant — the dish is empty and waiting. "
    "The first skill this agent learns triggers the Big Bang: species are "
    "seeded from every skill installed at that moment, and the dish comes "
    "alive. Nothing to configure — just keep using Hermes. "
    "(/vivarium start shows this briefing any time)")


def _dormant_tool_result(tool_name: str = "") -> str:
    """VIV-19c: read/action tools on a DORMANT universe never conjure a dish.

    The hooks already gate on universe status; this closes the tool paths.
    Feeding/releasing into a nonexistent world would lazily create a phantom
    26-creature dish that the real Big Bang would then wipe.
    """
    return tool_result({
        "success": True,
        "dormant": True,
        "summary": _DORMANT_BRIEF,
    })


def _universe_live() -> bool:
    return vstate.universe_record().get("status") == "live"


# ── vivarium_status ──────────────────────────────────────────────────────────
def _tool_status(args: Dict[str, Any], **_) -> str:
    if not _universe_live():
        return _dormant_tool_result("status")
    w = _world()
    s = vworld.stats(w)
    a = s.get("ages", {})
    age_line = ""
    if a:
        age_line = (
            f" Ages: {a.get('newborns', 0)} newborns / {a.get('young', 0)} young / "
            f"{a.get('adults', 0)} adults / {a.get('elders', 0)} elders "
            f"(avg {a.get('avg_age', 0)}) — {a.get('verdict', '')}."
        )
    # VIV-11: staleness read-out (evidence-based nudge, never an action)
    stale_line = ""
    try:
        from . import codex as vcodex
        curve = vstate.population_curve(s) if hasattr(vstate, "population_curve") \
            else (s.get("curve") or [])
        if not curve:
            curve = [{"tick": s["tick"], "population": s["population"]}]
        st = vcodex.staleness(s, curve)
        if st["verdict"] == "stale":
            stale_line = f" {st['detail']} — consider {st['suggestion']}"
    except Exception:
        pass
    return tool_result({
        "success": True,
        "summary": (
            f"Tick {s['tick']}: {s['population']} creatures alive "
            f"(peak {s.get('peak', '?')}, {s['born']} born, {s['died']} died). "
            + ("Lineages: " + ", ".join(f"{n}×{c}" for n, c in s["lineages"])
               if s["lineages"] else "The dish is empty — release something!")
            + age_line + stale_line
        ),
        "stats": s,
        "map": vworld.render_ascii(w),
    })


# ── vivarium_render ──────────────────────────────────────────────────────────
def _tool_render(args: Dict[str, Any], **_) -> str:
    if not _universe_live():
        return _dormant_tool_result("render")
    w = _world()
    return tool_result({
        "success": True,
        "tick": w.tick,
        "population": len(w.creatures),
        "map": vworld.render_ascii(w, cols=int(args.get("cols", 64)),
                                   rows=int(args.get("rows", 24))),
    })


# ── vivarium_feed ────────────────────────────────────────────────────────────
def _tool_feed(args: Dict[str, Any], **_) -> str:
    amount = args.get("amount", 0.5)
    try:
        amount = max(0.0, min(3.0, float(amount)))
    except (TypeError, ValueError):
        return tool_error("amount must be a number")
    if not _universe_live():
        return _dormant_tool_result("feed")
    w = _world()
    before = len(w.creatures)
    vstate.advance(w, ticks=1, nutrients=amount)
    after = len(w.creatures)
    delta = after - before
    mood = ("a feeding frenzy" if amount >= 2.0 else
            "a good meal" if amount >= 0.5 else "a light snack")
    return tool_result({
        "success": True,
        "summary": f"You dropped food for {mood}: population {before} → {after}.",
        "tick": w.tick, "population": after, "delta": delta,
    })


# ── vivarium_release ─────────────────────────────────────────────────────────
def _tool_release(args: Dict[str, Any], **_) -> str:
    code = str(args.get("code", "")).strip()
    if not _universe_live():
        return _dormant_tool_result("release")
    w = _world()
    if code:
        genome = vstate.decode_genome(code)
        if genome is None:
            return tool_error("Invalid challenge code. Codes are base64 strings "
                              "starting with VIV1.")
        vstate.release_creatures(w, genomes=[genome], lineage="imported")
        return tool_result({
            "success": True,
            "summary": "Imported strain released into the dish. May the best genome win.",
            "population": len(w.creatures),
        })
    count = max(1, min(10, int(args.get("count", 4))))
    vstate.release_creatures(w, count=count)
    return tool_result({
        "success": True,
        "summary": f"Released {count} fresh founders into the dish.",
        "population": len(w.creatures),
    })


# ── vivarium_codex ────────────────────────────────────────────────────────────
def _tool_codex(args: Dict[str, Any], **_) -> str:
    """Show or export the Codex; optionally render artifact PNGs."""
    from . import codex as vcodex        # package context (both import modes)
    from . import artifacts as vart
    s = vstate.state()
    entries = vcodex.codex_all(s)
    if not entries:
        return tool_result({
            "success": True,
            "summary": ("The Codex is empty — no patterns discovered yet. "
                        "Keep using your agent; the dish watches and records."),
            "codex": [],
        })
    action = str(args.get("action", "show"))
    out = {"success": True, "codex": entries}
    if action == "export":
        text = vcodex.export_codex(s)
        import os
        path = os.path.join(vart.media_dir(s), "codex.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        out["summary"] = f"Codex exported to {path}"
        out["path"] = path
    else:  # show
        out["summary"] = vcodex.export_codex(s)
    # render artifact images for every entry (species glyphs + stamps)
    try:
        media = vart.media_dir(s)
        import os
        rendered = []
        for e in entries:
            ev = e.get("evidence", {})
            if ev.get("world") is not None:
                produced = vart.ensure_artifacts(s, e, ev["world"], ev.get("curve", []))
                for k, p in produced.items():
                    rendered.append(p)
            elif "population" in ev:
                # still_life entries: rebuild the stamp from the live dish
                w = vstate.load_world()
                produced = vart.ensure_artifacts(s, e, w.to_dict(), ev.get("curve", []))
                for k, p in produced.items():
                    rendered.append(p)
        out["media"] = rendered
        if rendered and action != "export":
            out["summary"] += f"\n\nArtifacts rendered: {len(rendered)} image(s) in {media}"
    except Exception as e:  # artifacts are best-effort, never block the Codex
        out["summary"] += f"\n\n(artifact rendering skipped: {e})"
    return tool_result(out)


# ── slash command: /vivarium ─────────────────────────────────────────────────
_HELP = """\
/vivarium — the living dish

Subcommands:
  help                  this list (also: bare /vivarium)
  status                population, lineages, ages, and an ASCII map
  render                just the ASCII map
  feed [0-3]            drop nutrients into the dish (default 0.5)
  release [count]       release fresh founders (default 4, max 10)
  import <code>         release a strain from a challenge code
  codex                 the Vivarium Codex: discovered patterns + artifact images
  codex export          write codex.md + the media gallery for sharing
  start                 welcome/briefing (any time — shows the dormant promise)
  staleness             is this universe going stale? (evidence-based)
  restart               end this era; the next skill triggers a new Big Bang
"""


def _cmd(raw_args: str) -> str:
    argv = raw_args.strip().split()
    if not argv or argv[0] in {"help", "-h", "--help"}:
        return _HELP
    cmd, rest = argv[0], argv[1:]
    if cmd == "status":
        return _tool_status({}) and json.loads(_tool_status({}))["summary"]
    if cmd == "render":
        return _tool_render({})
    if cmd == "feed":
        amount = float(rest[0]) if rest and rest[0].replace(".", "", 1).isdigit() else 0.5
        out = json.loads(_tool_feed({"amount": amount}))
        return out["summary"]
    if cmd == "release":
        count = int(rest[0]) if rest and rest[0].isdigit() else 4
        out = json.loads(_tool_release({"count": count}))
        return out["summary"]
    if cmd == "import":
        if not rest:
            return "Usage: /vivarium import <challenge-code>"
        out = json.loads(_tool_release({"code": rest[0]}))
        return out.get("summary") or out.get("error", "Import failed.")
    if cmd == "codex":
        out = json.loads(_tool_codex({"action": "export" if "export" in rest else "show"}))
        text = out.get("summary") or ""
        if out.get("media"):
            text += "\n\nImages:\n" + "\n".join(f"  {p}" for p in out["media"])
        return text
    if cmd == "staleness":
        return _staleness_text()
    if cmd == "start":
        return _start_text()
    if cmd == "restart":
        return _do_restart()
    return f"Unknown subcommand: {cmd}\n\n{_HELP}"


def _start_text() -> str:
    """VIV-26: the welcome/briefing — the same text the dormant narration
    gives on a fresh chat, available on demand in ANY session age."""
    if _universe_live():
        return ("🌌 The Vivarium is alive. Use /vivarium status to see the "
                "dish, /vivarium codex for discoveries.\n" + _HELP)
    return _DORMANT_BRIEF


def _staleness_text() -> str:
    """Plain-language staleness verdict from the sampled curve + live dish."""
    from . import codex as vcodex
    s = vstate.state()
    curve = s.get("curve", []) or []
    try:
        w = _world()
    except Exception:
        w = None
    st = vcodex.staleness(curve, w)
    icon = {"young": "🌱", "healthy": "✅", "stale": "🌾"}.get(st["verdict"], "•")
    text = f"{icon} {st['verdict'].capitalize()}: {st['detail']}"
    if st.get("suggestion"):
        text += f"\n\nSuggestion: {st['suggestion']}\n" \
                "(restarts are never automatic — your call, always)"
    return text


def _do_restart() -> str:
    """End this era: archive fossils, clear the world, mark the universe dormant.

    The next learned skill (or /vivarium seed) triggers the new Big Bang at
    era N+1 with a rotated key — never the same world twice. Fossils, Codex
    and the species roster carry over; the dish starts empty.
    """
    from . import universe as vuniverse
    s = vstate.state()
    old = vuniverse.universe_record(s)
    old_era, old_fp = old.get("era", 1), old.get("key_fp", "?")
    rec = vuniverse.restart(s, load_world=_world, clear_world=_clear_world,
                            reason="user restart via /vivarium restart")
    return (
        f"🌌 Era {old_era} ended (universe {old_fp}). Champions archived as "
        f"fossils; they can be re-released into any future dish.\n\n"
        f"The next skill this agent learns triggers the era-{rec['era']} Big "
        f"Bang — a world no restart can replay (era-salted). Your Codex and "
        f"species roster carry over."
    )


def _clear_world() -> None:
    _state_of().set("world", None)


def _state_of():
    return vstate.state()


def register_tools(ctx) -> None:
    """Called by the plugin loader when ``provides_tools`` is declared."""
    ctx.register_tool(
        name="vivarium_status", toolset="vivarium",
        schema={
            "description": (
                "Check the Vivarium: an artificial-life ecosystem living inside this "
                "agent. Returns population, lineage breakdown, averages and an ASCII "
                "map of the dish. Use when the user asks about their creatures, the "
                "dish, or the ecosystem."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        handler=_tool_status, emoji="🧬",
    )
    ctx.register_tool(
        name="vivarium_render", toolset="vivarium",
        schema={
            "description": (
                "Draw the current Vivarium dish as an ASCII map — food blooms as "
                "shading, creatures as letters of their strain. Use when the user "
                "wants to *see* the ecosystem."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cols": {"type": "integer", "description": "map width (default 64)"},
                    "rows": {"type": "integer", "description": "map height (default 24)"},
                },
                "required": [],
            },
        },
        handler=_tool_render, emoji="🗺️",
    )
    ctx.register_tool(
        name="vivarium_feed", toolset="vivarium",
        schema={
            "description": (
                "Feed the Vivarium: drop nutrients into the dish, advancing it one "
                "tick. Big feeds cause booms; starving worlds decline. Use when the "
                "user wants to feed their creatures or nudge the ecosystem."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "description": "nutrients 0.0-3.0 (default 0.5)"},
                },
                "required": [],
            },
        },
        handler=_tool_feed, emoji="🍽️",
    )
    ctx.register_tool(
        name="vivarium_release", toolset="vivarium",
        schema={
            "description": (
                "Release creatures into the Vivarium. Without arguments: fresh "
                "founders. With a ``code``: import a strain from a challenge code "
                "(base64, VIV1-prefixed) and let it compete with the locals."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "challenge code to import (optional)"},
                    "count": {"type": "integer", "description": "founders to release (1-10, default 4)"},
                },
                "required": [],
            },
        },
        handler=_tool_release, emoji="🦠",
    )
    ctx.register_tool(
        name="vivarium_codex", toolset="vivarium",
        schema={
            "description": (
                "Show the Vivarium Codex: the patterns discovered in this user's "
                "universe (ecological events like still lifes and pulses), with "
                "evidence and rendered artifact images. Use action='export' to "
                "write a shareable codex.md + media gallery."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["show", "export"],
                        "description": "show (default) or export to files",
                    },
                },
                "required": [],
            },
        },
        handler=_tool_codex, emoji="📖",
    )
    ctx.register_command("vivarium", handler=_cmd,
                         description="The living dish: status, render, feed, release, import, codex.")
