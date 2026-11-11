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
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Optional, Tuple

try:  # package mode (Hermes plugin)
    from . import world as W
except ImportError:  # flat mode (tests)
    import world as W

CHUNK = 4096          # kitty protocol: base64 chunks of 4096 bytes


# ── capability detection ─────────────────────────────────────────────────────
def _classify_env(env: dict) -> str:
    """Classify one env mapping: 'kitty' | 'iterm2' | 'sixel' | 'none'."""
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


def _proc_environ(pid: int) -> dict:
    """Read one /proc environ (NUL-separated; same-UID processes only)."""
    from pathlib import Path
    try:
        raw = Path(f"/proc/{int(pid)}/environ").read_bytes()
    except (OSError, ValueError):
        return {}
    out: dict[str, str] = {}
    for chunk in raw.split(b"\0"):
        if not chunk or b"=" not in chunk:
            continue
        k, _, v = chunk.partition(b"=")
        out[k.decode("utf-8", "replace")] = v.decode("utf-8", "replace")
    return out


def _parent_pid(pid: int) -> int:
    """PPID from /proc/<pid>/stat. comm may contain spaces, so parse the
    numeric fields AFTER the closing paren: [0]=state, [1]=ppid."""
    from pathlib import Path
    try:
        stat = Path(f"/proc/{int(pid)}/stat").read_text("utf-8", "replace")
        fields = stat[stat.rfind(")") + 2:].split()
        return int(fields[1])
    except (OSError, ValueError, IndexError):
        return 0


def _detect_from_ancestors(max_up: int = 2, environ_of=_proc_environ,
                           parent_of=_parent_pid, has_ctty=None) -> str:
    """VIV-77: capability from the SURFACE, not the (stripped) child env.

    Terminal children are spawned with a deliberately scrubbed env (the TUI
    slash worker: served_profile_child_env strips TERMINAL_*/KITTY_*), so
    os.environ-based detection sees nothing even when the user sits in a
    real kitty. The terminal identity survives in the nearest ancestor that
    kept it (worker -> TUI), readable from /proc/<pid>/environ. VIV-77b:
    the worker is ALSO spawned start_new_session=True, so it owns no
    controlling terminal — a ctty is no longer required to trust the walk
    (a detached gateway's ancestors simply have no terminal env either,
    and every paint path re-verifies a writable tty before emitting).
    max_up=2 covers worker -> TUI -> shell; explicit has_ctty=True/False
    stays injectable for tests.
    """
    if has_ctty is False:
        return "none"
    pid = parent_of(os.getpid())
    for _ in range(max_up):
        if pid <= 1:
            break
        res = _classify_env(environ_of(pid))
        if res != "none":
            return res
        pid = parent_of(pid)
    return "none"


def detect_graphics(env: Optional[dict] = None) -> str:
    """Return 'kitty' | 'iterm2' | 'sixel' | 'none'.

    Conservative by design: env evidence only, no terminal queries (which
    can hang pipes). Callers may override with force= for tests.
    VIV-77: with no explicit env, a child whose own environment was
    scrubbed (TUI slash worker) falls back to the nearest ancestor that
    still has terminal env — the paint surface (/dev/tty) is shared with
    that ancestor, so its identity is the honest one.
    """
    own = dict(os.environ if env is None else env)
    res = _classify_env(own)
    if res != "none":
        return res
    if env is None:            # live detection only; explicit envs stay pure
        return _detect_from_ancestors()
    return "none"


def explain_graphics() -> str:
    """VIV-77b diagnostic trace for /vivarium doctor: how the live answer
    was reached, so a paste can never be ambiguous again. Format:
    'own=none walk=kitty@4242 atty=/dev/pts/1' (walk=kitty means the
    ancestor walk found the terminal identity; atty= the paint device
    found among the ancestors' fds)."""
    own = dict(os.environ)
    own_term = own.get("TERM") or "-"
    own_res = _classify_env(own)
    walk = "off" if own_res != "none" else _detect_from_ancestors()
    walk_pid = ""
    if walk != "none":
        pid = _parent_pid(os.getpid())
        for _ in range(2):
            if pid <= 1:
                break
            if _classify_env(_proc_environ(pid)) != "none":
                walk_pid = f"@{pid}"
                break
            pid = _parent_pid(pid)
    atty = _ancestor_tty_path() or "-"
    return f"own={own_res}(TERM={own_term}) walk={walk}{walk_pid} atty={atty}"


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


