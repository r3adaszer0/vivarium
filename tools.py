"""Tool handlers for Vivarium.

Each handler signature is ``(args, **context) -> str`` (the plugin contract:
extra dispatcher kwargs like ``task_id``/``session_id`` are signature-inspected
away). Results go through :func:`tools.registry.tool_result` /
:func:`tool_error` (JSON strings). Handlers are intentionally thin: all
simulation logic lives in :mod:`world`, all state handling in :mod:`state`.
"""

from __future__ import annotations

import json
import math
import os
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


# ── media preference (VIV-27; shared policy in media_policy.py) ─────────────
MEDIA_PREF_KEY = "media_pref"          # "auto" | "image" | "ascii"
_MEDIA_MODES = ("auto", "image", "ascii")


def media_pref() -> str:
    try:
        from . import media_policy as vmp
    except ImportError:  # pragma: no cover
        import media_policy as vmp
    return vmp.media_pref(vstate.state())


def set_media_pref(mode: str) -> str:
    if mode not in _MEDIA_MODES:
        return f"Unknown mode '{mode}'. Use: on (image), off (ascii), auto."
    vstate.state().set(MEDIA_PREF_KEY, mode)
    return {
        "auto": "Media: auto — images where supported, ASCII elsewhere.",
        "image": "Media: image — prefer real renders (kitty graphics, "
                 "attachments); falls back to ASCII elsewhere.",
        "ascii": "Media: ascii — text-only dish; images on demand via "
                 "/vivarium render --image.",
    }[mode]


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
    rich = bool(args.get("rich"))
    # ANSI colors only when the output can actually show them: a tty.
    # In gateway/chat contexts the codes would surface as mojibake (the
    # same lesson as the kitty-escape leak).
    import sys as _sys
    want_color = bool(args.get("color")) and _sys.stdout.isatty()
    fn = vworld.render_ascii_rich if rich else vworld.render_ascii
    cols = int(args.get("cols", 96 if rich else 64))
    rows = int(args.get("rows", 32 if rich else 24))
    out = {
        "success": True,
        "tick": w.tick,
        "population": len(w.creatures),
        "map": (fn(w, cols=cols, rows=rows, color=True) if (rich and want_color)
                else fn(w, cols=cols, rows=rows)),
        "legend": ("█ = creatures · ░▒▓ = food blooms (lush→faint)"
                   if rich else
                   "X = creatures, dots/: = food blooms"),
    }
    # honor the media preference: "ascii" means images ONLY on explicit
    # request (this call IS explicit when image=true, so it still renders);
    # the pref gates AUTOMATIC delivery elsewhere (narration, hooks)
    if args.get("image") or (media_pref() == "image"):
        # VIV-28b: render the true PNG and emit via the best graphics
        # protocol the terminal supports (opt-in only — the CALLER set
        # image=true deliberately). Non-supporting terminals get the path.
        try:
            from . import artifacts as vart
        except ImportError:  # pragma: no cover
            import artifacts as vart
        media = vart.media_dir(vstate.state())
        path = vart.render_dish_png(vstate.state(), w, f"dish_{w.tick}")
        if path:
            out["media"] = [path]
            # No graphics emission here: tool results travel the message
            # pipeline (attach-only); the SLASH paints via /dev/tty.
            out["graphics"] = f"attached {path}"
    return tool_result(out)


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


