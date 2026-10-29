"""Build booklets: step-by-step instructions with a picture for every step.

A booklet is plain JSON, stored with the build, and renders to one
self-contained HTML page (no scripts, no external files). Each step has an
isometric SVG drawing: the parts added in that step in full colour,
everything placed before them faded, plus a callout of the parts to find.

Grid: x and y in studs, z in plates (a brick is 3 plates tall). BrickGPT's z
is in bricks, so its layers are multiplied by 3.

Standard library only.
"""

import html
import math

PLATES = {"brick": 3, "plate": 1, "tile": 1, "curved": 2, "slope": 2}  # height of each kind
STUD_KINDS = ("brick", "plate", "round")  # kinds with studs on top
SLOPE_LOW = 0.35  # height (plates) of a slope's low end

# Approximate colours for drawing, chosen by eye; one per vocabulary name.
HEX = {
    "white": "#f2f2ee", "black": "#2b2b2b", "light_bluish_gray": "#a3a8ab", "dark_bluish_gray": "#6b6e6c",
    "light_gray": "#9ea39f", "dark_gray": "#6e6d60", "red": "#c8261c", "dark_red": "#741816",
    "blue": "#1458b8", "dark_blue": "#173a66", "medium_blue": "#5c94d8", "dark_azure": "#1a8cc6",
    "medium_azure": "#3fb2c4", "sand_blue": "#6476a0", "yellow": "#f2cc3a", "bright_light_yellow": "#fbec5c",
    "orange": "#f88b1e", "bright_light_orange": "#f6bb44", "dark_orange": "#a6581a", "green": "#2a7a44",
    "dark_green": "#1d4634", "bright_green": "#50a04c", "lime": "#b8e21e", "sand_green": "#a2bcab",
    "olive_green": "#9a9a5e", "tan": "#e2cc9f", "dark_tan": "#958a74", "reddish_brown": "#5b2d17",
    "dark_brown": "#3a2410", "medium_nougat": "#ab7e58", "light_nougat": "#f4d6b4", "bright_pink": "#e6afc9",
    "dark_pink": "#c873a0", "magenta": "#923c7a", "medium_lavender": "#ac7bb9", "dark_purple": "#41388f",
    "pearl_gold": "#ab8136", "flat_silver": "#8b898a", "trans_clear": "#e8eef0", "trans_black": "#655f55",
    "trans_red": "#d03c30", "trans_orange": "#f0922a", "trans_yellow": "#f4ce3c", "trans_green": "#86b68e",
    "trans_bright_green": "#d7e3a8", "trans_light_blue": "#b0ecea", "trans_dark_blue": "#2034a0",
    "trans_neon_green": "#f2ee88", "unknown": "#b8b8b8",
}

STUD = 26.0  # pixels per stud in a step picture
COS, SIN = math.cos(math.pi / 6), 0.5
PLATE = 0.4  # plate height in studs (3.2 mm on an 8 mm stud pitch)


# --- parts and placements -----------------------------------------------------

def kind_of(part) -> str:
    shape = (part.get("shape") or "").lower()
    if "round" in shape:
        return "round"
    if part["family"] == "slope":
        return "curved" if "curved" in shape else "slope"
    if part["family"] in ("plate", "tile"):
        return part["family"]
    return "brick"


def label(part) -> str:
    """'orange 1x2 brick', 'lime 1x1 round plate'."""
    color = part["color"].replace("_", " ")
    shape = part.get("shape") or part["family"]
    if not part.get("size") or shape.startswith(part["size"]):  # "1x1 slope (cheese)" names its size
        return f"{color} {shape}"
    return f"{color} {part['size']} {shape}"


def place(part, at, along="x", down=None) -> dict:
    """One part on the grid. along: which axis the part's long side runs on.
    down: for slopes, the direction the slope falls towards (+x, -x, +y, -y)."""
    a, b = sorted(int(n) for n in part["size"].split("x"))
    lx, ly = (b, a) if along == "x" else (a, b)
    kind = kind_of(part)
    height = (3 if part["family"] == "brick" else 1) if kind == "round" else PLATES[kind]
    if kind in ("curved", "slope") and down is None:
        down = "+x" if along == "x" else "+y"
    return {"part": dict(part), "at": list(at), "dims": [lx, ly, height], "kind": kind, "down": down}


