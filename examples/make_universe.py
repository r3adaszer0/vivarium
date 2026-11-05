"""Birth your real universe: discover this machine's skills, seed the dish,
run the Hadean era, and render the result (PNG + terminal block map).

Uses the REAL PluginState (hermes_cli.plugins_state), so the universe is born
into ~/.hermes/plugin-data/vivarium/ — exactly where the installed plugin
will find it. The universe key is generated here, once, and never printed.

Usage: .venv/bin/python make_universe.py [--ticks N]
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import discovery as vdisc   # noqa: E402
import seeding as S         # noqa: E402
import universe as U        # noqa: E402
import world as W           # noqa: E402


def real_state():
    from hermes_cli.plugins_state import PluginState
    return PluginState("vivarium")


def save_world(w):
    real_state().set(U.UNIVERSE_KEY_DATA if hasattr(U, "UNIVERSE_KEY_DATA")
                     else "world", w.to_dict())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=int, default=300)
    args = ap.parse_args()

    s = real_state()
    rec = U.universe_record(s)
    print(f"universe: status={rec['status']} era={rec.get('era', 1)} "
          f"key_fp={rec['key_fp']}")

    if rec["status"] == "live":
        d = s.get("world")
        w = W.World.from_dict(d) if d else None
        if w is None:
            raise SystemExit("live universe but no world data — inspect state")
        print("universe already live — showing the current dish")
    else:
        skills = vdisc.discover()
        canon = [sk for sk in skills if sk["is_canon"]]
        priv = [sk for sk in skills if not sk["is_canon"]]
        print(f"discovered {len(skills)} skills: {len(canon)} canon, {len(priv)} private")
        out = S.seed(s, skills, save_world=save_world)
        if out is None:
            raise SystemExit("seeding refused (not dormant?)")
        w = out["world"]
        print(S.onboard_message(out))
        print()
        print("Genesis species:")
        for sp in out["canon_species"][:8]:
            print(f"  {sp['eidos']}  ← {sp['name']}")
        if len(out["canon_species"]) > 8:
            print(f"  … and {len(out['canon_species']) - 8} more canon species")
        for sp in out["private_species"]:
            print(f"  {sp['eidos']}  ← {sp['name']} (PRIVATE)")

    print(f"\nHadean era: advancing {args.ticks} ticks…")
    W.run(w, ticks=args.ticks)
    save_world(w)
    st = W.stats(w)
    print(f"after {args.ticks} ticks: {st['population']} creatures, "
          f"{len(st.get('lineages', []))} lineages alive")
    for name, count in st.get("lineages", []):
        print(f"  {name}: {count}")
    print()
    print("=== TERMINAL VIEW (block map: ░▒▓ food, letters = lineage initial) ===")
    print(W.render_ascii(w, cols=64, rows=24))


if __name__ == "__main__":
    main()
