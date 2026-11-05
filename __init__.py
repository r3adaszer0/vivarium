"""Vivarium — a persistent artificial-life ecosystem inside Hermes.

The dish: a grid where food regrows and diffuses, and genome-carrying
creatures forage, reproduce, mutate and go extinct. Hermes's own tool
calls drop nutrients into the world; the world's state is injected back
as ecology narration each turn. Lives in ``~/.hermes/plugins/vivarium/``;
world state persists in ``ctx.state``-managed JSON on disk.
"""

from __future__ import annotations

from . import world  # noqa: F401  (package body must stay import-cheap)

__version__ = "0.1.0"


def register(ctx) -> None:
    """Register Vivarium's hooks, tools and slash command with Hermes."""
    from .hooks import register_hooks
    from .tools import register_tools

    register_hooks(ctx)
    register_tools(ctx)
