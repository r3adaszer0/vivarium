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
    if kind not in ("kitty", "iterm2", "sixel"):
        return ""
    offer = ("\n\n🖼️ Graphics-capable terminal detected — the dish "
             "renders as a real image by default. Disable anytime: "
             "/vivarium images off")
    if directive:
        offer += ("\n(vivarium layout: relay the text above first, then call "
                  "vivarium_render with image=true — it paints the dish "
                  "inline in this terminal and reserves its rows — then "
                  "continue your reply below the picture. Do not repeat the "
                  "image as ASCII.)")
    return offer
