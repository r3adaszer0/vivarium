"""Demo: create a dish, run 300 ticks, show stats + map. `python3 demo.py`"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from world import new_world, run, stats, render_ascii

w = new_world(seed=2026)
for _ in range(6):
    run(w, 50)
    s = stats(w)
    lin = ", ".join(f"{n}×{c}" for n, c in s["lineages"])
    print(f"tick {s['tick']:>4} | pop {s['population']:>3} | born {s['born']:>4} "
          f"died {s['died']:>4} | {lin}")
print()
print(render_ascii(w, cols=64, rows=22))
print()
code = __import__("state").encode_genome(stats(w) and w.creatures[0].genome)
print(f"sample challenge code ({len(code)} chars): {code[:60]}...")
