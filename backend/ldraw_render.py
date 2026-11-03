"""Booklet pictures from real part shapes: the LDraw meshes in
ldraw_kit.json.gz (see ldraw_mesh), placed on the booklet grid, drawn with a
z-buffer, flat shading and the parts' own edge lines, like a printed
instruction book.

Grid -> LDraw: grid x is LDraw x, grid y is LDraw z, and up is -y; a stud is
20 LDraw units, a plate 8. A view is {"yaw": degrees, "elevation": degrees}:
yaw 45 looks from the +x/+y corner (the corner the vector pictures used),
elevation is the camera's height above the table.
"""

import gzip
import io
import json
import math
from functools import lru_cache

import numpy as np
from PIL import Image

from . import wonder_design as wd
from .ldraw_mesh import MESHES

DEFAULT_VIEW = {"yaw": 45, "elevation": 32}
SUPERSAMPLE = 3
DEPTH_EPS = 1.2  # LDraw units: an edge this close in front of the surface under it is drawn

# Plain bricks, plates and tiles by size.
PLAIN = {
    "brick": {"1x1": "3005", "1x2": "3004", "1x3": "3622", "1x4": "3010", "1x6": "3009", "1x8": "3008",
              "2x2": "3003", "2x3": "3002", "2x4": "3001", "2x6": "2456", "2x8": "3007"},
    "plate": {"1x1": "3024", "1x2": "3023b", "1x3": "3623", "1x4": "3710", "1x6": "3666", "1x8": "3460",
              "2x2": "3022", "2x3": "3021", "2x4": "3020", "2x6": "3795", "2x8": "3034"},
    "tile": {"1x1": "3070b", "1x2": "3069b", "1x3": "63864", "1x4": "2431", "2x2": "3068b"},
}
PRINTED = {"98138": "98138p07"}  # the kit's printed round tile is the eye

# Which way each directional part faces as LDraw draws it, as (x, z):
# "down" the end a slope falls to, "studs" a wedge's or edge tile's studded
# edge, "clip" the end the clip sticks out of, "side" the face with side studs.
NATIVE = {
    "54200": ("down", (0, -1)), "11477": ("down", (0, -1)), "6091": ("down", (0, -1)), "50950": ("down", (0, -1)),
    "41769a": ("studs", (1, 0)), "41770a": ("studs", (-1, 0)), "33909": ("studs", (0, 1)),
    "63868": ("clip", (1, 0)),
    "32952": ("side", (0, -1)), "30414": ("side", (0, -1)), "4070": ("side", (0, -1)),
}
TAPER = {"41769a": (0, -1), "41770a": (0, -1)}  # a wedge's narrow end
WEDGES = ("41769a", "41770a")                   # the same footprint, mirrored: the kit has one of each
PROTRUDES = {"63868", "32952", "30414"}         # the body is centred on the origin; the clip or studs stick out

# The light, relative to the camera: (to the right, towards the viewer, up).
# Tops brightest, the left-hand sides a little darker, the right-hand sides darkest.
LIGHT = (-0.144, 0.663, 0.734)


# --- meshes -------------------------------------------------------------------------

def _rgb(hex_color):
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))


@lru_cache(maxsize=1)
def meshes() -> dict:
    with gzip.open(MESHES, "rt", encoding="utf-8") as fh:
        data = json.load(fh)["meshes"]
    out = {}
    for name, m in data.items():
        tris = np.array(m["tris"], np.float64).reshape(-1, 3, 3)
        two = np.zeros(len(tris), bool)
        two[m["two"]] = True
        out[name] = {"tris": tris, "tc": np.array(m["tc"], int), "two": two,
                     "lines": np.array(m["lines"], np.float64).reshape(-1, 2, 3), "lc": np.array(m["lc"], int),
                     "cond": np.array(m["cond"], np.float64).reshape(-1, 4, 3), "cc": np.array(m["cc"], int),
                     "palette": [_rgb(h) for h in m["palette"]]}
        out[name]["body"] = _body(name, out[name])
    return out


