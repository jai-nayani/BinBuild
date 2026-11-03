"""Build booklets: step-by-step instructions with a picture for every step.

A booklet is plain JSON, stored with the build, and renders to one
self-contained HTML page (no scripts, no external files). Each step has a
picture drawn from the real part shapes (LDraw, see ldraw_render): the parts
added in that step in full colour, everything placed before them faded, plus
a callout of the parts to find.

Grid: x and y in studs, z in plates (a brick is 3 plates tall). BrickGPT's z
is in bricks, so its layers are multiplied by 3.
"""

import base64
import html
import json
from functools import lru_cache

PLATES = {"brick": 3, "plate": 1, "tile": 1, "curved": 2, "slope": 2, "wedge": 1}  # height of each kind
# Curved slopes are not all the same piece: the azure 1x2 (LDraw 6091) stands
# 4 plates tall with a stud on its flat end, the 1x3 (50950) is a brick tall.
CURVED_HEIGHTS = {("1x2", "medium_azure"): 4, ("1x3", None): 3}

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


# --- parts and placements -----------------------------------------------------

def kind_of(part) -> str:
    shape = (part.get("shape") or "").lower()
    if "round" in shape:
        return "round"
    if "wedge" in shape:
        return "wedge"
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


def place(part, at, along="x", down=None, studs=None, clip=None, narrow=None, side=None) -> dict:
    """One part on the grid. along: which axis the part's long side runs on.
    down: for slopes, the direction the slope falls towards (+x, -x, +y, -y).
    studs: for a wedge plate or the tile with studs on one edge, the edge that
    carries the studs; the wedge's surface falls away from that edge, and only
    that edge's cells get studs. clip: the end a clip plate's clip sticks out of.
    Drawing only, not part of the validated design: narrow, the end a wedge
    plate tapers to (which of the two mirror-image wedges it is); side, the way
    a brick's side studs face."""
    a, b = sorted(int(n) for n in part["size"].split("x"))
    lx, ly = (b, a) if along == "x" else (a, b)
    kind = kind_of(part)
    height = (3 if part["family"] == "brick" else 1) if kind == "round" else PLATES[kind]
    if kind == "curved":
        height = CURVED_HEIGHTS.get((part["size"], part["color"]),
                                    CURVED_HEIGHTS.get((part["size"], None), height))
    if kind in ("curved", "slope") and down is None:
        down = "+x" if along == "x" else "+y"
    if kind == "wedge" and studs and down is None:
        down = ("-" if studs[0] == "+" else "+") + studs[1]  # falls away from the studded edge
    out = {"part": dict(part), "at": list(at), "dims": [lx, ly, height], "kind": kind,
           "down": down, "studs": studs}
    out.update({k: v for k, v in (("clip", clip), ("narrow", narrow), ("side", side)) if v})
    return out


def parts_list(placements) -> list:
    """Distinct parts with quantities, in order of first use."""
    found = {}
    for p in placements:
        key = label(p["part"])
        if key not in found:
            found[key] = {"label": key, "part": p["part"], "qty": 0, "example": p}
        found[key]["qty"] += 1
    return list(found.values())


def booklet(title, subtitle, placements, steps, source, notes=(), view=None) -> dict:
    """steps: [(text, [placement indices added in this step])]. view: the
    camera for its pictures (ldraw_render), as the book shows the model."""
    return {
        "title": title, "subtitle": subtitle, "source": source, "notes": list(notes),
        **({"view": view} if view else {}),
        "placements": placements,
        "parts": [{"label": p["label"], "part": p["part"], "qty": p["qty"]} for p in parts_list(placements)],
        "steps": [{"n": n, "text": text, "add": list(add),
                   "parts": [{"label": p["label"], "qty": p["qty"]}
                             for p in parts_list([placements[i] for i in add])]}
                  for n, (text, add) in enumerate(steps, 1)],
    }


# --- drawing --------------------------------------------------------------------

PICTURE = (720, 540)   # largest picture, in pixels (shown at about half that: sharp on phones)
THUMB = (138, 120)     # a part in a parts list


@lru_cache(maxsize=512)
def _png(key) -> tuple:
    from . import ldraw_render as lr
    placements, new, shown, frame, view, size = json.loads(key)
    img = lr.render(placements, shown=shown, new=new, frame=frame, view=view, size=tuple(size))
    return lr.png(img), img.size


