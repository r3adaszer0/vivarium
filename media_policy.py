"""Media-delivery policy shared by tools (slash) and hooks (narration).

The offer: one line, once, on graphics-capable terminals — default-ON
images with a disable path (user decision, 2980540). The no-nag rule:
once media_pref is anything but auto, the offer never appears again.
"""
from __future__ import annotations

try:  # package context (Hermes plugin) or flat import (tests)
    from . import termrender as vterm
except ImportError:  # pragma: no cover
    import termrender as vterm

MEDIA_PREF_KEY = "media_pref"          # "auto" | "image" | "ascii"


def media_pref(s) -> str:
    val = s.get(MEDIA_PREF_KEY, "auto")
    return val if val in ("auto", "image", "ascii") else "auto"


def set_media_pref(s, mode: str) -> str:
    if mode not in ("auto", "image", "ascii"):
        raise ValueError("media_pref must be auto|image|ascii")
    s.set(MEDIA_PREF_KEY, mode)
    return mode


def media_offer(s, *, directive: bool = False) -> str:
    """One-line offer for narrations; empty when decided or incapable.

    directive=True (Big Bang / birth narrations): also instruct the AGENT
    to paint the dish now — the agent reads the narration as context and
    can run ``/vivarium render --image`` in the same turn, so a
    graphics-capable user sees the newborn dish without asking. The
    paint itself must happen via the slash (tool results can't paint;
    TUI-ownership law), which is exactly what the directive asks for.
    """
    if media_pref(s) != "auto":
        return ""
    kind = vterm.detect_graphics()
    offer = ("\n\n🖼️ Graphics-capable terminal detected — Vivarium "
             "paints the dish here automatically (Big Bang, births, "
             "status). Disable anytime: /vivarium images off")
    if directive:
        # VIV-79: the directive is about the RELAY TARGET, not about this
        # process. Gateway/chat processes are headless — detect_graphics()
        # is "none" there no matter what the user's terminal really is
        # (the doctor trace proved it), so gating the directive on it
        # silently deleted it from every relayed card and the image was
        # lost. Interactive-graphics processes paint themselves; every
        # other drain must instruct the agent to attach the picture.
        import sys as _sys
        interactive = getattr(_sys.stdout, "isatty", lambda: False)()
        if interactive and kind in ("kitty", "iterm2", "sixel"):
            return offer
        return ("\n\n(When you relay this card, ALSO call the "
                "vivarium_render tool with image=true in the same turn so "
                "the dish image is attached to your reply.)")
    if kind not in ("kitty", "iterm2", "sixel"):
        return ""
    return offer