# ── vivarium_export ───────────────────────────────────────────────────────────
def _tool_export(args: Dict[str, Any], **_) -> str:
    name = str(args.get("name", "")).strip()
    return tool_result({
        "success": True,
        "summary": _export_text([name] if name else []),
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
_EXPLAIN_TEXT = """How your skills become living creatures

Every skill your agent learns is written down as text. Vivarium takes
that text and computes its SHA-256 hash: a fixed fingerprint that is
the same for the same text and completely different for any other.

That fingerprint becomes the creature's genome: six numbers (forage,
aggression, metabolism, sense, mutation rate, hue) read out of the
hash bytes. Change one word of the skill and the fingerprint changes
completely, so every skill makes a species nobody has ever seen.

Three properties make this the heart of Vivarium:

1. Deterministic. The same skill always produces the same species —
   in your dish, in a friend's dish, a hundred years from now. No
   random number generator anywhere; the creature's body is a pure
   function of the words you taught your agent. This is why a race
   between two species can be re-run bit-for-bit anywhere.

2. One-way. The genome is a hash of your skill's text: from the
   creature you cannot read the skill, and Vivarium never stores the
   text either — only the species ID (a short prefix of the hash).
   Your skills stay yours; what leaves your machine for a race is the
   six genome numbers, nothing else.

3. Bounded. Six numbers sit inside fixed ranges (a gene cannot be
   infinite). Children inherit their parent's numbers with small
   hash-driven drift, so lineages evolve — but no skill can conjure
   an unbeatable god-creature; the physics stays fair.

Why a hash and not, say, the skill's name? Names are chosen, hashes
are earned: a name is a label anyone can pick, while the hash binds
the creature to the exact bytes of what your agent actually learned.
The species is literally your skill's fingerprint, walking around
eating food in a dish.

See it yourself: /vivarium show <Eidos ID> prints a species card; its
Eidos_ ID is the first bytes of its skill's hash."""


_HELP = """\
/vivarium — the living dish

Subcommands:
  help                  this list (also: bare /vivarium)
  status                population, lineages, ages, and an ASCII map
  show [name|id]        meet one species up close: face, genes, story (--image: glyph)
  clip [species] [ticks] [--zoom]   film the dish as a short MP4 (into the gallery)
  explain               how your skills become living creatures (the hash story)
  narration on|off      the walkthrough story (off = bare birth lines only)
  render [--rich] [--color] [--image]   the dish map (--rich: dense blocks; --color: colored creatures, terminal only; --image: true PNG when supported)
  serve [--keep]        open the gallery in your browser (localhost only)
  images on|off|auto    how imagery is delivered (auto = where supported)
  feed [0-3]            drop nutrients into the dish (default 0.5)
  release [count]       release fresh founders (default 4, max 10)
  import <code>         release a strain from a challenge code
  codex                 the Vivarium Codex: discovered patterns + artifact images
  codex export          write codex.md + the media gallery for sharing
  export [name]         your species as VIV1 challenge codes (shareable)
  race <code> | <seed> [codes]   run a scenario duel (shareable, deterministic)
  start                 welcome/briefing + the universe view (graphics when possible)
  staleness             is this universe going stale? (evidence-based)
  restart               end this era (farewell picture of the old dish); next skill births a new one
"""


def _render_text(out: dict) -> str:
    """Human text for the render slash output. Slash-UX law: render the
    map; show the media path once (never duplicate via a graphics note)."""
    text = f"Tick {out.get('tick')} — {out.get('population')} creatures\n\n" \
           + out.get("map", "") + "\n\n" + out.get("legend", "")
    if not out.get("map"):
        # image painted inline: skip the map/legend block entirely
        text = f"Tick {out.get('tick')} — {out.get('population')} creatures"
    for m in out.get("media", []) or []:
        text += f"\n\n🖼️ {m}"
    g = out.get("graphics") or ""
    if g and not g.startswith("saved to") \
            and not g.startswith("attached"):  # path already shown via 🖼️
        text += f"\n({g})"
    return text


def _cmd(raw_args: str) -> str:
    argv = raw_args.strip().split()
    if not argv or argv[0] in {"help", "-h", "--help"}:
        return _HELP
    cmd, rest = argv[0], argv[1:]
    if cmd == "status":
        out = json.loads(_tool_status({}))
        text = out.get("summary", "")
        if out.get("map"):
            text += "\n\nThe dish:\n" + out["map"] + \
                "\n\n(X = creatures, dots/: = food blooms)"
        return text
    if cmd == "render":
        want_image = "image" in rest or "--image" in rest
        out = json.loads(_tool_render({
            "rich": "rich" in rest or "--rich" in rest,
            "image": want_image,
            "color": ("color" in rest or "--color" in rest
                      or "colour" in rest or "--colour" in rest)}))
        if want_image and out.get("media") and media_pref() != "off":
            try:
                from . import termrender as vterm
            except ImportError:  # pragma: no cover
                import termrender as vterm
            # CLEVER OVERLAY: the returned text reserves blank rows where
            # the image will sit; the TUI's own redraw engine owns and
            # scrolls those rows (it printed them), so nothing gets
            # clipped. A deferred paint drops the PNG on top of the
            # reserved rectangle; if painting fails, the ASCII map is
            # written into the same rows instead — the ASCII is both the
            # placeholder AND the fallback.
            path = out["media"][0]
            size = vterm.png_size(path) or (342, 339)
            res_rows = max(1, math.ceil(size[1] / vterm.CELL_H))
            res_cols = max(20, math.ceil(size[0] / vterm.CELL_W))
            out["map"] = ""      # the overlay replaces the inline ASCII
            out["legend"] = ""
            text = _render_text(out)
            summary, _, tail = text.partition("\n\n")
            spacer = "\n".join(" " * res_cols for _ in range(res_rows))
            # trail = path + graphics note lines (after the reserved rows)
            trail = tail.lstrip("\n") if tail else ""
            trail_rows = trail.count("\n") + 1 if trail else 0
            out["graphics"] = vterm.paint_over(
                path, res_rows, trail_rows, delay=0.6)
            return (summary + "\n\n" + spacer + "\n" + trail).rstrip() + "\n"
        return _render_text(out)
    if cmd == "serve":
        return _serve_text("keep" in rest or "--keep" in rest)
    if cmd == "images":
        if not rest:
            return f"Media delivery: {media_pref()}.\n" \
                   "Set with: /vivarium images on|off|auto"
        return set_media_pref({"on": "image", "off": "ascii"}.get(rest[0], rest[0]))
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
    if cmd == "export":
        return _export_text(rest)
    if cmd == "race":
        return _race_text(rest)
    if cmd == "show":
        return _show_text(rest)
    if cmd == "clip":
        return _clip_text(rest)
    if cmd == "explain":
        return _EXPLAIN_TEXT
    if cmd == "narration":
        return _narration_text(rest)
    if cmd == "staleness":
        return _staleness_text()
    if cmd == "start":
        return _start_text()
    if cmd == "restart":
        return _do_restart()
    return f"Unknown subcommand: {cmd}\n\n{_HELP}"


def _serve_text(keep: bool) -> str:
    """VIV-28b: localhost-only gallery over the plugin's media dir."""
    try:  # package mode / flat mode
        from . import termrender as vterm
    except ImportError:  # pragma: no cover
        import termrender as vterm
    try:
        from . import artifacts as vart
    except ImportError:  # pragma: no cover
        import artifacts as vart
    try:
        media = vart.media_dir(vstate.state())
    except Exception:
        media = None
    if not media or not os.path.isdir(media):
        return ("No gallery yet — artifacts appear after Codex discoveries. "
                "Use /vivarium codex first.")
    try:
        w = _world()
        dish = vworld.render_ascii(w)
    except Exception:
        dish = ""
    res = vterm.serve_gallery(media, dish_map=dish, keep=keep,
                              open_browser=True)
    if "error" in res:
        return res["error"]
    lifetime = "stays up until Hermes exits (--keep)" if keep \
        else "dies with this session; use /vivarium serve --keep to persist"
    return (f"🖼️ Gallery: {res['url']}  ({lifetime})\n"
            f"Localhost only — nothing leaves this machine.")


def _race_text(rest: list) -> str:
    """VIV-21: run a scenario duel. /vivarium race <code> or
    /vivarium race <seed> [challenge-code ...] (new scenario from seed)."""
    try:  # package mode (Hermes) / flat mode (tests)
        from . import scenario as vscen
    except ImportError:  # pragma: no cover
        import scenario as vscen
    if not rest:
        return ("Usage:\n"
                "  /vivarium race <scenario-code>\n"
                "  /vivarium race <seed> [challenge-code ...]  — new duel "
                "from a seed word; optional contestant strains\n"
                "Contestant codes come from /vivarium codex exports or other "
                "agents' challenge codes.")
    if rest[0].startswith("SCEN1"):
        spec = vscen.decode_scenario(rest[0])
        if spec is None:
            return "Invalid scenario code (must be SCEN1…)."
    else:
        seed = rest[0]
        spec = vscen.decode_scenario(vscen.encode_scenario(seed, vscen.SCENARIO_TICKS, rest[1:]))
    # scenarios are self-contained experiments — they run even while the
    # profile universe is dormant; no plugin state is touched, no universe
    # key is read (Rule 4, and safe for fresh installs)
    res = vscen.run_scenario(spec)
    share = vscen.encode_scenario(spec["seed"], spec["ticks"],
                                  spec.get("contestants", []))
    return (vscen.format_results(res)
            + f"\n\nShare this exact race (same dish, same results "
              f"everywhere):\n{share}")




# ── VIV-13: challenge-code export ────────────────────────────────────────────
def _export_text(rest: list) -> str:
    """Export your species as VIV1 challenge codes (race entrants).

    /vivarium export          — all species with their codes
    /vivarium export <name>   — one species: code + species card
    A code IS the genome (6 trait numbers) — safe to share; no skill
    content, no key material. The genome is stored at birth (VIV-13);
    species born before this version can be back-filled by re-deriving
    from the still-installed skill.
    """
    s = vstate.state()
    births = s.get("births", {})
    if isinstance(births, list):      # manual-era shape — no genomes there
        births = {}
    if not births:
        return ("No species have been born yet. Species appear when the "
                "Big Bang seeds them (first skill learned) or when a new "
                "skill is learned in a live universe.")
    if rest:
        name = rest[0]
        rec = births.get(name)
        if rec is None:
            matches = [n for n in births if name.lower() in n.lower()]
            if len(matches) == 1:
                rec, name = births[matches[0]], matches[0]
            elif matches:
                return ("Ambiguous name — matches: " + ", ".join(sorted(matches)))
            else:
                return (f"Unknown species '{name}'. "
                        f"/vivarium export lists every species.")
        g = rec.get("genome")
        if not g:
            return (f"{rec.get('eidos', name)} was born before challenge-code "
                    f"storage — its genome can no longer be re-derived "
                    f"(the skill was removed). It lives on in the dish.")
        code = vstate.encode_genome(g)
        return (f"{rec.get('eidos', name)} — challenge code:\n{code}\n\n"
                f"Enter a race: /vivarium race <seed> {code[:16]}…\n"
                f"Anyone can run it — codes carry the genome only.")
    lines = ["Your species — challenge codes (share freely, genome only):"]
    for name in sorted(births):
        rec = births[name]
        g = rec.get("genome")
        eidos = rec.get("eidos", "?")
        if g:
            code = vstate.encode_genome(g)
            lines.append(f"  {eidos:<14} {name:<28} {code}")
        else:
            lines.append(f"  {eidos:<14} {name:<28} (code unavailable — "
                         f"born pre-VIV-13, skill no longer installed)")
    lines.append("")
    lines.append("Race them: /vivarium race <seed-word> <code> [<code> …]")
    return "\n".join(lines)


def _media_offer() -> str:
    """Shared policy: see media_policy.py."""
    try:
        from . import media_policy as vmp
    except ImportError:  # pragma: no cover
        import media_policy as vmp
    return vmp.media_offer(vstate.state())


def _universe_view_text(header: str) -> str:
    """VIV-35: start/restart deliver the universe VISUALLY, best-effort.

    Graphics-capable terminal: paint the dish inline (same overlay path
    as /vivarium render --image). Chat platforms / plain terminals: save
    the PNG, point at it, and fall back to the rich ASCII map so nobody
    leaves empty-handed.
    """
    if not _universe_live():
        return header
    w = _world()
    try:
        from . import artifacts as vart
    except ImportError:  # pragma: no cover
        import artifacts as vart
    path = vart.render_dish_png(vstate.state(), w, f"universe_{w.tick}")
    text = header
    try:
        from . import termrender as vterm
    except ImportError:  # pragma: no cover
        import termrender as vterm
    kind = vterm.detect_graphics()
    if path and kind in ("kitty", "iterm2", "sixel"):
        size = vterm.png_size(path) or (342, 339)
        res_rows = max(1, math.ceil(size[1] / vterm.CELL_H))
        res_cols = max(20, math.ceil(size[0] / vterm.CELL_W))
        spacer = "\n".join(" " * res_cols for _ in range(res_rows))
        graphics = vterm.paint_over(path, res_rows, 0, delay=0.4)
        return (text + "\n\n" + spacer
                + (f"\n{graphics}" if graphics else ""))
    # No inline graphics: hand over the image + rich ASCII
    rich = vworld.render_ascii_rich(w, cols=80, rows=26)
    tail = ("\n\nA live picture of your universe is saved at:\n  " + path
            if path else "")
    tail += ("\n\nFor the full experience, open Vivarium from a graphics "
             "capable terminal (kitty, WezTerm, iTerm2) — the dish paints "
             "as a real image there. More info: "
             "https://github.com/r3adaszer0/vivarium")
    return text + "\n\n" + rich + tail


def _start_text() -> str:
    """VIV-26/VIV-35: the welcome/briefing + the universe view."""
    offer = _media_offer()
    if _universe_live():
        return _universe_view_text(
            "🌌 The Vivarium is alive. Here it is "
            "(/vivarium status for numbers):") + "\n" + _HELP + offer
    return _DORMANT_BRIEF + offer


def _staleness_text() -> str:
    """Plain-language staleness verdict from the sampled curve + live dish."""
    try:
        from . import codex as vcodex
    except ImportError:  # pragma: no cover
        import codex as vcodex
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


def _narration_text(rest: list) -> str:
    """VIV-31: /vivarium narration on|off — the advanced-user channel.

    off: walkthrough acts are suppressed; bare birth lines (name + ID)
    still fire and the dormant brief stays. on: the full story.
    """
    try:
        from . import acts as vacts
    except ImportError:  # pragma: no cover
        import acts as vacts
    s = vstate.state()
    if not rest:
        mode = "off" if not vacts.narration_on(s) else "on"
        return (f"Walkthrough narration: {mode}.\n"
                "Set with: /vivarium narration on|off "
                "(off keeps bare birth lines and the dormant brief)")
    mode = rest[0].lower()
    if mode not in ("on", "off"):
        return "Usage: /vivarium narration on|off"
    vacts.set_narration(s, mode)
    if mode == "off":
        return ("Narration off. The dish keeps living quietly: birth "
                "notices become bare name + ID lines and the dormant "
                "brief stays. /vivarium narration on brings the story "
                "back.")
    return ("Narration on. The walkthrough acts will guide the journey: "
            "the Big Bang tour, meeting your first Hermi, the Codex "
            "introduction, extinctions, and the multiplayer ritual.")


def _clip_text(rest: list) -> str:
    """VIV-33: /vivarium clip [species] [ticks] — the dish as an MP4.

    Renders the dish tick-by-tick with the cinematography engine and
    encodes MP4 via the ffmpeg rawvideo pipe (PIL frames; no numpy/
    imageio dependency). A species argument highlights that lineage and
    zooms to its centroid; plain clip films the whole dish.
    The video lands in the media gallery (see /vivarium serve).
    """
    try:  # package mode / flat mode
        from . import cinematography as vcin
        from . import artifacts as vart
    except ImportError:  # pragma: no cover
        import cinematography as vcin
        import artifacts as vart
    if not _universe_live():
        return _dormant_tool_result("clip")
    ticks = 120
    target = None
    zoom = False
    for a in rest:
        if a.isdigit():
            ticks = max(10, min(600, int(a)))
        elif a in ("--zoom", "zoom"):
            zoom = True
        else:
            target = a
    w = _world()
    # resolve the target species (Eidos id or skill-name fragment)
    lineage = None
    births = vstate.state().get("births", {})
    if isinstance(births, dict) and target:
        if target in births:
            lineage = births[target].get("eidos")
        else:
            for n, rec in births.items():
                if target.lower() in n.lower() or \
                        str(rec.get("eidos", "")).lower() == target.lower():
                    lineage = rec.get("eidos")
                    break
        if lineage is None:
            return (f"Unknown species '{target}'. /vivarium show lists "
                    f"the roster.")
    if not w.creatures:
        return "The dish is empty — nothing to film yet."
    # zoom target: the lineage's centroid, else the dish center
    region = None
    if zoom or lineage:
        members = [c for c in w.creatures
                   if c.alive() and (lineage is None or c.lineage == lineage)]
        if members:
            cx = sum(c.x for c in members) // len(members)
            cy = sum(c.y for c in members) // len(members)
            region = (cx, cy, 12)
    # lineage colors: highlight target, dim others
    colors = {}
    if lineage:
        try:  # package mode / flat mode
            from . import identity as vident
        except ImportError:  # pragma: no cover
            import identity as vident
        g = (births or {}).get(target, {}).get("genome")
        hue = g["hue"] if g else None
        for c in w.creatures:
            if c.lineage == lineage and hue is not None:
                colors[c.lineage] = vident.color_for(hue)
        colors.setdefault("__dim__", (70, 74, 84))
    start_tick = w.tick
    name = f"clip_{start_tick}_{lineage or 'dish'}.mp4"
    path = f"{vart.media_dir(vstate.state())}/{name}"
    try:
        vcin.render_clip_ffmpeg(w, path, ticks=ticks, region=region,
                                lineage_colors=colors or None,
                                highlight=lineage)
    except FileNotFoundError:
        return ("ffmpeg is required to encode the clip but is not on "
                "this machine's PATH. The dish still lives — install "
                "ffmpeg and try again.")
    return (f"🎥 Clip written: {path}\n"
            f"  {ticks} ticks of the dish at tick {start_tick}"
            f"{' — ' + lineage + ' highlighted' if lineage else ''}\n"
            f"Watch it in the gallery: /vivarium serve "
            f"(or open the file directly).")


def _show_text(rest: list) -> str:
    """VIV-32: /vivarium show [name|id] — meet one species up close.

    Accepts an Eidos ID (Eidos_1a2b3c), a skill name, or a unique
    fragment. Shows the species card (face, name, traits, population);
    --image paints the species glyph via the overlay.
    """
    s = vstate.state()
    births = s.get("births", {})
    if isinstance(births, list):
        births = {}
    if not births:
        return ("No species have been born yet. The Big Bang (first skill "
                "learned) seeds the founding roster; every later skill "
                "births one more.")
    rec = None
    name = None
    if rest:
        query = rest[0]
        if query in births:
            rec, name = births[query], query
        else:
            matches = [n for n in births
                       if query.lower() in n.lower()
                       or str(births[n].get("eidos", "")).lower()
                       .endswith(query.lower())]
            eidos_hits = [n for n in births
                          if str(births[n].get("eidos", "")).lower()
                          == query.lower()]
            matches = eidos_hits or matches
            if len(matches) == 1:
                rec, name = births[matches[0]], matches[0]
            elif len(matches) > 1:
                return ("Ambiguous — matches: " + ", ".join(sorted(matches))
                        + "\nUse a longer fragment or the full Eidos ID.")
    if rec is None:
        if rest:
            return (f"Unknown species '{rest[0]}'. /vivarium show lists "
                    f"every species.")
        lines = ["Who would you like to meet? Species in this universe:"]
        for n in sorted(births):
            lines.append(f"  {births[n].get('eidos', '?')}  ({n})")
        lines.append("Meet one: /vivarium show <Eidos ID or name>")
        return "\n".join(lines)
    eidos = rec.get("eidos", "?")
    genome = rec.get("genome")
    if not genome:
        return (f"{eidos} was born before genome storage — its genes can "
                f"no longer be re-derived. It lives on in the dish.")
    w = _world()
    count = sum(1 for c in w.creatures
                if c.lineage == eidos and c.alive())
    try:
        from . import identity as vident
    except ImportError:  # pragma: no cover
        import identity as vident
    card = vident.species_card(eidos, genome, vident.color_for(genome["hue"]),
                               lineage_count=count,
                               founding_skill=name or "")
    if "--image" in rest or "image" in rest:
        try:
            from . import artifacts as vart
            from . import termrender as vterm
        except ImportError:  # pragma: no cover
            import artifacts as vart
            import termrender as vterm
        path = vart.render_glyph_png(s, eidos, genome)
        if path:
            size = vterm.png_size(path) or (220, 220)
            res_rows = max(1, math.ceil(size[1] / vterm.CELL_H))
            res_cols = max(20, math.ceil(size[0] / vterm.CELL_W))
            spacer = "\n".join(" " * res_cols for _ in range(res_rows))
            graphics = vterm.paint_over(path, res_rows, 0, delay=0.4)
            return card + "\n\n" + spacer + (
                f"\n{graphics}" if graphics else "")
    return card


def _do_restart() -> str:
    """End this era: archive fossils, clear the world, mark the universe dormant.

    The next learned skill (or /vivarium seed) triggers the new Big Bang at
    era N+1 with a rotated key — never the same world twice. Fossils, Codex
    and the species roster carry over; the dish starts empty.
    """
    try:
        from . import universe as vuniverse
    except ImportError:  # pragma: no cover
        import universe as vuniverse
    s = vstate.state()
    old = vuniverse.universe_record(s)
    old_era, old_fp = old.get("era", 1), old.get("key_fp", "?")
    # VIV-35: capture the era's LAST dish before it clears — the farewell
    # picture. Rendered from the pre-restart world, delivered after.
    farewell_png = None
    try:
        w_old = _world()
        from . import artifacts as vart
        farewell_png = vart.render_dish_png(
            s, w_old, f"era{old_era}_final_{w_old.tick}")
    except Exception:
        farewell_png = None
    rec = vuniverse.restart(s, load_world=_world, clear_world=_clear_world,
                            reason="user restart via /vivarium restart")
    text = (
        f"🌌 Era {old_era} ended (universe {old_fp}). Champions archived as "
        f"fossils; they can be re-released into any future dish.\n\n"
        f"The next skill this agent learns births a brand-new world, derived "
        f"with a fresh key. Your Codex and species roster carry over."
        f"{_media_offer()}"
    )
    if farewell_png:
        try:
            from . import termrender as vterm
        except ImportError:  # pragma: no cover
            import termrender as vterm
        kind = vterm.detect_graphics()
        if kind in ("kitty", "iterm2", "sixel"):
            size = vterm.png_size(farewell_png) or (342, 339)
            res_rows = max(1, math.ceil(size[1] / vterm.CELL_H))
            res_cols = max(20, math.ceil(size[0] / vterm.CELL_W))
            spacer = "\n".join(" " * res_cols for _ in range(res_rows))
            # trail = every text row printed AFTER the reserved rows (the
            # era-ended briefing + offer). The overlay must climb over
            # them or the picture lands low (user-measured ~6 rows).
            trail_rows = text.count("\n") + 1 if text else 0
            graphics = vterm.paint_over(
                farewell_png, res_rows, trail_rows, delay=0.4)
            text = (f"The last picture of era {old_era}:\n\n" + spacer
                    + (f"\n{graphics}" if graphics else "")
                    + "\n\n" + text)
        else:
            text = (f"The last picture of era {old_era} is saved at:\n  "
                    f"{farewell_png}\n\n" + text)
    return text


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
                "Check the Vivarium: an artificial-life world living inside this "
                "agent. Returns population, lineage breakdown, averages and an ASCII "
                "map of the dish. Use when the user asks about their creatures, the "
                "dish, or the living world."
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
                "shading, creatures as X marks. Set rich=true for a denser "
                "block-character view (needs a wide terminal). Use when the user "
                "wants to *see* the living world."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cols": {"type": "integer", "description": "map width (default 64, rich 96)"},
                    "rows": {"type": "integer", "description": "map height (default 24, rich 32)"},
                    "rich": {"type": "boolean", "description": "dense block-character view"},
                    "color": {"type": "boolean", "description": "truecolor creatures (terminal only)"},
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
                "user wants to feed their creatures or nudge the living world."
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
        name="vivarium_export", toolset="vivarium",
        schema={
            "description": (
                "Export Vivarium species as VIV1 challenge codes — the shareable "
                "genome strings used to enter races (/vivarium race) or send a "
                "strain to another agent. Optionally narrow to one species by name."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "species/skill name (optional; omit for all)"},
                },
                "required": [],
            },
        },
        handler=_tool_export, emoji="🧾",
    )
    ctx.register_tool(
        name="vivarium_codex", toolset="vivarium",
        schema={
            "description": (
                "Show the Vivarium Codex: the patterns discovered in this user's "
                "universe (living-world events like still lifes and pulses), with "
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