def _body(name, mesh):
    """(centre x, centre z, half x, half z, bottom y) of a part's body, in LDraw units."""
    pts = np.concatenate([mesh["tris"].reshape(-1, 3), mesh["lines"].reshape(-1, 3)])
    lo, hi = pts.min(0), pts.max(0)
    if name in PROTRUDES:
        hx = min(-lo[0], hi[0])
        hz = min(-lo[2], hi[2])
        inside = (np.abs(pts[:, 0]) < hx - 0.5) & (np.abs(pts[:, 2]) < hz - 0.5)
        return 0.0, 0.0, hx, hz, pts[inside, 1].max()
    return (lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2, (hi[0] - lo[0]) / 2, (hi[2] - lo[2]) / 2, hi[1]


_CODE = {v: k for k, v in wd.CODES.items()}


def ldraw_number(part):
    """The LDraw part for a booklet part, or None (drawn as a plain block)."""
    family, size = part["family"], part.get("size") or ""
    shape = " ".join((part.get("shape") or "").lower().split())
    size = wd.canonical(size) if "x" in size else size
    if shape in ("", family) and family in PLAIN:
        return PLAIN[family].get(size)
    code = _CODE.get((family, shape))
    if code is None and shape == "round tile":
        return "98138"
    found = wd.part_for(code, size, part.get("color")) if code else None
    if not found:
        return None
    number = found.ldraw.split("/")[0]
    return PRINTED.get(number, number) if "printed" in shape else number


def _block(p):
    """A part with no LDraw mesh here: a box with a stud on every cell."""
    lx, ly, h = p["dims"]
    kit = meshes()
    box, stud = kit["box5.dat"], kit["stud.dat"]
    height = h * 8
    tris = [box["tris"] * [lx * 10, height, ly * 10] + [lx * 10, 0, ly * 10]]
    lines = [box["lines"] * [lx * 10, height, ly * 10] + [lx * 10, 0, ly * 10]]
    cond, tc, lc, cc = [], [box["tc"]], [box["lc"]], []
    if p["kind"] in ("brick", "plate", "round"):
        for cx in range(lx):
            for cy in range(ly):
                off = [cx * 20 + 10, 0, cy * 20 + 10]
                tris.append(stud["tris"] + off)
                lines.append(stud["lines"] + off)
                cond.append(stud["cond"] + off)
                tc.append(stud["tc"])
                lc.append(stud["lc"])
                cc.append(stud["cc"])
    mesh = {"tris": np.concatenate(tris), "tc": np.concatenate(tc), "two": np.zeros(sum(len(t) for t in tris), bool),
            "lines": np.concatenate(lines), "lc": np.concatenate(lc),
            "cond": np.concatenate(cond) if cond else np.zeros((0, 4, 3)),
            "cc": np.concatenate(cc) if cc else np.zeros(0, int), "palette": []}
    return mesh, (lx * 10, ly * 10, lx * 10, ly * 10, height)


# --- placing parts ----------------------------------------------------------------------

def _turn(k, v):
    """(x, z) turned k quarter turns about the vertical."""
    x, z = v
    for _ in range(k % 4):
        x, z = z, -x
    return x, z


_DIRS = {"+x": (1, 0), "-x": (-1, 0), "+y": (0, 1), "-y": (0, -1)}


def _orient(number, p, view):
    """Quarter turns for a part so its footprint and directional end match the
    placement. Side studs face the placement's `side`, else the camera."""
    body = meshes()[number]["body"]
    lx, ly, _ = p["dims"]
    native = (round(body[2] / 10), round(body[3] / 10))
    fits = [k for k in range(4) if (native if k % 2 == 0 else native[::-1]) == (lx, ly)]
    if not fits:
        return None
    kind, direction = NATIVE.get(number, (None, None))
    want = {"down": p.get("down"), "studs": p.get("studs"), "clip": p.get("clip"), "side": p.get("side")}.get(kind)
    if want in _DIRS:
        match = [k for k in fits if _turn(k, direction) == _DIRS[want]]
        fits = match or fits
    elif kind == "side":
        yaw = math.radians(view["yaw"])
        toward = (math.sin(yaw), math.cos(yaw))
        fits = sorted(fits, key=lambda k: -(_turn(k, direction)[0] * toward[0] + _turn(k, direction)[1] * toward[1]))
    return fits[0]


def _wedge(p, centre):
    """Which wedge mould and turn: the studs on the placement's edge, the
    narrow end at the placement's `narrow`, else pointing away from the
    model's centre."""
    x0, y0, _ = p["at"]
    lx, ly, _ = p["dims"]
    away = _DIRS.get(p.get("narrow")) or (x0 + lx / 2 - centre[0], y0 + ly / 2 - centre[1])
    best = None
    for number in WEDGES:
        k = _orient(number, p, DEFAULT_VIEW)
        if k is None:
            continue
        tx, tz = _turn(k, TAPER[number])
        score = tx * away[0] + tz * away[1]
        if best is None or score > best[0] + 1e-9:
            best = (score, number, k)
    return best[1:] if best else (None, None)


def _placed(placements, view):
    """Every placement as (mesh, world transform). The transform maps LDraw
    part coordinates to LDraw world coordinates: rotation, then offset."""
    centre = _centre(placements)
    out = []
    for p in placements:
        number = ldraw_number(p["part"])
        k = None
        if number in WEDGES:
            number, k = _wedge(p, centre)
        elif number:
            k = _orient(number, p, view)
        if number is None or k is None:
            mesh, body = _block(p)
            k = 0
        else:
            mesh, body = meshes()[number], meshes()[number]["body"]
        cx, cz, _, _, bottom = body
        rot = np.eye(3)
        for _ in range(k):
            rot = np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]]) @ rot
        x0, y0, z0 = p["at"]
        lx, ly, _ = p["dims"]
        target = np.array([(x0 + lx / 2) * 20, -z0 * 8, (y0 + ly / 2) * 20])
        offset = target - rot @ np.array([cx, bottom, cz])
        out.append((mesh, rot, offset))
    return out


