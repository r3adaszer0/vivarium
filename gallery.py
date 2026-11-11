"""The Hermi Gallery: /vivarium serve as a naturalist's ledger (VIV-89).

One self-contained HTML page, stdlib only, wired to REAL state:
- the masthead carries the era chip, the seed fingerprint and the
  localhost-only promise;
- THE PULSE: one band per universe this dish has known (the current one
  plus every key found in the fossil record), above the living population
  curve of the current era;
- NOW: the dish (rich ASCII map parsed to a pixel canvas, or the newest
  archived dish PNG when the universe sleeps), the census beside it;
- THE CHAPTERS: the current universe's registry — every birth as a
  certificate (face from identity.glyph_rgb_cells, name from
  identity.name_of, genes, genome chip, alive/extinct), the era's clips
  as a filmstrip and its artifacts as snapshots; every CLOSED universe
  (each distinct fossil key) keeps its own shelf of the fallen;
- an appendix lists files too old to attribute to any era, by date.

Nothing here phones home: the server binds 127.0.0.1 and the page pulls
every byte from that server.
"""
from __future__ import annotations

import html as _html
import json as _json
import os
import time as _time

try:  # package context (Hermes plugin) or flat import (tests)
    from . import identity as vid
except ImportError:  # pragma: no cover
    import identity as vid


# ── palette (the terminal's own) ──────────────────────────────────────────────
BG, PANEL, PANEL2, RAISE = "#0a0f0d", "#0f1813", "#12211a", "#16281f"
LINE, INK, MUT, DIMINK = "#1e3529", "#cfe8d8", "#8fb4a0", "#5d7f6e"
ACC, AMBER, ROSE = "#7cc7ff", "#e6b85a", "#e96a8a"
LIVE_DOT = "#57d98b"

