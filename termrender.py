"""VIV-28b: terminal-graphics rendering + the localhost gallery.

Delivery ladder (first supported wins):
  1. kitty          — PNG via the kitty graphics protocol (APC escapes)
  2. iTerm2         — PNG via OSC 1337 (single-shot, no chunking)
  3. sixel          — PNG via sixel escape (writer included, basic palette)
  4. plain terminal — nothing emitted; caller shows the ASCII/rich dish
  5. /vivarium serve— localhost-only gallery in the browser (the universal
                      graphics terminal)

Hard rules (from references/termrender.md):
- OPT-IN only: `emit_image()` never runs unless the caller explicitly asked
  for graphics (`--image` / rich=true+image). Auto-emitted escapes print
  garbage in non-supporting terminals and log captures.
- Capability detection is conservative: env vars + opt-in; when unsure,
  fall back (ASCII + file path is always correct).
- The gallery binds 127.0.0.1 ONLY — it displays the user's dish.
- No plugin-state writes anywhere in this module; reads media/ only. Safe
  while the universe is dormant.

This module is state-free and import-safe in both package and flat modes
(dual-mode header, no lazy sibling imports).
"""

from __future__ import annotations

import base64
import os
import shutil
import sys
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Optional, Tuple

try:  # package mode (Hermes plugin)
    from . import world as W
except ImportError:  # flat mode (tests)
    import world as W

CHUNK = 4096          # kitty protocol: base64 chunks of 4096 bytes


# ── capability detection ─────────────────────────────────────────────────────
def detect_graphics(env: Optional[dict] = None) -> str:
    """Return 'kitty' | 'iterm2' | 'sixel' | 'none'.

    Conservative by design: env evidence only, no terminal queries (which
    can hang pipes). Callers may override with force= for tests.
    """
    env = dict(os.environ if env is None else env)
    term = env.get("TERM", "")
    if env.get("KITTY_WINDOW_ID") or "kitty" in term:
        return "kitty"
    if env.get("ITERM_SESSION_ID") or env.get("TERM_PROGRAM") == "iTerm.app":
        return "iterm2"
    # sixel-capable terminals commonly announce themselves
    if "sixel" in term or env.get("TERM_PROGRAM") in ("WezTerm",) \
            or "foot" in term:
        return "sixel"
    return "none"


# ── escape emitters (byte-exact, verified) ───────────────────────────────────
def _kitty_escape(png: bytes, img_id: int = 1) -> bytes:
    """PNG → kitty APC escape, chunked at 4096 b64 bytes.

    ESC _ G f=100,a=T,I=<id>,m=<1|0>,q=2 ; <b64> ESC \\
    Continuation chunks carry ONLY m. The payload may contain ';' — never
    split on it.
    """
    b64 = base64.b64encode(png).decode()
    first, rest = b64[:CHUNK], b64[CHUNK:]
    out = [f"\x1b_Gf=100,a=T,I={img_id},m={1 if rest else 0},q=2,C=1;{first}\x1b\\".encode()]
    while rest:
        chunk, rest = rest[:CHUNK], rest[CHUNK:]
        out.append(f"\x1b_Gm={1 if rest else 0};{chunk}\x1b\\".encode())
    return b"".join(out)


def _iterm2_escape(png: bytes, name: str = "vivarium.png") -> bytes:
    """PNG → iTerm2 OSC 1337 (single-shot; inline=1 displays it)."""
    b64 = base64.b64encode(png).decode()
    return (f"\x1b]1337;File=name={name};size={len(png)};inline=1;"
            f"preserveAspectRatio=1:{b64}\x1b\\".encode())