def overlay_bytes(png_path: str, climb: int, env: Optional[dict] = None) -> bytes:
    """Save cursor, climb, emit the picture, restore — as one byte string.

    Used when the text and the picture must leave in a single write. The
    deferred paint_over path cannot be used there: writing the card to
    /dev/tty means prompt_toolkit never learns those rows exist, so a
    later paint measured against the cursor lands wherever the renderer
    left it — which is how the dish went missing.
    """
    kind = detect_graphics(env)
    try:
        with open(png_path, "rb") as fh:
            data = fh.read()
    except OSError:
        return b""
    if kind == "kitty":
        esc = _kitty_escape(data)
    elif kind == "iterm2":
        esc = _iterm2_escape(data)
    elif kind == "sixel":
        esc = _sixel_escape(data)
    else:
        return b""
    up = max(0, int(climb))
    move = f"\x1b[{up}A".encode() if up else b""
    return b"\x1b7" + move + esc + b"\x1b8"


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
    # VIV-77b: a session-less worker has no ctty — fall back to the
    # ancestor's pty device; NEVER dump escapes into a non-tty stdout
    # (that pipe may be a JSON protocol, where they are corruption).
    tty = _open_paint_tty()
    if tty is not None:
        try:
            os.write(tty, payload.encode("latin-1"))
        finally:
            os.close(tty)
    else:
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
                  open_browser: bool = True, html: "str | None" = None,
                  dish_provider=None) -> dict:
    """Serve the media dir + dish on 127.0.0.1:<port> (ephemeral by default).

    Returns {url, port, thread}. The server dies when the process exits
    unless keep=True (a deliberate daemon). Binds localhost ONLY.
    `html` (VIV-89): a full page from gallery.build_page — when given it
    REPLACES the flat index; the caller owns all data gathering.
    `dish_provider` (VIV-90): a callable returning
    {"tick", "alive", "grid"} — served fresh at /live/dish.json on every
    request, so a page refresh asks the dish for its CURRENT tick. It may
    accept fresh=False (VIV-98): with fresh=1 the provider must NOT fall
    back to a cached frame — a failed render surfaces as 503, because a
    status request exists to bring the truth. The provider runs inside
    the caller's process (it sees the live dish); any failure answers
    503 and the page keeps its last dish.
    """
    media = Path(media_dir)
    if not media.is_dir():
        return {"error": f"no media directory at {media_dir}"}
    if html is None:
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

        def do_GET(self):
            if dish_provider is not None and \
                    self.path.split("?")[0] in ("/live/dish.json", "/live/dish"):
                try:
                    import json as _json
                    fresh = "fresh=1" in self.path
                    try:
                        body = _json.dumps(dish_provider(fresh=fresh)).encode("utf-8")
                    except TypeError:      # a provider that takes no args
                        body = _json.dumps(dish_provider()).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except Exception as exc:
                    import json as _json
                    body = _json.dumps({"error": f"{type(exc).__name__}: {exc}"}).encode("utf-8")
                    self.send_response(503)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                return
            super().do_GET()

    httpd = ThreadingHTTPServer(("127.0.0.1", port), _H)
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


def _ancestor_tty_path(max_up: int = 2, parent_of=_parent_pid,
                       fds_of=None, readlink_of=None) -> str:
    """VIV-77b: the paint surface when this process owns no ctty.

    The slash worker is spawned start_new_session=True with piped stdio, so
    /dev/tty is gone — but its ancestors (the TUI) still sit on the user's
    pty. Find a tty device among the ancestors' open fds and return its
    path; opening the same pty device lands the bytes on the user's screen.
    Same-UID /proc read, guarded throughout; fds_of/readlink_of injectable
    for tests.
    """
    from pathlib import Path
    pid = parent_of(os.getpid())
    for _ in range(max_up):
        if pid <= 1:
            break
        try:
            entries = fds_of(pid) if fds_of else Path(f"/proc/{pid}/fd").iterdir()
            for entry in entries:
                try:
                    target = (readlink_of(entry) if readlink_of
                              else os.readlink(entry))
                except OSError:
                    continue
                if target.startswith("/dev/pts/") or target == "/dev/tty":
                    return target
        except OSError:
            pass
        pid = parent_of(pid)
    return ""


def _open_paint_tty():
    """A writable fd for the paint surface: own ctty first, then the
    ancestor's pty device (VIV-77b). None when no surface is reachable."""
    try:
        return os.open("/dev/tty", os.O_WRONLY)
    except OSError:
        pass
    path = _ancestor_tty_path()
    if not path:
        return None
    try:
        return os.open(path, os.O_WRONLY)
    except OSError:
        return None


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
        fd = _open_paint_tty()
        if fd is None:
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