def parts_list(placements) -> list:
    """Distinct parts with quantities, in order of first use."""
    found = {}
    for p in placements:
        key = label(p["part"])
        if key not in found:
            found[key] = {"label": key, "part": p["part"], "qty": 0, "example": p}
        found[key]["qty"] += 1
    return list(found.values())


def booklet(title, subtitle, placements, steps, source, notes=()) -> dict:
    """steps: [(text, [placement indices added in this step])]."""
    return {
        "title": title, "subtitle": subtitle, "source": source, "notes": list(notes),
        "placements": placements,
        "parts": [{"label": p["label"], "part": p["part"], "qty": p["qty"]} for p in parts_list(placements)],
        "steps": [{"n": n, "text": text, "add": list(add),
                   "parts": [{"label": p["label"], "qty": p["qty"]}
                             for p in parts_list([placements[i] for i in add])]}
                  for n, (text, add) in enumerate(steps, 1)],
    }


# --- drawing --------------------------------------------------------------------

def _shade(hex_color, factor):
    """factor < 1 darkens, > 1 mixes towards white."""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    if factor <= 1:
        r, g, b = (round(c * factor) for c in (r, g, b))
    else:
        t = min(factor - 1, 1)
        r, g, b = (round(c + (255 - c) * t) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def _xy(x, y, z):
    return ((x - y) * COS * STUD, (x + y) * SIN * STUD - z * PLATE * STUD)


def _pts(points):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


def _height_fn(p):
    """Top height (plates) at a point (x, y) of a placement's footprint."""
    x0, y0, z0 = p["at"]
    lx, ly, h = p["dims"]
    if p["kind"] not in ("curved", "slope"):
        return lambda x, y: z0 + h
    axis, sign = p["down"][1], p["down"][0]
    length = lx if axis == "x" else ly

    def height(x, y):
        along = (x - x0) if axis == "x" else (y - y0)
        t = min(max(along if sign == "+" else length - along, 0), length) / length
        rise = math.cos(math.pi / 2 * t) if p["kind"] == "curved" else 1 - t
        return z0 + SLOPE_LOW + (h - SLOPE_LOW) * rise
    return height


def _columns(placements):
    """Every 1x1 stud column of every part, in drawing order (back to front)."""
    cols = []
    for i, p in enumerate(placements):
        x0, y0, z0 = p["at"]
        lx, ly, _ = p["dims"]
        for cx in range(x0, x0 + lx):
            for cy in range(y0, y0 + ly):
                cols.append((cx + cy, z0, cx, i))
    cols.sort()
    return cols


def _colors(p, faded):
    base = HEX.get(p["part"]["color"], HEX["unknown"])
    dark = sum(int(base[i:i + 2], 16) for i in (1, 3, 5)) < 200
    c = {"top": base, "left": _shade(base, 0.86), "right": _shade(base, 0.7),
         "edge": _shade(base, 1.45) if dark else _shade(base, 0.45)}
    if faded:
        c = {k: _shade(v, 1.62) for k, v in c.items()}
    return c


def _stud(out, cx, cy, z, c, radius=0.3, tall=0.42):
    (sx, sy) = _xy(cx + 0.5, cy + 0.5, z)
    (_, ty) = _xy(cx + 0.5, cy + 0.5, z + tall)
    rx, ry = radius * math.sqrt(2) * COS * STUD, radius * math.sqrt(2) * SIN * STUD
    out.append(f'<ellipse cx="{sx:.1f}" cy="{sy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{c["right"]}" stroke="{c["edge"]}" stroke-width="0.8"/>')
    out.append(f'<rect x="{sx - rx:.1f}" y="{ty:.1f}" width="{2 * rx:.1f}" height="{sy - ty:.1f}" fill="{c["left"]}"/>')
    out.append(f'<path d="M{sx - rx:.1f},{ty:.1f}V{sy:.1f}M{sx + rx:.1f},{ty:.1f}V{sy:.1f}" stroke="{c["edge"]}" stroke-width="0.8"/>')
    out.append(f'<ellipse cx="{sx:.1f}" cy="{ty:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{_shade(c["top"], 1.12)}" stroke="{c["edge"]}" stroke-width="0.8"/>')


def _cylinder(out, p, c):
    x0, y0, z0 = p["at"]
    top = z0 + p["dims"][2]
    _stud(out, x0, y0, z0, c, radius=0.47, tall=top - z0)
    _stud(out, x0, y0, top, c)


def _filled(placements, shown) -> set:
    """Plate cells (x, y, z) filled by the shown box-shaped parts: faces and
    studs behind them are never seen, so they are not drawn."""
    cells = set()
    for i in shown:
        p = placements[i]
        if p["kind"] in ("brick", "plate", "tile"):
            x0, y0, z0 = p["at"]
            lx, ly, h = p["dims"]
            cells.update((x, y, z) for x in range(x0, x0 + lx) for y in range(y0, y0 + ly)
                         for z in range(z0, z0 + h))
    return cells


def _column(out, p, cx, cy, c, height, filled):
    x0, y0, z0 = p["at"]
    lx, ly, h = p["dims"]
    x1, y1 = x0 + lx, y0 + ly
    span = range(z0, z0 + math.ceil(h))
    sloped = p["kind"] in ("curved", "slope")
    axis = p["down"][1] if sloped else None
    n_x = 7 if axis == "x" else 2  # samples along a side that runs along x
    n_y = 7 if axis == "y" else 2

    def side(ax, ay, bx, by, n):
        return [_xy(ax + (bx - ax) * k / (n - 1), ay + (by - ay) * k / (n - 1),
                    height(ax + (bx - ax) * k / (n - 1), ay + (by - ay) * k / (n - 1))) for k in range(n)]

    s_ny = side(cx, cy, cx + 1, cy, n_x)              # -y edge, along x
    s_px = side(cx + 1, cy, cx + 1, cy + 1, n_y)      # +x edge, along y
    s_py = side(cx + 1, cy + 1, cx, cy + 1, n_x)      # +y edge, along x
    s_nx = side(cx, cy + 1, cx, cy, n_y)              # -x edge, along y
    edge = f'stroke="{c["edge"]}" stroke-width="1.1" stroke-linejoin="round" fill="none"'
    if cx == x1 - 1 and not all((cx + 1, cy, z) in filled for z in span):  # right face
        poly = [_xy(cx + 1, cy, z0), _xy(cx + 1, cy + 1, z0)] + s_px[::-1]
        out.append(f'<polygon points="{_pts(poly)}" fill="{c["right"]}" stroke="{c["right"]}" stroke-width="1"/>')
        lines = [[_xy(cx + 1, cy, z0), _xy(cx + 1, cy + 1, z0)]]
        if cy == y0:
            lines.append([_xy(cx + 1, cy, z0), s_px[0]])
        if cy == y1 - 1:
            lines.append([_xy(cx + 1, cy + 1, z0), s_px[-1]])
        out.extend(f'<polyline points="{_pts(l)}" {edge}/>' for l in lines)
    if cy == y1 - 1 and not all((cx, cy + 1, z) in filled for z in span):  # left face
        poly = [_xy(cx, cy + 1, z0), _xy(cx + 1, cy + 1, z0)] + s_py
        out.append(f'<polygon points="{_pts(poly)}" fill="{c["left"]}" stroke="{c["left"]}" stroke-width="1"/>')
        lines = [[_xy(cx, cy + 1, z0), _xy(cx + 1, cy + 1, z0)]]
        if cx == x0:
            lines.append([_xy(cx, cy + 1, z0), s_py[-1]])
        out.extend(f'<polyline points="{_pts(l)}" {edge}/>' for l in lines)
    if not sloped and (cx, cy, z0 + h) in filled:
        return  # something sits on this column: its top and stud are hidden
    top = s_ny + s_px[1:] + s_py[1:] + s_nx[1:]
    out.append(f'<polygon points="{_pts(top)}" fill="{_shade(c["top"], 1.08) if sloped else c["top"]}" '
               f'stroke="{c["top"]}" stroke-width="1"/>')
    for keep, line in ((cy == y0, s_ny), (cx == x1 - 1, s_px), (cy == y1 - 1, s_py), (cx == x0, s_nx)):
        if keep:
            out.append(f'<polyline points="{_pts(line)}" {edge}/>')
    if p["kind"] in STUD_KINDS:
        _stud(out, cx, cy, z0 + h, c)


def _bounds(placements):
    xs, ys = [], []
    for p in placements:
        x0, y0, z0 = p["at"]
        lx, ly, h = p["dims"]
        for x in (x0, x0 + lx):
            for y in (y0, y0 + ly):
                for z in (z0, z0 + h + 0.5):
                    sx, sy = _xy(x, y, z)
                    xs.append(sx)
                    ys.append(sy)
    pad = STUD * 0.6
    return min(xs) - pad, min(ys) - pad, max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad


def picture(placements, new=(), shown=None, frame=None, max_width=None) -> str:
    """SVG of the placements in `shown` (default all). Parts in `new` are in
    full colour; the others are faded, unless `new` is empty (all full)."""
    shown = range(len(placements)) if shown is None else shown
    visible = set(shown)
    new = set(new)
    frame = frame or _bounds([placements[i] for i in visible])
    filled = _filled(placements, visible)
    out = []
    for diag, _, cx, i in _columns(placements):
        if i not in visible:
            continue
        p = placements[i]
        cy = diag - cx
        c = _colors(p, faded=bool(new) and i not in new)
        if p["kind"] == "round":
            _cylinder(out, p, c)
        else:
            _column(out, p, cx, cy, c, _height_fn(p), filled)
    x, y, w, h = frame
    width = f' width="{min(w, max_width):.0f}"' if max_width else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x:.1f} {y:.1f} {w:.1f} {h:.1f}"{width} '
            f'role="img">' + "".join(out) + "</svg>")