def _sixel_escape(png: bytes) -> bytes:
    """PNG → sixel via a minimal decoder: DCS with a 16-color quantization.

    Real sixel needs raster attributes + color palette + band data. Rather
    than half-support it, this decodes the PNG's raw pixels (via the same
    minimal zlib reader artifacts.py uses) and emits true sixel bands.
    Falls back to b'' on any decode trouble — callers then use the path.
    """
    try:
        pixels, size = _decode_png(png)
    except Exception:
        return b""
    w, h = size
    # quantize to a small palette (greys + primaries), 4x4 dither-free
    palette, index = _quantize(pixels, w, h)
    out = bytearray()
    out += b"\x1bP0;1;0q"                      # DCS, raster mode
    out += f'"1;1;{w};{h}'.encode() + b"$"     # raster attributes
    # color definitions
    for i, (r, g, b) in enumerate(palette):
        out += f"#{i};2;{r*100//255};{g*100//255};{b*100//255}".encode() + b"$"
    # sixel bands: 6 pixel rows per band; simple, correct, unoptimized
    for band_top in range(0, h, 6):
        band = bytearray()
        band_colors = set()
        for x in range(w):
            for dy in range(6):
                y = band_top + dy
                if y < h:
                    band_colors.add(index[y * w + x])
        for ci in sorted(band_colors):
            band += f"#{ci}".encode()
            for x in range(w):
                mask = 0
                for dy in range(6):
                    y = band_top + dy
                    if y < h and index[y * w + x] == ci:
                        mask |= 1 << dy
                band += (chr(63 + mask) if mask else "").encode()
            band += b"$"
        band += b"-"
        out += band
    out += b"\x1b\\"
    return bytes(out)