_CSS = """
:root{--bg:%(BG)s;--panel:%(PANEL)s;--panel2:%(PANEL2)s;--raise:%(RAISE)s;
--line:%(LINE)s;--ink:%(INK)s;--mut:%(MUT)s;--dimink:%(DIMINK)s;
--acc:%(ACC)s;--amber:%(AMBER)s;--rose:%(ROSE)s;
--mono:ui-monospace,"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;
--serif:Georgia,"Times New Roman",serif}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--ink);font-family:var(--mono);font-size:14px;
line-height:1.5;margin:0;-webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:0 28px}
header{padding:38px 0 22px;border-bottom:1px solid var(--line)}
.wordmark{font-size:13px;letter-spacing:.24em;color:var(--mut);text-transform:uppercase}
.wordmark b{color:var(--ink);font-weight:600}
.rule{display:flex;align-items:center;gap:14px;margin-top:10px}
.rule h1{font-size:30px;font-weight:600;letter-spacing:-.01em;margin:0}
.rule .tick{flex:1;height:1px;background:var(--line)}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px;align-items:center}
.chip{font-size:11px;letter-spacing:.06em;color:var(--mut);border:1px solid var(--line);
border-radius:4px;padding:4px 9px;background:var(--panel)}
.chip .dot{display:inline-block;width:7px;height:7px;border-radius:50%%;margin-right:6px;
vertical-align:1px}
.chip.live .dot{background:%(LIVE)s;box-shadow:0 0 6px %(LIVE)s88}
.chip.dorm .dot{background:var(--dimink)}
.chip.key{color:var(--acc);border-color:#1e3a52}
.chip.lock{color:var(--amber);border-color:#4a3c1e}
.search{margin-left:auto;display:flex;align-items:center;gap:8px;border:1px solid var(--line);
border-radius:5px;background:var(--panel);padding:5px 10px;min-width:250px}
.search input{background:none;border:0;outline:0;color:var(--ink);font-family:var(--mono);
font-size:12px;width:100%%}
.search input::placeholder{color:var(--dimink)}
.search kbd{font-size:10px;color:var(--dimink);border:1px solid var(--line);border-radius:3px;
padding:1px 5px}
nav.eras{display:flex;gap:6px;overflow-x:auto;padding:12px 0 0;scrollbar-width:none}
nav.eras::-webkit-scrollbar{display:none}
nav.eras a{color:var(--dimink);text-decoration:none;font-size:11px;padding:4px 9px;
border:1px solid transparent;border-radius:4px;white-space:nowrap}
nav.eras a:hover{color:var(--ink);border-color:var(--line)}
nav.eras a.cur{color:var(--amber);border-color:#4a3c1e;background:#1a1608}
section{padding:46px 0 8px}
.kicker{font-size:11px;letter-spacing:.28em;color:var(--dimink);text-transform:uppercase}
.kicker b{color:var(--mut);font-weight:500}
.sub{color:var(--mut);font-size:12.5px;margin:6px 0 0;max-width:640px}
.nowsec{display:grid;grid-template-columns:minmax(0,420px) 1fr;gap:26px;margin-top:22px}
.dishwrap{position:relative;border:1px solid var(--line);border-radius:8px;background:#060a08;
padding:14px;overflow:hidden}
.dishwrap .dish-title{position:absolute;top:14px;left:16px;font-size:10px;letter-spacing:.2em;
color:var(--dimink);text-transform:uppercase;z-index:2}
canvas.dish{width:100%%;height:auto;display:block;border-radius:4px;image-rendering:pixelated}
img.dishpng{width:100%%;display:block;border-radius:4px;image-rendering:pixelated}
.plate{position:absolute;left:14px;bottom:14px;font-size:10.5px;background:#0b0f0dcc;
border:1px solid #4a2a38;border-radius:4px;padding:3px 8px;color:#ffd7e2;white-space:nowrap}
.plate small{color:#b58496;margin-left:6px}
.nowside{display:flex;flex-direction:column;gap:14px}
.census{border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:16px 18px}
.census .line{font-size:13px;color:var(--mut)}
.census .line b{color:var(--ink);font-weight:600}
.census .line .sep{color:var(--dimink);margin:0 7px}
.census .line .hi{color:var(--amber)}
.statgrid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:7px 26px;
margin-top:12px;font-size:12px;color:var(--mut)}
.statgrid b{color:var(--ink);font-weight:500;float:right}
.sleepline{margin-top:14px;font-size:12px;color:var(--dimink);font-style:italic;
font-family:var(--serif)}
.latest{display:flex;gap:12px;align-items:center;border:1px solid var(--line);border-radius:8px;
background:var(--panel);padding:12px;text-decoration:none}
.latest .face{flex:none;width:64px;display:block}
.latest .face svg{display:block;width:64px;height:64px}
.latest .meta{min-width:0}
.latest .meta .t{font-size:12.5px;color:var(--ink);display:block}
.latest .meta .d{font-size:11px;color:var(--dimink);margin-top:3px;display:block;
white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.latest .meta .d.see{color:var(--acc)}
.latest .meta .d.chip-line{font-family:var(--mono);letter-spacing:.02em}
.chapter{display:grid;grid-template-columns:96px minmax(0,1fr);gap:0;margin-top:14px;
border-top:1px solid var(--line);padding-top:34px}
.rail{align-self:start;text-align:left;padding-left:2px}
.rail .num{font-size:44px;font-weight:600;color:var(--ink);letter-spacing:-.04em;line-height:1}
.rail .when{font-size:10.5px;color:var(--dimink);margin-top:8px;line-height:1.6;
word-break:break-all}
.rail .badge{display:inline-block;margin-top:10px;font-size:9.5px;letter-spacing:.14em;
text-transform:uppercase;padding:3px 8px;border-radius:3px;border:1px solid}
.rail .badge.bang{color:var(--amber);border-color:#4a3c1e;background:#1a1608}
.rail .badge.div{color:var(--acc);border-color:#1e3a52;background:#0b1620}
.rail .badge.dead{color:var(--dimink);border-color:var(--line)}
.rail .tally{margin-top:12px;font-size:11px;color:var(--mut)}
.rail .tally .up{color:%(LIVE)s}.rail .tally .dn{color:var(--rose)}
.chead{margin-bottom:20px}
.chead h2{font-size:19px;font-weight:600;margin:0;letter-spacing:-.01em}
.chead p{color:var(--mut);font-size:12.5px;margin:6px 0 0;max-width:620px}
.block{margin-top:26px}
.block .bt{font-size:10.5px;letter-spacing:.22em;color:var(--dimink);text-transform:uppercase;
display:flex;align-items:center;gap:12px}
.block .bt:after{content:"";flex:1;height:1px;background:var(--line)}
.snaprow{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-top:14px}
.snap{border:1px solid var(--line);border-radius:7px;background:#060a08;overflow:hidden}
.snap img{width:100%%;display:block;image-rendering:pixelated;cursor:zoom-in}
.snap .cap{display:flex;justify-content:space-between;font-size:10px;color:var(--dimink);
padding:7px 9px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.film{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:14px}
.clip{border:1px solid var(--line);border-radius:7px;overflow:hidden;background:var(--panel);
cursor:pointer;transition:border-color .15s,transform .15s}
.clip:hover{border-color:#35594a;transform:translateY(-2px)}
.clip .frame{position:relative;aspect-ratio:16/9;background:#060a08}
.clip video{width:100%%;height:100%%;display:block;object-fit:cover;pointer-events:none}
.clip .frame .play{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
opacity:.85;transition:opacity .15s;pointer-events:none}
.clip:hover .frame .play{opacity:1}
.clip .frame .play svg{width:38px;height:38px;filter:drop-shadow(0 2px 4px #000b)}
.clip .cl{display:flex;justify-content:space-between;align-items:baseline;gap:10px;
padding:9px 11px;font-size:11.5px;color:var(--mut)}
.clip .cl span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.clip .cl small{color:var(--dimink);flex:none}
.registry{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:14px}
.cert{border:1px solid var(--line);border-radius:7px;background:var(--panel);padding:13px;
transition:border-color .15s,opacity .2s}
.cert:hover{border-color:#35594a}
.cert.hide{display:none}
.cert .top{display:flex;gap:11px;align-items:center}
.cert .face{width:46px;height:46px;flex:none;border-radius:6px;background:#0b120e;
border:1px solid var(--line)}
.cert .face svg{width:100%%;height:100%%;display:block;image-rendering:pixelated}
.cert .id{min-width:0}
.cert .id .nm{font-size:13px;color:var(--ink);font-weight:600;white-space:nowrap;
overflow:hidden;text-overflow:ellipsis}
.cert .id .ei{font-size:10.5px;color:var(--acc)}
.cert .id .fr{font-size:10.5px;color:var(--dimink);margin-top:1px;white-space:nowrap;
overflow:hidden;text-overflow:ellipsis}
.genes{margin-top:11px;display:grid;grid-template-columns:70px minmax(0,1fr) 36px;
gap:3px 9px;align-items:center;font-size:10px;color:var(--dimink)}
.genes .track{display:block;height:3px;border-radius:2px;background:#0d1a13;overflow:hidden}
.genes .fill{display:block;height:100%%;border-radius:2px;background:var(--acc)}
.genes .v{text-align:right;color:var(--mut)}
.cert .foot{display:flex;justify-content:space-between;align-items:center;margin-top:11px;
padding-top:10px;border-top:1px dashed #1a2c22;font-size:10px;color:var(--dimink)}
.cert .foot .st{display:flex;align-items:center;gap:5px}
.cert .foot .st .d{width:6px;height:6px;border-radius:50%%}
.cert .foot .st.alive .d{background:%(LIVE)s}
.cert .foot .st.gone .d{background:var(--dimink)}
.genome-chip{margin-top:9px;font-size:9.5px;color:var(--dimink);background:#0b120e;
border:1px solid #14231b;border-radius:4px;padding:4px 7px;line-height:1.5;
word-spacing:1px}
.fallen{margin-top:16px;border:1px solid var(--line);border-radius:8px;background:var(--panel);
padding:16px}
.shelf{display:flex;gap:10px;overflow-x:auto;padding-bottom:6px}
.shelf::-webkit-scrollbar{height:8px}
.shelf::-webkit-scrollbar-thumb{background:#22392e;border-radius:4px}
.spec{flex:none;width:118px;border:1px solid var(--line);border-radius:6px;background:#0c120f;
padding:10px;text-align:center}
.spec svg{width:56px;height:56px;image-rendering:pixelated}
.spec .ln{font-size:9.5px;color:var(--dimink);margin-top:7px;word-break:break-all}
.spec .un{font-size:9px;color:#3d554a;margin-top:3px}
.appendix{margin-top:10px;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
.app{border:1px solid var(--line);border-radius:6px;background:var(--panel);padding:8px;
font-size:10px;color:var(--dimink)}
.app a{color:var(--mut);text-decoration:none;word-break:break-all}
.app a:hover{color:var(--acc)}
.app .when{margin-top:3px;color:#3d554a}
footer{margin-top:64px;border-top:1px solid var(--line);padding:34px 0 60px;text-align:center}
footer .epi{font-family:var(--serif);font-style:italic;font-size:17px;color:var(--mut)}
footer .det{margin-top:14px;font-size:11px;color:var(--dimink);letter-spacing:.08em}
footer .det b{color:var(--mut);font-weight:500}
kbd.nav{font-size:10px;color:var(--dimink);border:1px solid var(--line);border-radius:3px;
padding:1px 6px}
dialog{background:var(--bg);color:var(--ink);border:1px solid var(--line);border-radius:10px;
max-width:900px;width:92vw;padding:14px}
dialog::backdrop{background:#000c}
dialog video{width:100%%;border-radius:6px;background:#000}
dialog .t{font-size:12px;color:var(--mut);margin-bottom:10px}
@media (max-width:960px){.nowsec{grid-template-columns:1fr}
.chapter{grid-template-columns:1fr}
.rail{display:flex;gap:16px;align-items:baseline;flex-wrap:wrap}
.registry{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}
.film{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}
.snaprow{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}
.appendix{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}}
@media (prefers-reduced-motion:no-preference){
.chip.live .dot{animation:beat 2.4s ease-in-out infinite}
@keyframes beat{0%%,100%%{box-shadow:0 0 4px %(LIVE)s55}50%%{box-shadow:0 0 9px %(LIVE)scc}}}
"""


