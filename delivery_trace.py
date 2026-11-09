"""Delivery trace: one line per stage of a story beat.

The beat pipeline has five stages (event -> queue -> arm -> flush ->
paint). When a beat goes missing there is no way to tell which stage
dropped it from the outside: the printer is a background thread, hooks
are fail-open, and the TUI owns the screen. This module writes a
timestamped, append-only trace next to the plugin state so a single test
answers "where did it die?" instead of an hour of guessing.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path

_MAX_LINES = 400


def _path() -> Path:
    root = os.environ.get("HERMES_PLUGIN_DATA") or ""
    if not root:
        base = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
        root = str(base / "plugin-data" / "vivarium")
    p = Path(root)
    p.mkdir(parents=True, exist_ok=True)
    return p / "delivery.log"


def log(event: str, **fields) -> None:
    try:
        rec = {"t": _dt.datetime.now().isoformat(timespec="seconds"),
               "event": event}
        rec.update({k: v for k, v in fields.items() if v is not None})
        line = json.dumps(rec, ensure_ascii=False, default=str)
        p = _path()
        lines = []
        if p.exists():
            try:
                lines = p.read_text(encoding="utf-8").splitlines()
            except OSError:
                lines = []
        lines.append(line)
        p.write_text("\n".join(lines[-_MAX_LINES:]) + "\n", encoding="utf-8")
    except Exception:
        pass          # tracing must never break delivery


def tail(n: int = 12) -> str:
    try:
        p = _path()
        if not p.exists():
            return "(no delivery events yet)"
        lines = p.read_text(encoding="utf-8").splitlines()[-max(1, n):]
        return "\n".join(lines) if lines else "(no delivery events yet)"
    except Exception:
        return "(trace unavailable)"