# ── minimal PNG decode (for sixel; mirrors artifacts.py's writer) ───────────
def _decode_png(png: bytes) -> Tuple[list, Tuple[int, int]]:
    """Decode the subset of PNG that artifacts.write_png produces (truecolor,
    single IDAT, zlib). Returns (pixel_list_rowmajor, (w, h))."""
    import struct, zlib
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    pos = 8
    w = h = 0
    idat = b""
    while pos < len(png):
        (ln,) = struct.unpack(">I", png[pos:pos + 4])
        typ = png[pos + 4:pos + 8]
        data = png[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h = struct.unpack(">II", data[:8])
        elif typ == b"IDAT":
            idat += data
        pos += 12 + ln
    raw = zlib.decompress(idat)
    stride = 1 + w * 3          # filter byte + RGB
    pixels = []
    for y in range(h):
        row = raw[y * stride:(y + 1) * stride]
        assert row[0] == 0, "only filter 0 (none) is produced by write_png"
        px = row[1:]
        for x in range(w):
            pixels.append((px[x * 3], px[x * 3 + 1], px[x * 3 + 2]))
    return pixels, (w, h)


def _quantize(pixels, w, h):
    """Map pixels to a fixed 8-color palette; returns (palette, index list).

    Palette: black, white, red, green, blue, yellow, magenta, cyan — the
    sixel classics. -1 index = transparent/black (unused cell)."""
    pal = [(0, 0, 0), (255, 255, 255), (255, 0, 0), (0, 255, 0),
           (0, 0, 255), (255, 255, 0), (255, 0, 255), (0, 255, 255)]
    idx = []
    for (r, g, b) in pixels:
        best, bd = 0, 1 << 30
        for i, (pr, pg, pb) in enumerate(pal):
            d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
            if d < bd:
                best, bd = i, d
        idx.append(best)
    return pal, idx


# ── public API ───────────────────────────────────────────────────────────────
def emit_image(png_path: str, env: Optional[dict] = None,
               force: Optional[str] = None) -> str:
    """Emit a graphics-protocol escape for a PNG file, if the terminal can.

    GUARD (learned from the user's kitty test): escapes are only legal when
    THIS process owns the displaying tty — a local CLI session. In a
    gateway/relay context (chat platforms, piped output, no tty) the bytes
    cannot reach the screen and surface as mojibake in the message instead;
    there we return 'attached <path>' and let the gateway deliver the PNG
    natively as a chat attachment.
    """
    try:
        png = Path(png_path).read_bytes()
    except OSError as e:
        return f"could not read {png_path}: {e}"
    kind = force or detect_graphics(env)
    # NEVER write raw escapes from inside a tool: tool results travel the
    # message pipeline (gateway -> relay -> chat), where control bytes are
    # not graphics but mojibake (user's kitty paste proved it: the escape
    # payload arrived as visible text). Tools return 'attached <path>' and
    # the gateway delivers the PNG natively.
    # Escape emission is reserved for emit_image_raw() — callers that KNOW
    # they are attached to the displaying terminal (interactive CLI paths).
    return f"attached {png_path}"


def emit_image_raw(png_path: str, env: Optional[dict] = None,
                   force: Optional[str] = None) -> str:
    """Interactive-only: write graphics escapes to stdout directly.

    ONLY for processes that own the displaying terminal (a standalone
    script or CLI run inside the target terminal). Never call from a
    plugin tool — tool output travels the message pipeline.
    """
    kind = force or detect_graphics(env)
    try:
        png = Path(png_path).read_bytes()
    except OSError as e:
        return f"could not read {png_path}: {e}"
    payload = None
    if kind == "kitty":
        payload = _kitty_escape(png).decode("latin-1")
    elif kind == "iterm2":
        payload = _iterm2_escape(png).decode("latin-1")
    elif kind == "sixel":
        payload = _sixel_escape(png).decode("latin-1")
        if not payload:
            return f"saved to {png_path}"
    else:
        return f"saved to {png_path}"
    # VIV-39: reserve the image's rows. Without this the terminal keeps
    # printing (reasoning box, reply, tool-result line) on the cells the
    # image covers -> the dish lands ON TOP of the text. Move the cursor
    # down by the image height in text rows so everything after flows
    # below the picture.
    try:
        h = png_size(png_path)[1]
        rows = max(1, -(-int(h) // max(1, CELL_H)))   # ceil
        # Same idea as the /vivarium status overlay, in the one channel
        # this tool owns: reserve the rectangle, then paint into it.
        # ESC7 save, real newlines reserve the block (scrolling if at
        # the bottom), ESC8 restore to the block's top, image, then move
        # the cursor to the block's bottom so later text flows below.
        payload = ("\x1b7" + "\n" * rows + "\x1b8"
                   + payload + f"\x1b[{rows}B")
    except Exception:
        pass
    # Write to the RAW terminal device when possible: the Hermes TUI wraps
    # stdout (prompt_toolkit patch_stdout -> rich), which re-encodes ANSI
    # and mangles APC into visible text (user's kitty paste). /dev/tty
    # bypasses the wrapper so the terminal itself sees the bytes.
    try:
        tty = os.open("/dev/tty", os.O_WRONLY)
        try:
            os.write(tty, payload.encode("latin-1"))
        finally:
            os.close(tty)
    except OSError:
        sys.stdout.write(payload)      # plain terminal: stdout IS the tty
        sys.stdout.flush()
    return f"{kind} graphics emitted"



# ── localhost gallery ────────────────────────────────────────────────────────
def _gallery_html(entries: list, dish_map: str, title: str) -> str:
    """One static page: the ASCII dish up top, then artifact cards."""
    cards = []
    for e in entries:
        rel = e["file"]
        if rel.endswith(".mp4"):
            cards.append(
                f'<div class="card"><video controls src="{rel}"></video>'
                f'<p>{e.get("caption", "")}</p></div>')
        else:
            cards.append(
                f'<div class="card"><img src="{rel}" alt="{e.get("caption", "")}">'
                f'<p>{e.get("caption", "")}</p></div>')
    dish_lines = "\n".join(
        f'<div class="row">{line.replace(" ", "&nbsp;")}</div>'
        for line in dish_map.splitlines())
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{title}</title><style>
body{{background:#0b1210;color:#cfe8d8;font-family:monospace;margin:24px}}
h1{{font-size:1.2em}} .dish{{background:#060a08;padding:12px;border-radius:8px;
white-space:pre;font-size:11px;line-height:1.0;display:inline-block}}
.row{{height:11px}}
.grid{{display:flex;flex-wrap:wrap;gap:16px;margin-top:24px}}
.card{{background:#101a15;border:1px solid #1e3529;border-radius:8px;padding:10px;width:280px}}
.card img{{width:256px;image-rendering:pixelated}}
.card video{{width:256px}}
p{{font-size:0.8em;color:#9fc4ac;margin:6px 0 0}}
</style></head><body>
<h1>🌌 {title}</h1>
<div class="dish">{dish_lines}</div>
<div class="grid">{''.join(cards)}</div>
</body></html>"""


def serve_gallery(media_dir: str, dish_map: str = "",
                  title: str = "The Vivarium",
                  port: int = 0, keep: bool = False,
                  open_browser: bool = True) -> dict:
    """Serve the media dir + dish on 127.0.0.1:<port> (ephemeral by default).

    Returns {url, port, thread}. The server dies when the process exits
    unless keep=True (a deliberate daemon). Binds localhost ONLY.
    """
    media = Path(media_dir)
    if not media.is_dir():
        return {"error": f"no media directory at {media_dir}"}
    # build the index over existing artifacts (no new renders, no state)
    entries = []
    for p in sorted(media.glob("*")):
        if p.suffix in (".png", ".mp4") and p.name != "index.html":
            caption = p.stem.replace("_", " ").replace("-", " ")
            entries.append({"file": p.name, "caption": caption})
    html = _gallery_html(entries, dish_map, title)
    (media / "index.html").write_text(html, encoding="utf-8")

    class _H(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(media), **kw)

        def log_message(self, format, *args):    # silence request logging
            pass

    httpd = HTTPServer(("127.0.0.1", port), _H)
    actual = httpd.server_address[1]
    url = f"http://127.0.0.1:{actual}"
    t = threading.Thread(target=httpd.serve_forever, daemon=not keep)
    t.start()
    if open_browser:
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass
    return {"url": url, "port": actual, "thread": t, "server": httpd}


def png_size(png_path: str):
    """(width, height) from a PNG's IHDR — no dependencies."""
    with open(png_path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None
    import struct
    w, h = struct.unpack(">II", head[16:24])
    return int(w), int(h)


# terminal cell size estimate in pixels (kitty defaults ~10x20; a bad
# estimate only shifts the overlay slightly — the ASCII fallback lives
# underneath and the image hides it)
# Calibrated by direct user measurement (2026-11-06): the 339px dish
# occupies 23 terminal lines => cell height ≈ 15px (339/23). Previous
# estimates: 20px (assumed), 11px (over-corrected from a 13-row gap).
CELL_W, CELL_H = 10, 15


def paint_over(png_path: str, reserved_rows: int, trail_rows: int,
               delay: float = 0.6, env: Optional[dict] = None,
               extra_climb: int = 3) -> str:
    """Deferred overlay paint: the TUI prints `reserved_rows` blank rows
    (part of the slash text, so its redraw engine owns/scrolls them);
    `delay` seconds later this paints the PNG on top of that rectangle
    via /dev/tty. No fallback content: if the paint fails the rows stay
    blank (whitespace is the fallback — clean and harmless).

    `trail_rows` = text lines printed AFTER the reserved rows (path +
    note) — the cursor-relative dance must climb over them too.
    """
    import threading
    import time as _t

    def _work():
        _t.sleep(delay)
        size = png_size(png_path)
        try:
            fd = os.open("/dev/tty", os.O_WRONLY)
        except OSError:
            return ""   # silent: no tty -> whitespace fallback
        try:
            # The TUI adds rows after our text (blank line + prompt) that the
            # static count can't see — measured 2-3 on the live TUI. Climb
            # those too, or the image lands low and covers the path line.
            up = reserved_rows + trail_rows + max(0, extra_climb)
            payload = (f"\x1b[{up}A".encode()          # cursor up to overlay top
                       + _kitty_escape(open(png_path, "rb").read())
                       + f"\x1b[{up}B".encode())        # restore cursor
            os.write(fd, payload)
            return ""
        except Exception:
            return ""   # silent: whitespace is the fallback
        finally:
            os.close(fd)

    t = threading.Thread(target=_work, daemon=True)
    t.start()
    return ""   # silent: diagnostics never print (VIV-36b)