def picture(placements, new=(), shown=None, frame=None, view=None, size=PICTURE) -> str:
    """The placements in `shown` (default all), drawn from their real part
    shapes (backend/ldraw_render.py), as an SVG holding one PNG. Parts in
    `new` are in full colour; the others are faded, unless `new` is empty
    (all full). frame: ldraw_render.bounds() of the whole model, so a
    booklet's steps share one framing. view: the camera ({"yaw", "elevation"})."""
    key = json.dumps([placements, sorted(new), None if shown is None else sorted(shown),
                      list(frame) if frame else None, view, list(size)], sort_keys=True)
    data, (w, h) = _png(key)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img">'
            f'<image href="data:image/png;base64,{base64.b64encode(data).decode()}" width="{w}" height="{h}"/></svg>')


def cover(book) -> str:
    """The finished model, as the carousel card shows it."""
    return picture(book["placements"], view=book.get("view"))


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
        items.append(f'<li>{picture([solo], size=THUMB)}<span><b>{part["qty"]}×</b> '
                     f'{html.escape(part["label"])}</span></li>')
    return '<ul class="parts">' + "".join(items) + "</ul>"


def render_checklist(drafts, first=None, verified=0) -> str:
    """The draft piece lists as one printable page for a hand-check at the
    table, in the order given: unsure lines first and highlighted, a swatch per
    colour, lines numbered as the hand-check tool numbers them, and where a
    second read differs. first: {id: why} for the drafts to start with (marked
    "start here"). verified: how many drafts two reads already verified (not
    on the page)."""
    first = first or {}
    css = PAGE_CSS + """
.draft h2 { display: flex; justify-content: space-between; gap: 8px; }
.draft .state { font-size: 12px; font-weight: 600; padding: 3px 8px; border-radius: 9px; background: #fff1c2; }
.draft .state.done { background: #dff1e6; color: #1f8a4c; }
.draft table { border-collapse: collapse; width: 100%; font-size: 14px; }
.draft td { padding: 5px 4px; border-top: 1px solid var(--line); vertical-align: top; }
.draft td.box { width: 22px; } .draft td.qty { width: 34px; font-weight: 700; text-align: right; }
.draft tr.unsure { background: #fff6d8; } .draft .why { color: #8a5a00; font-size: 12px; display: block; }
.sw { display: inline-block; width: 12px; height: 12px; border-radius: 3px; border: 1px solid rgba(0,0,0,.3); margin-right: 6px; vertical-align: -1px; }
.draft .by { font-size: 11px; font-weight: 600; padding: 2px 7px; border-radius: 8px; background: #e7eefb; color: #2d4a7c; margin-left: 4px; }
.draft .count { color: #8a5a00; }
.draft .start { font-size: 11px; font-weight: 700; padding: 2px 7px; border-radius: 8px; background: #ffd84d; margin-left: 4px; }
.draft td.n { width: 26px; color: #888; font-size: 12px; }
.draft .second { background: #fde8e4; border-radius: 8px; padding: 6px 10px; font-size: 13px; }
.draft .second ul { margin: 4px 0 0; padding-left: 18px; }
"""
    waiting = sum(not d["hand_check"]["done"] for d in drafts)
    by_wonder = sum(d.get("read_by") == "muse-wonder-1.0" for d in drafts)
    out = ["<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">",
           "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
           f"<title>Manual hand-check · BinBuild</title><style>{css}</style></head><body>",
           "<header><h1>✅ Manual hand-check</h1>"
           f"<p>{len(drafts)} draft piece lists read from the book · {waiting} waiting for a check"
           + (f" · {by_wonder} read by Muse Wonder" if by_wonder else "")
           + (f" · {verified} more verified by two reads that agree, not listed" if verified else "")
           + "</p></header><main>",
           '<section class="card"><p class="note">For each build: lay these pieces out from the kit next to its page '
           "and build the model once. Tick each line; fix a count or a colour that's wrong. Highlighted lines were "
           "hard to read in the photo; fix them with <code>--set</code> or confirm them with <code>--sure</code>. "
           "As you build, record the steps, one per layer: <code>python -m backend.manual_check &lt;id&gt; "
           "--record</code> asks what to do and where each piece goes (<code>#n @x,y,z</code>: studs along the "
           "table, plates up; a brick is 3). <code>--preview FILE.html</code> shows the booklet they make. "
           "Then <code>--done --by NAME</code>: the build is verified and gets its booklet. "
           + (f"Start with the {len(first)} marked <b>start here</b>: closest to verified." if first else "")
           + "</p>"
           + ('<p class="note">Lists marked <b>read by Muse Wonder</b> come from the picture of the finished model, '
              "not from a printed list: pieces hidden inside the model may be missing or guessed, so build it "
              "before you tick.</p>" if by_wonder else "") + "</section>"]
    for d in drafts:
        done = d["hand_check"]["done"]
        wonder = d.get("read_by") == "muse-wonder-1.0"
        cc = d.get("count_check")
        count = (f' · <span class="count">the page says {cc["page_says"]}'
                 + ("" if cc["matches"] else f', this list has {cc["list_total"]}') + "</span>") if cc else ""
        note = f'<p class="note">Wonder: {html.escape(d["count_note"])}</p>' if d.get("count_note") else ""
        second = d.get("second_read") or {}
        if second and not second.get("agrees"):
            note += ('<div class="second"><b>A second read of the page disagrees</b> (Muse Wonder, '
                     f'{html.escape(second["on"])}), so check these lines first:<ul>'
                     + "".join(f"<li>{html.escape(x)}</li>" for x in second["differences"]) + "</ul></div>")
        disputed = d.get("picture_check") or {}
        if disputed.get("agrees") is False:
            note += (f'<div class="second"><b>The page\'s picture disagrees with this list</b> '
                     f'({html.escape(disputed["by"])}, {html.escape(disputed["on"])}), so check these lines first:<ul>'
                     + "".join(f"<li>{html.escape(x)}</li>" for x in disputed["differences"]) + "</ul></div>")
        steps = len(d.get("steps") or [])
        start = (f'<span class="start" title="{html.escape(first[d["id"]])}">start here</span>'
                 if d["id"] in first else "")
        out.append(f'<section class="card draft"><h2><span>{html.escape(d["name"])} '
                   f'<small>· page{"s" * (len(d["pages"]) > 1)} {", ".join(map(str, d["pages"]))}</small>'
                   + start + ('<span class="by">read by Muse Wonder</span>' if wonder else "") + '</span>'
                   f'<span class="state{" done" if done else ""}">{"hand-checked" if done else "draft"}</span></h2>'
                   f'<p class="note">{html.escape(d["id"])} · {d["elements_total"]} elements{count} · '
                   f'{d["unsure_elements"]} unsure · {steps} step{"s" * (steps != 1)} recorded · '
                   f'from {html.escape(d["read_from"])}</p>'
                   + (f'<p class="note"><b>Start here:</b> {html.escape(first[d["id"]])}.</p>' if start else "")
                   + f'{note}<table>')
        for n, e in sorted(enumerate(d["elements"], 1), key=lambda ne: ne[1]["sure"]):
            why = f'<span class="why">unsure: {html.escape(e["doubt"] or "")}</span>' if not e["sure"] else ""
            out.append(f'<tr class="{"" if e["sure"] else "unsure"}"><td class="box">☐</td><td class="n">#{n}</td>'
                       f'<td class="qty">{e["qty"]}×</td><td><span class="sw" style="background:'
                       f'{HEX.get(e["color"], HEX["unknown"])}"></span>{html.escape(label(e))}{why}</td></tr>')
        out.append("</table></section>")
    out.append("</main><footer>BinBuild · Not affiliated with the LEGO Group.</footer></body></html>")
    return "".join(out)


def render_html(book) -> str:
    """The booklet as one self-contained HTML page."""
    from .ldraw_render import bounds
    placements, view = book["placements"], book.get("view")
    frame = bounds(placements, view)
    total = sum(p["qty"] for p in book["parts"])
    out = [
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
        f"<title>{html.escape(book['title'])} · BinBuild booklet</title><style>{PAGE_CSS}</style></head><body>",
        f"<header><h1>🧱 {html.escape(book['title'])}</h1><p>{html.escape(book['subtitle'])}</p></header><main>",
        '<section class="card"><h2>What you will build</h2>',
        f'<div class="pic">{picture(placements, frame=frame, view=view)}</div>',
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
            f'<div class="pic">{picture(placements, new=step["add"], shown=placed, frame=frame, view=view)}</div>'
            f'<p>{html.escape(step["text"])}</p></div></section>')
    out.append('<section class="card"><h2>🎉 Done!</h2>'
               f'<p class="note">{len(book["steps"])} steps, {total} pieces. '
               f'Made by BinBuild from {html.escape(book["source"])}.</p></section>')
    out.append("</main><footer>BinBuild · Not affiliated with the LEGO Group.</footer></body></html>")
    return "".join(out)