def _centre(placements):
    xs = [p["at"][0] + p["dims"][0] / 2 for p in placements] or [0]
    ys = [p["at"][1] + p["dims"][1] / 2 for p in placements] or [0]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


# --- the camera ------------------------------------------------------------------------

def _camera(view):
    """(screen x, screen y down, depth towards the viewer) rows, from LDraw world."""
    yaw, el = math.radians(view["yaw"]), math.radians(view["elevation"])
    sa, ca, se, ce = math.sin(yaw), math.cos(yaw), math.sin(el), math.cos(el)
    # world: x, y (down), z. horizontal: across = x ca - z sa, towards = x sa + z ca; up = -y
    return np.array([[ca, 0, -sa],
                     [sa * se, ce, ca * se],
                     [sa * ce, -se, ca * ce]])


def _light(view):
    yaw = math.radians(view["yaw"])
    right, toward, up = np.array([math.cos(yaw), 0, -math.sin(yaw)]), np.array([math.sin(yaw), 0, math.cos(yaw)]), \
        np.array([0, -1, 0])
    light = LIGHT[0] * right + LIGHT[1] * toward + LIGHT[2] * up
    return light / np.linalg.norm(light)


def _world(placed, which, key):
    parts = [(placed[i][0][key] @ placed[i][1].T) + placed[i][2] for i in which if len(placed[i][0][key])]
    return parts


def bounds(placements, view=None, shown=None):
    """Screen-space box (LDraw units) of the shown placements: a frame for pictures."""
    view = view or DEFAULT_VIEW
    shown = range(len(placements)) if shown is None else shown
    placed = _placed(placements, view)
    pts = [w.reshape(-1, 3) for w in _world(placed, shown, "tris")]
    if not pts:
        return (0.0, 0.0, 1.0, 1.0)
    s = np.concatenate(pts) @ _camera(view).T
    return float(s[:, 0].min()), float(s[:, 1].min()), float(s[:, 0].max()), float(s[:, 1].max())


# --- drawing ---------------------------------------------------------------------------

def _mix(rgb, toward, t):
    return tuple(round(c + (w - c) * t) for c, w in zip(rgb, toward))


def _edge_rgb(base):
    dark = sum(base) < 200
    return _mix(base, (255, 255, 255), 0.45) if dark else _mix(base, (0, 0, 0), 0.6)