# --- the page ---------------------------------------------------------------------

PAGE_CSS = """
:root { --yellow: #ffd500; --ink: #1c1c1c; --muted: #6b6b6b; --line: #e4e0d5; --bg: #fbf8f1; }
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--ink); }
header { background: var(--yellow); padding: 18px 16px 14px; }
header h1 { margin: 0; font-size: 26px; }
header p { margin: 4px 0 0; color: #4d4300; font-size: 14px; }
main { padding: 16px; max-width: 720px; margin: 0 auto; }
.card { background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 16px; margin-bottom: 14px; break-inside: avoid; }
.card h2 { margin: 0 0 8px; font-size: 18px; }
.pic { text-align: center; }
.pic svg { max-width: 100%; height: auto; max-height: 52vh; }
.parts { display: flex; flex-wrap: wrap; gap: 8px; margin: 6px 0 10px; padding: 0; list-style: none; }
.parts li { display: flex; align-items: center; gap: 6px; border: 1px solid var(--line); border-radius: 10px; padding: 4px 8px 4px 4px; font-size: 14px; }
.parts svg { width: 46px; height: 40px; }
.parts b { font-size: 16px; }
.step { display: grid; grid-template-columns: 48px 1fr; gap: 4px 12px; }
.step .num { font-size: 34px; font-weight: 800; line-height: 1; }
.step .body { min-width: 0; }
.step p { margin: 8px 0 0; font-size: 16px; line-height: 1.4; }
.note { color: var(--muted); font-size: 13px; line-height: 1.45; margin: 6px 0 0; }
footer { text-align: center; color: var(--muted); font-size: 12px; padding: 8px 16px 24px; }
@media print { body { background: #fff; } .card { border-color: #ccc; } }
"""


