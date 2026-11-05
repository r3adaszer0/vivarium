"""Skill discovery — enumerate installed skills, classify canon vs private.

Canon: byte-identical to the bundled catalog (shipped with Hermes, same on
every machine) -> plain-hash derivation, the Founding Forty, public namespace.
Private: anything else (user-written or user-modified) -> keyed HMAC.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Dict, List

try:
    from hermes_cli.config import get_hermes_home  # type: ignore
except Exception:  # pragma: no cover - outside Hermes runtime
    def get_hermes_home() -> Path:
        return Path(os.path.expanduser("~/.hermes"))

BUNDLED_SKILLS_DIR = Path("/usr/local/lib/hermes-agent/skills")
CANON_DOMAIN = b"VIVARUM-CANON-v1"   # domain-separated, version-pinned


def _skill_md_files(root: Path) -> Dict[str, Path]:
    """name -> SKILL.md path for every skill under root (category dirs ok)."""
    found: Dict[str, Path] = {}
    if not root.is_dir():
        return found
    for p in root.rglob("SKILL.md"):
        name = p.parent.name
        if name not in found:            # first (shortest) path wins
            found[name] = p
    return found


def discover(skills_dir: Path = None) -> List[dict]:
    """All installed skills classified for seeding.

    Returns [{name, path, bytes, is_canon, kind}] where kind in
    {"canon", "private-modified", "private"}.
    """
    skills_dir = Path(skills_dir or get_hermes_home() / "skills")
    bundled = _skill_md_files(BUNDLED_SKILLS_DIR)
    installed = _skill_md_files(skills_dir)
    out: List[dict] = []
    for name, path in sorted(installed.items()):
        data = path.read_bytes()
        bundle = bundled.get(name)
        if bundle is not None and bundle.read_bytes() == data:
            kind = "canon"
            is_canon = True
        elif bundle is not None:
            kind = "private-modified"    # stock skill, locally edited
            is_canon = False
        else:
            kind = "private"             # user-created
            is_canon = False
        out.append({"name": name, "path": str(path), "bytes": data,
                    "is_canon": is_canon, "kind": kind})
    return out


def canon_digest(data: bytes) -> bytes:
    """Public, version-pinned derivation for stock skills (no key needed)."""
    return hashlib.sha256(CANON_DOMAIN + data).digest()