def _raster(tri2, depth, rgb, width, height):
    """Z-buffer the screen triangles. Returns (depth, colour, coverage) buffers."""
    zbuf = np.full(width * height, -np.inf)
    out = np.zeros((width * height, 3), np.uint8)
    if not len(tri2):
        return zbuf, out, np.zeros(width * height, bool)
    x, y = tri2[:, :, 0], tri2[:, :, 1]
    area = (x[:, 1] - x[:, 0]) * (y[:, 2] - y[:, 0]) - (y[:, 1] - y[:, 0]) * (x[:, 2] - x[:, 0])
    xmin = np.clip(np.floor(x.min(1)).astype(int), 0, width - 1)
    xmax = np.clip(np.ceil(x.max(1)).astype(int), 0, width - 1)
    ymin = np.clip(np.floor(y.min(1)).astype(int), 0, height - 1)
    ymax = np.clip(np.ceil(y.max(1)).astype(int), 0, height - 1)
    size = np.maximum(xmax - xmin, ymax - ymin) + 1
    ok = np.abs(area) > 1e-9
    idx_all, d_all, t_all = [], [], []
    k = 1
    while True:
        sel = np.nonzero(ok & (size <= k) & (size > k // 2))[0]
        if len(sel):
            gy, gx = np.divmod(np.arange(k * k), k)
            chunk = max(1, 600_000 // (k * k))
            for s in range(0, len(sel), chunk):
                ids = sel[s:s + chunk]
                px = xmin[ids, None] + gx[None, :]
                py = ymin[ids, None] + gy[None, :]
                fx, fy = px + 0.5, py + 0.5
                x0, x1, x2 = (x[ids, i, None] for i in range(3))
                y0, y1, y2 = (y[ids, i, None] for i in range(3))
                a = area[ids, None]
                w0 = ((x2 - x1) * (fy - y1) - (y2 - y1) * (fx - x1)) / a
                w1 = ((x0 - x2) * (fy - y2) - (y0 - y2) * (fx - x2)) / a
                w2 = 1 - w0 - w1
                inside = ((w0 >= -1e-9) & (w1 >= -1e-9) & (w2 >= -1e-9)
                          & (px <= xmax[ids, None]) & (py <= ymax[ids, None]))
                rows, cols = np.nonzero(inside)
                if not len(rows):
                    continue
                d = (w0 * depth[ids, 0, None] + w1 * depth[ids, 1, None] + w2 * depth[ids, 2, None])[rows, cols]
                idx_all.append(py[rows, cols] * width + px[rows, cols])
                d_all.append(d)
                t_all.append(ids[rows])
        if k >= size[ok].max(initial=1):
            break
        k *= 2
    if not idx_all:
        return zbuf, out, np.zeros(width * height, bool)
    idx, d, t = np.concatenate(idx_all), np.concatenate(d_all), np.concatenate(t_all)
    np.maximum.at(zbuf, idx, d)
    win = d >= zbuf[idx]
    out[idx[win]] = rgb[t[win]]
    return zbuf, out, np.isfinite(zbuf)


def _draw_lines(seg2, segd, rgb, zbuf, out, cover, width, height, thick):
    """Edge lines over the z-buffered picture: drawn where nothing is in front."""
    if not len(seg2):
        return
    a, b = seg2[:, 0], seg2[:, 1]
    n = np.maximum(np.ceil(np.hypot(*(b - a).T) / 0.5).astype(int), 1) + 1
    seg = np.repeat(np.arange(len(seg2)), n)
    start = np.repeat(np.cumsum(n) - n, n)
    t = (np.arange(n.sum()) - start) / (n[seg] - 1).clip(1)
    px = a[seg, 0] + t * (b[seg, 0] - a[seg, 0])
    py = a[seg, 1] + t * (b[seg, 1] - a[seg, 1])
    d = segd[seg, 0] + t * (segd[seg, 1] - segd[seg, 0])
    ix, iy = np.floor(px).astype(int), np.floor(py).astype(int)
    inb = (ix >= 0) & (ix < width) & (iy >= 0) & (iy < height)
    ix, iy, d, seg = ix[inb], iy[inb], d[inb], seg[inb]
    vis = d >= zbuf[iy * width + ix] - DEPTH_EPS
    ix, iy, seg = ix[vis], iy[vis], seg[vis]
    r = thick / 2
    span = range(-math.ceil(r) + 1, math.ceil(r) + 1)
    for ox in span:
        for oy in span:
            jx, jy = ix + ox, iy + oy
            keep = (jx >= 0) & (jx < width) & (jy >= 0) & (jy < height)
            pix = jy[keep] * width + jx[keep]
            out[pix] = rgb[seg[keep]]
            cover[pix] = True


def render(placements, shown=None, new=(), frame=None, view=None, size=(720, 540), max_scale=4.0) -> Image.Image:
    """An RGBA picture of the shown placements (default all). Parts in `new`
    are in full colour, the others faded, unless `new` is empty. frame: a
    screen box from bounds() so a booklet's steps share one framing."""
    view = view or DEFAULT_VIEW
    shown = list(range(len(placements)) if shown is None else shown)
    new = set(new)
    frame = frame or bounds(placements, view, shown)
    pad = 10
    fx0, fy0, fx1, fy1 = frame[0] - pad, frame[1] - pad, frame[2] + pad, frame[3] + pad
    scale = min(size[0] / (fx1 - fx0), size[1] / (fy1 - fy0), max_scale)
    width, height = max(1, round((fx1 - fx0) * scale)), max(1, round((fy1 - fy0) * scale))
    ss = SUPERSAMPLE
    sw, sh = width * ss, height * ss
    cam = _camera(view)
    toward, light_dir = cam[2], _light(view)
    placed = _placed(placements, view)

    tri_s, tri_d, tri_rgb, seg_s, seg_d, seg_rgb = [], [], [], [], [], []
    for i in shown:
        mesh, rot, offset = placed[i]
        base = _rgb(_hex(placements[i]["part"]["color"]))
        faded = bool(new) and i not in new
        palette = [base] + [tuple(c) for c in mesh["palette"]]
        edge = _edge_rgb(base)
        if len(mesh["tris"]):
            w = mesh["tris"] @ rot.T + offset
            nrm = np.cross(w[:, 1] - w[:, 0], w[:, 2] - w[:, 0])
            length = np.linalg.norm(nrm, axis=1)
            keep = length > 1e-12
            w, nrm, two, tc = w[keep], nrm[keep] / length[keep, None], mesh["two"][keep], mesh["tc"][keep]
            facing = nrm @ toward
            nrm = np.where((two & (facing < 0))[:, None], -nrm, nrm)
            keep = (facing > 1e-6) | two
            w, nrm, tc = w[keep], nrm[keep], tc[keep]
            light = 0.45 + 0.55 * np.clip(nrm @ light_dir, 0, None) / LIGHT[2]
            light = np.clip(light, 0, 1.06)
            cols = np.array([palette[0] if c < 0 else palette[c + 1] for c in tc], float).reshape(-1, 3)
            cols = np.clip(cols * light[:, None], 0, 255)
            if faded:
                cols = cols + (255 - cols) * 0.62
            s = w @ cam.T
            tri_s.append(s[:, :, :2])
            tri_d.append(s[:, :, 2])
            tri_rgb.append(cols.astype(np.uint8))
        for key, ckey in (("lines", "lc"), ("cond", "cc")):
            if not len(mesh[key]):
                continue
            w = mesh[key] @ rot.T + offset
            s = w @ cam.T
            cols = mesh[ckey]
            if key == "cond":
                p1, p2, c1, c2 = (s[:, j, :2] for j in range(4))
                u, v1, v2 = p2 - p1, c1 - p1, c2 - p1
                side1 = u[:, 0] * v1[:, 1] - u[:, 1] * v1[:, 0]
                side2 = u[:, 0] * v2[:, 1] - u[:, 1] * v2[:, 0]
                show = side1 * side2 > 0
                s, cols = s[show][:, :2], cols[show]
            rgb = np.array([edge if c < 0 else palette[c + 1] for c in cols], float).reshape(-1, 3)
            if faded:
                rgb = rgb + (255 - rgb) * 0.62
            seg_s.append(s[:, :, :2])
            seg_d.append(s[:, :, 2])
            seg_rgb.append(rgb.astype(np.uint8))

    def to_px(s):
        return np.stack([(s[..., 0] - fx0) * scale * ss, (s[..., 1] - fy0) * scale * ss], -1)

    if tri_s:
        zbuf, out, cover = _raster(to_px(np.concatenate(tri_s)), np.concatenate(tri_d),
                                   np.concatenate(tri_rgb), sw, sh)
    else:
        zbuf, out, cover = np.full(sw * sh, -np.inf), np.zeros((sw * sh, 3), np.uint8), np.zeros(sw * sh, bool)
    if seg_s:
        thick = max(1.0, min(1.25, scale / 2.2)) * ss
        _draw_lines(to_px(np.concatenate(seg_s)), np.concatenate(seg_d), np.concatenate(seg_rgb),
                    zbuf, out, cover, sw, sh, thick)
    rgba = np.concatenate([out, (cover * 255).astype(np.uint8)[:, None]], 1).reshape(sh, sw, 4)
    img = Image.fromarray(rgba).convert("RGBa").resize((width, height), Image.BOX)
    return img.convert("RGBA")


def _hex(color):
    from .booklet import HEX
    return HEX.get(color, HEX["unknown"])


def png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()