def _parts_html(placements, parts) -> str:
    items = []
    for part in parts:
        example = next(p for p in placements if label(p["part"]) == part["label"])
        solo = dict(example, at=[0, 0, 0])
        items.append(f'<li>{picture([solo])}<span><b>{part["qty"]}×</b> {html.escape(part["label"])}</span></li>')
    return '<ul class="parts">' + "".join(items) + "</ul>"


def render_checklist(drafts) -> str:
    """The draft piece lists as one printable page for a hand-check at the
    table: unsure lines first and highlighted, a swatch per colour."""
    css = PAGE_CSS + """
.draft h2 { display: flex; justify-content: space-between; gap: 8px; }
.draft .state { font-size: 12px; font-weight: 600; padding: 3px 8px; border-radius: 9px; background: #fff1c2; }
.draft .state.done { background: #dff1e6; color: #1f8a4c; }
.draft table { border-collapse: collapse; width: 100%; font-size: 14px; }
.draft td { padding: 5px 4px; border-top: 1px solid var(--line); vertical-align: top; }
.draft td.box { width: 22px; } .draft td.qty { width: 34px; font-weight: 700; text-align: right; }
.draft tr.unsure { background: #fff6d8; } .draft .why { color: #8a5a00; font-size: 12px; display: block; }
.sw { display: inline-block; width: 12px; height: 12px; border-radius: 3px; border: 1px solid rgba(0,0,0,.3); margin-right: 6px; vertical-align: -1px; }
"""
    waiting = sum(not d["hand_check"]["done"] for d in drafts)
    out = ["<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">",
           "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
           f"<title>Manual hand-check · BinBuild</title><style>{css}</style></head><body>",
           "<header><h1>✅ Manual hand-check</h1>"
           f"<p>{len(drafts)} draft piece lists read from the book · {waiting} waiting for a check</p></header><main>",
           '<section class="card"><p class="note">For each build: lay these pieces out from the kit next to its page '
           "and build the model once. Tick each line; fix a count or a colour that's wrong. Highlighted lines were "
           "hard to read in the photo. Then record it: <code>python -m backend.manual_check &lt;id&gt; --done --by "
           "NAME</code> (use <code>--set</code> and <code>--sure</code> for fixes).</p></section>"]
    for d in drafts:
        done = d["hand_check"]["done"]
        out.append(f'<section class="card draft"><h2><span>{html.escape(d["name"])} '
                   f'<small>· pages {", ".join(map(str, d["pages"]))}</small></span>'
                   f'<span class="state{" done" if done else ""}">{"hand-checked" if done else "draft"}</span></h2>'
                   f'<p class="note">{html.escape(d["id"])} · {d["elements_total"]} elements · '
                   f'{d["unsure_elements"]} unsure · from {html.escape(d["read_from"])}</p><table>')
        for e in sorted(d["elements"], key=lambda e: e["sure"]):
            why = f'<span class="why">unsure: {html.escape(e["doubt"] or "")}</span>' if not e["sure"] else ""
            out.append(f'<tr class="{"" if e["sure"] else "unsure"}"><td class="box">☐</td>'
                       f'<td class="qty">{e["qty"]}×</td><td><span class="sw" style="background:'
                       f'{HEX.get(e["color"], HEX["unknown"])}"></span>{html.escape(label(e))}{why}</td></tr>')
        out.append("</table></section>")
    out.append("</main><footer>BinBuild · Not affiliated with the LEGO Group.</footer></body></html>")
    return "".join(out)