# ── small builders ────────────────────────────────────────────────────────────
def _esc(s) -> str:
    return _html.escape(str(s), quote=True)


def _grid_json(rich_map: str) -> str:
    """SGR dish map -> compact hex grid for the web canvas.

    Each cell becomes RRGGBB + a one-char tier (solid=full block, dim for
    ▓▒░). Rows are '|' separated, cells ',' separated. Pure stdlib.
    VIV-91: creatures are SPACES with a BACKGROUND color (48;2;) — the
    parser tracks bg as well as fg, or every creature renders as lattice.
    """
    import re
    fg = (60, 120, 84)                     # the lattice default
    bg = None                              # creature blocks carry 48;2;
    rows = []
    for raw in (rich_map or "").splitlines():
        cells = []
        for tok in re.split(r"(\x1b\[[0-9;]*m)", raw):
            if tok.startswith("\x1b["):
                body = tok[2:-1]
                if body.startswith("38;2;"):
                    fg = tuple(int(x) for x in body[5:].split(";"))[:3]
                elif body.startswith("48;2;"):
                    bg = tuple(int(x) for x in body[5:].split(";"))[:3]
                elif body in ("0", ""):
                    fg = (60, 120, 84)
                    bg = None
                continue
            for ch in tok:
                if ch == " " and bg is not None:
                    r, g, b, a = *bg, "f"          # colored-space creature
                elif ch == "█":
                    r, g, b, a = *fg, "f"
                elif ch == "▓":
                    r, g, b, a = *fg, "b"
                elif ch == "▒":
                    r, g, b, a = *fg, "7"
                elif ch == "░":
                    r, g, b = max(fg[0] // 3, 8), max(fg[1] // 2, 18), fg[2] // 2
                    a = "4"
                else:
                    r, g, b, a = 10, 30, 20, "4"
                cells.append("%02x%02x%02x%s" % (r, g, b, a))
        if cells:
            rows.append(",".join(cells))
    return "|".join(rows)


def _face_svg(genome: dict, dead: bool = False, size: int = 46) -> str:
    """The REAL deterministic 7x7 glyph as inline SVG (identity spec)."""
    hue = float(genome.get("hue", 0.0))
    rgb = vid.color_for(hue)
    cells = vid.glyph_rgb_cells(genome, rgb)
    rects = []
    for y, row in enumerate(cells):
        for x, (r, g, b) in enumerate(row):
            if dead:
                lum = (r * 3 + g * 6 + b) // 10
                r = g = b = min(lum, 96)
            if (r, g, b) == (0, 0, 0) or (r < 12 and g < 12 and b < 14):
                continue
            rects.append(f'<rect x="{x}" y="{y}" width="1.02" height="1.02"'
                         f' fill="rgb({r},{g},{b})"/>')
    return (f'<svg viewBox="-0.02 -0.02 7.04 7.04" width="{size}" height="{size}"'
            f' shape-rendering="crispEdges" xmlns='
            f'"http://www.w3.org/2000/svg">{"".join(rects)}</svg>')


_GEN_LABEL = (("forage", "forage"), ("sense", "sense"),
              ("metabolism_mult", "metab"), ("aggression", "aggr"),
              ("mutate", "mutate"), ("dispersal", "disperse"))
_GEN_KEY = {"forage": "for", "aggression": "agg", "metabolism_mult": "met",
            "sense": "sen", "mutate": "mut", "dispersal": "dis"}


def _cert(skill: str, e: dict, extinct_hexes: frozenset) -> str:
    gen = e.get("genome") or {}
    eidos = e.get("eidos", "")
    hexid = eidos.replace("Eidos_", "")
    dead = hexid in extinct_hexes
    try:
        genus, epithet, _common = vid.name_of(gen)
        nm = f"{genus} {epithet}"
    except Exception:
        nm = "unnamed strain"
    bars = "".join(
        f'<span>{lbl}</span>'
        f'<span class="track"><span class="fill" '
        f'style="width:{max(3, min(100, float(gen.get(k, 0)) / 3 * 100)):.0f}%"></span></span>'
        f'<span class="v">{float(gen.get(k, 0)):.2f}</span>'
        for k, lbl in _GEN_LABEL)
    chip = " ".join(f"{_GEN_KEY.get(k, k[:3])}:{float(v):.2f}"
                    for k, v in gen.items() if k != "hue")
    q = _esc(skill) + " " + _esc(eidos) + " " + _esc(nm)
    return (f'<div class="cert" id="cert-{_esc(hexid)}" data-search="{q}">'
            f'<div class="top"><div class="face">{_face_svg(gen, dead)}</div>'
            f'<div class="id"><div class="nm">{_esc(nm)}</div>'
            f'<div class="ei">{_esc(eidos)}</div>'
            f'<div class="fr">from skill “{_esc(skill)}”</div></div></div>'
            f'<div class="genes">{bars}</div>'
            f'<div class="genome-chip" title="{_esc(chip)}">{_esc(chip)}</div>'
            f'<div class="foot"><span class="st {"gone" if dead else "alive"}">'
            f'<span class="d"></span>{"extinct" if dead else "alive"}</span>'
            f'<span>{_esc(e.get("day", ""))}</span>'
            f'<span class="cp" data-chip="{_esc(chip)}" '
            f'onclick="navigator.clipboard&&navigator.clipboard.writeText'
            f'(this.dataset.chip)">copy</span></div></div>')


def _latest_species(skill: str, e: dict, extinct_hexes: frozenset) -> str:
    """The newest birth, featured in NOW (VIV-92): face, name, genome chip,
    provenance — linked to its full certificate below."""
    gen = e.get("genome") or {}
    eidos = e.get("eidos", "")
    hexid = eidos.replace("Eidos_", "")
    dead = hexid in extinct_hexes
    try:
        genus, epithet, _common = vid.name_of(gen)
        nm = f"{genus} {epithet}"
    except Exception:
        nm = "unnamed strain"
    chip = " ".join(f"{_GEN_KEY.get(k, k[:3])}:{float(v):.2f}"
                    for k, v in gen.items() if k != "hue")
    return (f'<a class="latest" href="#cert-{_esc(hexid)}">'
            f'<span class="face">{_face_svg(gen, dead, 64)}</span>'
            f'<span class="meta">'
            f'<span class="t">Latest birth · {_esc(nm)}</span>'
            f'<span class="d">{_esc(eidos)} · era {_esc(e.get("era", "?"))} '
            f'· from skill “{_esc(skill)}”</span>'
            f'<span class="d chip-line">{_esc(chip)}</span>'
            f'<span class="d see">see its certificate ↓</span>'
            f'</span></a>')


def _specimen(lineage: str, genome: dict, universe: str, day: str) -> str:
    return (f'<div class="spec">{_face_svg(genome or {}, True, 56)}'
            f'<div class="ln">{_esc(lineage)}</div>'
            f'<div class="un">universe {_esc(universe[:8])} · {_esc(day)}</div></div>')


# ── the page ──────────────────────────────────────────────────────────────────
def build_page(media_dir: str, dish_map: str, title: str = "The Hermi Gallery",
               st=None, live_flag: bool = True) -> str:
    """Assemble the gallery from real plugin state.

    `live_flag` (VIV-90): when the serving process can answer
    /live/dish.json with a fresh dish per request, the canvas is marked
    data-live and the page asks for a new dish on every load.

    `st` is the plugin state handle (`.get(key, default)`); everything it
    provides is real — nothing is invented here.
    """
    births = (st.get("births", {}) if st else {}) or {}
    if not isinstance(births, dict):
        births = {}
    fossils = (st.get("fossils", []) if st else []) or []
    if not isinstance(fossils, (list, tuple)):
        fossils = []
    fossils = [f for f in fossils if isinstance(f, dict)]
    curve = (st.get("curve", []) if st else []) or []
    if not isinstance(curve, (list, tuple)):
        curve = []
    curve = [p for p in curve if isinstance(p, dict)]
    uni = (st.get("universe", {}) if st else {}) or {}
    if not isinstance(uni, dict):
        uni = {}
    era = uni.get("era", "?")
    key_fp = uni.get("key_fp", "—")
    status = uni.get("status", "dormant")
    live = status == "live"
    genesis_day = (uni.get("genesis") or {}).get("day", "")

    extinct_hexes = frozenset(
        (f.get("lineage", "").replace("Eidos_", "") for f in fossils))

    # media: this era (mtime >= genesis day, when known) vs the appendix
    now = _time.time()
    files = []
    if media_dir and os.path.isdir(media_dir):
        for name in sorted(os.listdir(media_dir)):
            p = os.path.join(media_dir, name)
            if not os.path.isfile(p) or name == "index.html":
                continue
            try:
                mt = os.path.getmtime(p)
            except OSError:
                continue
            files.append({"name": name, "mtime": mt, "path": name})
    this_era, earlier = [], []
    if genesis_day:
        try:
            import datetime as _dt
            gate = _time.mktime(_dt.date.fromisoformat(genesis_day).timetuple())
        except Exception:
            gate = 0
        for f in files:
            (this_era if f["mtime"] >= gate else earlier).append(f)
    else:
        this_era = list(files)
    clips = [f for f in this_era if f["name"].endswith(".mp4")]
    snaps = [f for f in this_era if f["name"].endswith(".png")]
    newest_png = max((f for f in files if f["name"].endswith(".png")),
                     key=lambda f: f["mtime"], default=None)

    # universes for the pulse: current + every fossil key
    closed = {}
    for f in fossils:
        u = f.get("universe", "?")
        slot = closed.setdefault(u, {"key": u, "n": 0, "days": []})
        slot["n"] += 1
        if f.get("day"):
            slot["days"].append(f["day"])
    closed_list = sorted(closed.values(),
                         key=lambda s: min(s["days"]) if s["days"] else "9")

    css = _CSS % {"BG": BG, "PANEL": PANEL, "PANEL2": PANEL2, "RAISE": RAISE,
                  "LINE": LINE, "INK": INK, "MUT": MUT, "DIMINK": DIMINK,
                  "ACC": ACC, "AMBER": AMBER, "ROSE": ROSE, "LIVE": LIVE_DOT}
    grid = _grid_json(dish_map)

    # ── masthead ──
    nav_items = [(key_fp, f"era {era}", True)] + [
        (s["key"], s["key"][:8], False) for s in closed_list]
    nav = "".join(
        f'<a href="#u{_esc(k)}"{" class=\"cur\"" if cur else ""}>{_esc(lbl)}</a>'
        for k, lbl, cur in nav_items)
    head = f"""<header id="top">
  <div class="wordmark"><b>vivarium</b> — hermes keeps the dish</div>
  <div class="rule"><h1>{_esc(title)}</h1><div class="tick"></div></div>
  <div class="chips">
    <span class="chip {'live' if live else 'dorm'}"><span class="dot"></span>Era {_esc(era)} · {_esc(status)}</span>
    <span class="chip key">seed {_esc(key_fp)}</span>
    <span class="chip">{len(fossils)} fossils</span>
    <span class="chip">{len(births)} births</span>
    <span class="chip lock">&#128274;&nbsp;127.0.0.1 only — never leaves this machine</span>
    <span class="search"><input id="q" placeholder="search eidos, skill, species…"
      aria-label="search"><kbd>/</kbd></span>
  </div>
  <nav class="eras" aria-label="universes">{nav}</nav>
</header>"""


    # ── now ──
    statgrid, dish_visual = "", ""
    if live and grid:
        # the dish canvas mirrors the dish's REAL shape (VIV-91): the grid
        # is built at the world's own cols/rows, so the web dish is the
        # same square the terminal paints — never a squashed strip.
        _rows = grid.count("|") + 1
        _cols = len(grid.split("|")[0].split(","))
        dish_visual = (f'<canvas class="dish" id="dish" data-grid="{_esc(grid)}"'
                       f'{"" if live_flag is False else " data-live"}'
                       f' width="{_cols * 10}" height="{_rows * 10}"></canvas>')
    elif newest_png:
        dish_visual = (f'<img class="dishpng" src="{_esc(newest_png["path"])}" '
                       f'alt="the last archived dish">')
    else:
        dish_visual = '<div style="height:200px;display:flex;align-items:center;'\
            'justify-content:center;color:#3d554a;font-size:12px">no dish archived yet</div>'
    if live:
        last = curve[-1] if curve else {}
        census = (f'<div class="line"><b id="census-tick">tick {_esc(last.get("tick", "—"))}</b>'
                  f'<span class="sep">·</span><b id="census-alive">{_esc(last.get("population", "—"))} alive</b>'
                  f'<span class="sep">·</span><span class="hi">the dish is live</span></div>')
    else:
        last = curve[-1] if curve else {}
        census = (f'<div class="line"><b>tick {_esc(last.get("tick", "—"))}</b>'
                  f'<span class="sep">·</span><b>{_esc(last.get("population", 0))} alive</b>'
                  f'<span class="sep">·</span>the dish sleeps until the next skill wakes it</div>')
    peak = max((int(p.get("population", 0)) for p in curve), default=0)
    span_t = max((int(p.get("tick", 0)) for p in curve), default=0)
    now_sec = f"""<div class="census">{census}
  <div class="statgrid">
    <span>births recorded <b>{len(births)}</b></span><span>peak <b>{peak}</b></span>
    <span>fossils <b>{len(fossils)}</b></span><span>universes closed <b>{len(closed_list)}</b></span>
  </div>
  <div class="sleepline">the dish is alive in silence — it speaks only when something is born.</div>
</div>"""
    # VIV-92: the featured card in NOW is the latest BORN SPECIES, not the
    # latest clip — the filmstrip below still holds every clip.
    latest = ""
    if births:
        def _newest():
            def key(kv):
                try:
                    era_v = int(kv[1].get("era", 0))
                except (TypeError, ValueError):
                    era_v = 0
                return (era_v, str(kv[1].get("day", "")))
            try:
                return max(births.items(), key=key)
            except (AttributeError, TypeError):
                return None
        pair = _newest()
        if pair and isinstance(pair[1], dict) and pair[1].get("eidos"):
            latest = _latest_species(pair[0], pair[1], extinct_hexes)
    now = f"""<section id="now">
  <div class="kicker">Now <b>· the dish as it stands</b></div>
  <div class="nowsec">
    <div class="dishwrap"><div class="dish-title">Era {_esc(era)} ·
      {_esc(status)}</div>{dish_visual}
      <div class="plate">the living dish<small>era {_esc(era)}</small></div></div>
    <div class="nowside">{now_sec}{latest}</div>
  </div>
</section>"""

    # ── chapters ──
    # current universe first, then the closed ones (fossil keys)
    cert_html = "".join(_cert(skill, e, extinct_hexes)
                        for skill, e in births.items() if isinstance(e, dict))
    era_clips = "".join(
        f'<div class="clip" data-src="{_esc(f["path"])}" data-name="{_esc(f["name"])}">'
        f'<div class="frame"><video src="{_esc(f["path"])}" muted preload="metadata"></video>'
        f'<div class="play"><svg viewBox="0 0 24 24" fill="#cfe8d8">'
        f'<path d="M8 5v14l11-7z"/></svg></div></div>'
        f'<div class="cl"><span>{_esc(f["name"])}</span><small>clip</small></div></div>'
        for f in clips)
    era_snaps = "".join(
        f'<div class="snap"><img src="{_esc(f["path"])}" alt="{_esc(f["name"])}" '
        f'loading="lazy"><div class="cap"><span>{_esc(f["name"])}</span>'
        f'<span>{_time.strftime("%H:%M", _time.localtime(f["mtime"]))}</span></div></div>'
        for f in snaps)

    cur_blocks = ""
    if era_snaps:
        cur_blocks += (f'<div class="block"><div class="bt">The dish &amp; artifacts '
                       f'· this era</div><div class="snaprow">{era_snaps}</div></div>')
    if era_clips:
        cur_blocks += (f'<div class="block"><div class="bt">The filmstrip · clips '
                       f'from this era</div><div class="film">{era_clips}</div></div>')
    else:
        cur_blocks += (f'<div class="block"><div class="bt">The filmstrip · clips '
                       f'from this era</div><div class="film"><div class="app" '
                       f'style="grid-column:1/-1;padding:14px">No clips filmed in '
                       f'this era yet — <a style="color:var(--mut)" href="#">'
                       f'/vivarium clip</a> films the live dish, and it lands here.'
                       f'</div></div></div>')
    if cert_html:
        cur_blocks += (f'<div class="block"><div class="bt">The registry · every '
                       f'Hermi ever born</div><div class="registry" id="registry">'
                       f'{cert_html}</div></div>')
    cur_chapter = f"""<div class="chapter" id="u{_esc(key_fp)}">
  <div class="rail"><div class="num">{_esc(era)}</div>
    <div class="when">began {_esc(genesis_day) or "—"}</div>
    <div class="badge {'bang' if live else 'dead'}">{'the living era' if live else 'dormant'}</div>
    <div class="tally"><span class="up">{len(births)} born</span> ·
      <span class="dn">{len(fossils)} fossil lines</span></div>
    <div class="when" style="margin-top:8px">seed {_esc(key_fp)}</div></div>
  <div><div class="chead"><h2>The living ledger</h2>
    <p>Every skill that ever ran put one seed in this universe's soil; the registry
       below is the complete birth record of era {_esc(era)}.</p></div>
    {cur_blocks}</div></div>"""

    closed_chapters = []
    for s in closed_list:
        shelf = "".join(
            _specimen(f.get("lineage", "?"), f.get("genome") or {},
                      s["key"], f.get("day", ""))
            for f in fossils if f.get("universe") == s["key"])
        days = sorted(s["days"])
        span = f'{days[0]} — {days[-1]}' if len(days) > 1 else (days[0] if days else "—")
        closed_chapters.append(f"""<div class="chapter" id="u{_esc(s["key"])}">
  <div class="rail"><div class="num" style="color:var(--dimink)">·</div>
    <div class="when">{_esc(span)}</div><div class="badge dead">closed</div>
    <div class="tally"><span class="dn">{s["n"]} fossils</span></div>
    <div class="when" style="margin-top:8px">universe {_esc(s["key"][:8])}</div></div>
  <div><div class="chead"><h2>A closed universe</h2>
    <p>Its dish is not archived — what survives is the fossil record: every
       lineage that ever died there, with its genome, kept on purpose.</p></div>
    <div class="block"><div class="bt">The fallen of {_esc(s["key"][:8])}</div>
      <div class="fallen"><div class="shelf">{shelf}</div></div></div></div></div>""")

    chapters = f"""<section id="chapters">
  <div class="kicker">The Chapters <b>· every era keeps its own shelf</b></div>
  <p class="sub">Dishes are snapshots, clips are filmstrips, births are certificates.
     Nothing is deleted on restart — a new era simply opens the next page of the ledger.</p>
  {cur_chapter}{''.join(closed_chapters)}
</section>"""

    # ── appendix: earlier files, by date, nothing hidden ──
    apps = "".join(
        f'<div class="app"><a href="{_esc(f["path"])}">{_esc(f["name"])}</a>'
        f'<div class="when">{_time.strftime("%Y-%m-%d %H:%M", _time.localtime(f["mtime"]))}'
        f'</div></div>' for f in earlier[:48])
    appendix = (f"""<section id="appendix"><div class="kicker">Appendix
<b>· earlier archives</b></div>
  <p class="sub">Files from before this era began. Their era attribution is not
     recorded, so they are listed by date instead of being shown under the wrong
     universe.</p>
  <div class="appendix">{apps}</div></section>""" if earlier else "")

    footer = f"""<footer>
  <div class="epi">“The dish is alive in silence — it speaks only when something is born.”</div>
  <div class="det">every dish re-runs <b>exactly</b> · deterministic by seed ·
    <b>127.0.0.1</b> only · <span style="white-space:nowrap">{_esc(title)}</span></div>
</footer>"""

    script = """<script>
/* the dish: server-parsed SGR grid -> pixel canvas */
(function(){
  const cv=document.getElementById('dish');if(!cv)return;
  const ctx=cv.getContext('2d');
  function drawDish(grid){
    const rows=grid.split('|');
    const cellW=Math.ceil(cv.width/rows[0].split(',').length);
    const cellH=Math.ceil(cv.height/rows.length);
    const tier={f:1,b:0.72,'7':0.48,'4':0.3};
    ctx.clearRect(0,0,cv.width,cv.height);
    rows.forEach((row,y)=>{
      row.split(',').forEach((hex,x)=>{
        const r=parseInt(hex.slice(0,2),16),g=parseInt(hex.slice(2,4),16),
              b=parseInt(hex.slice(4,6),16),a=tier[hex[6]]||0.3;
        ctx.fillStyle='rgba('+r+','+g+','+b+','+a+')';
        ctx.fillRect(x*cellW,y*cellH,Math.max(1,cellW-1),Math.max(1,cellH-1));
      });
    });
  }
  drawDish(cv.dataset.grid);
  /* a refresh asks the dish for its current tick; so does a slow poll —
     the page stays a live window on the dish while Hermes works */
  if(cv.dataset.live!==undefined){
    const askDish=()=>{
      fetch('/live/dish.json',{cache:'no-store'}).then(r=>r.ok?r.json():r.json().then(j=>Promise.reject(j)))
      .then(d=>{
        if(!d||!d.grid)return;
        cv.dataset.grid=d.grid;drawDish(d.grid);
        const t=document.getElementById('census-tick'),
              a=document.getElementById('census-alive');
        if(t&&d.tick!=null)t.textContent='tick '+d.tick;
        if(a&&d.alive!=null)a.textContent=d.alive+' alive';
      }).catch(e=>{console.warn('[vivarium] live dish:',e&&e.error||e)});
    };
    askDish();setInterval(askDish,4000);
  }
})();
/* search: filter the registry */
(function(){
  const q=document.getElementById('q');if(!q)return;
  const cards=[...document.querySelectorAll('.cert')];
  q.addEventListener('input',()=>{
    const v=q.value.trim().toLowerCase();
    cards.forEach(c=>c.classList.toggle('hide',!!v&&
      !c.dataset.search.toLowerCase().includes(v)));
  });
  document.addEventListener('keydown',e=>{
    if(e.key==='/'&&document.activeElement!==q){e.preventDefault();q.focus()}
  });
})();
/* clips: click opens the theater */
(function(){
  const d=document.getElementById('theater'),body=document.getElementById('theaterBody');
  document.querySelectorAll('.clip').forEach(c=>c.addEventListener('click',()=>{
    body.innerHTML='<div class="t">'+c.dataset.name+' — served from 127.0.0.1 only</div>'+
      '<video src="'+c.dataset.src+'" controls autoplay></video>';
    d.showModal();
  }));
  d.addEventListener('close',()=>{body.innerHTML=''});
})();
/* keyboard: walk the universes */
(function(){
  const anchors=[...document.querySelectorAll('[id^="u"]')];
  let i=0;
  document.addEventListener('keydown',e=>{
    if(document.activeElement&&(document.activeElement.tagName==='INPUT'))return;
    if(e.key==='ArrowRight'||e.key==='ArrowLeft'){
      i=Math.min(anchors.length-1,Math.max(0,i+(e.key==='ArrowRight'?1:-1)));
      anchors[i].scrollIntoView({block:'start'});
    }
  });
})();
</script>"""

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title><style>{css}</style></head><body><div class="wrap">
{head}{now}{chapters}{appendix}{footer}
</div><dialog id="theater"><div id="theaterBody"></div></dialog>{script}
</body></html>"""