def render_html(book) -> str:
    """The booklet as one self-contained HTML page."""
    placements = book["placements"]
    frame = _bounds(placements)
    total = sum(p["qty"] for p in book["parts"])
    out = [
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
        f"<title>{html.escape(book['title'])} · BinBuild booklet</title><style>{PAGE_CSS}</style></head><body>",
        f"<header><h1>🧱 {html.escape(book['title'])}</h1><p>{html.escape(book['subtitle'])}</p></header><main>",
        '<section class="card"><h2>What you will build</h2>',
        f'<div class="pic">{picture(placements, frame=frame)}</div>',
        f"<h2>Find these {total} pieces</h2>{_parts_html(placements, book['parts'])}",
    ]
    out += [f'<p class="note">{html.escape(n)}</p>' for n in book.get("notes", ())]
    out.append("</section>")
    placed = []
    for step in book["steps"]:
        placed += step["add"]
        out.append(
            f'<section class="card step"><div class="num">{step["n"]}</div><div class="body">'
            f'{_parts_html(placements, step["parts"])}'
            f'<div class="pic">{picture(placements, new=step["add"], shown=placed, frame=frame)}</div>'
            f'<p>{html.escape(step["text"])}</p></div></section>')
    out.append('<section class="card"><h2>🎉 Done!</h2>'
               f'<p class="note">{len(book["steps"])} steps, {total} pieces. '
               f'Made by BinBuild from {html.escape(book["source"])}.</p></section>')
    out.append("</main><footer>BinBuild · Not affiliated with the LEGO Group.</footer></body></html>")
    return "".join(out)
