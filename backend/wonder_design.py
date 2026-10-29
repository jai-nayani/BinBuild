"""Designs with every kind of piece the kit owns, and their validator.

BrickGPT's format is one brick per line, `SIZE (x,y,z)`, and it only knows
the 8 plain brick sizes. This module keeps that line and extends it, so the
same parser shape and the booklet path still apply:

    SIZE (x,y,z) CODE COLOR [down=+x | studs=-y | clip=+y]

- SIZE `HxW`: H studs along x, W along y (as BrickGPT). The inventory key
  sorts it (`2x1` and `1x2` are the same piece).
- (x,y,z): the piece's minimum corner; x and y in studs, z in **plates**
  (a brick is 3 plates; BrickGPT counted z in bricks).
- CODE: which kind of piece (PARTS below), COLOR: its BrickLink colour.
- A direction for pieces that need one: which way a slope runs down, which
  edge carries the studs, which end the clip is on.

Geometry comes from the LDraw library (stud pitch 20 LDU = 8 mm, plate
8 LDU = 3.2 mm, brick 24 LDU = 9.6 mm): each part's footprint, height and
top studs were read from its .dat file, and `verify_against_ldraw` checks
them again whenever the library is on the machine.

The validator checks a design against the owned inventory: counts within
what is owned, every piece on the stud grid and inside the 20 x 20 base,
no two pieces in the same space, and every piece held by studs to the rest
(one connected model that stands on the table). Connections are vertical
only: a piece's bottom on the top studs of a piece below. Side studs,
clips and bars are not counted as connections. Standard library only.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

GRID = 20             # studs, as BrickGPT
MAX_PLATES = 60       # 20 bricks
LDRAW = Path.home() / "Downloads" / "ldraw"

# code: (inventory family, inventory shape)
CODES = {
    "brick": ("brick", "brick"),
    "round_brick": ("brick", "round brick"),
    "headlight_brick": ("brick", "headlight brick"),
    "tall_side_stud_brick": ("brick", "tall 1x1 brick with 2 studs on side"),
    "side_stud_brick": ("brick", "brick with 4 studs on side"),
    "plate": ("plate", "plate"),
    "round_plate": ("plate", "round plate"),
    "clip_plate": ("plate", "plate with clip"),
    "jumper_plate": ("plate", "jumper plate"),
    "wedge_plate": ("plate", "wedge plate"),
    "cheese_slope": ("slope", "1x1 slope (cheese)"),
    "curved_slope": ("slope", "curved slope"),
    "round_tile": ("tile", "round printed tile"),
    "edge_stud_tile": ("tile", "tile with 2 studs on edge"),
}


@dataclass(frozen=True)
class Part:
    """One kind of piece. top: "all" (a stud on every cell), "none", "edge"
    (studs only along the edge `studs=` names), "low_end" (a stud only on
    the cell at the `down=` end, which is lower), "off_grid" (one stud
    between two cells: nothing can go on it in this format). bottom: "all"
    or "edge" (only the cells under the studded edge reach a stud below).
    direction: the token the line must carry, if any."""

    code: str
    size: str
    height: int                   # plates
    ldraw: str
    top: str = "all"
    bottom: str = "all"
    direction: str = None         # "down", "studs" or "clip"
    low_end_height: int = None    # low_end parts: the stud cell's height
    note: str = ""


# Kit pieces -> LDraw parts. Colour only matters where one inventory key
# covers two different moulds (the kit's black and azure "curved slopes").
PARTS = {
    ("brick", "1x2", None): Part("brick", "1x2", 3, "3004"),
    ("round_brick", "1x1", None): Part("round_brick", "1x1", 3, "3062b"),
    ("headlight_brick", "1x1", None): Part("headlight_brick", "1x1", 3, "4070",
                                           note="its side stud is not a connection here"),
    ("tall_side_stud_brick", "1x1", None): Part("tall_side_stud_brick", "1x1", 5, "32952",
                                                note="1 2/3 bricks tall; side studs not counted"),
    ("side_stud_brick", "1x4", None): Part("side_stud_brick", "1x4", 3, "30414",
                                           note="side studs not counted"),
    ("plate", "1x2", None): Part("plate", "1x2", 1, "3023b"),
    ("plate", "1x6", None): Part("plate", "1x6", 1, "3666"),
    ("plate", "2x2", None): Part("plate", "2x2", 1, "3022"),
    ("plate", "2x4", None): Part("plate", "2x4", 1, "3020"),
    ("round_plate", "1x1", None): Part("round_plate", "1x1", 1, "6141"),
    ("clip_plate", "1x2", None): Part("clip_plate", "1x2", 1, "63868", direction="clip",
                                      note="the clip sticks out past the `clip=` end"),
    ("jumper_plate", "1x2", None): Part("jumper_plate", "1x2", 1, "3794b", top="off_grid",
                                        note="one centre stud between the two cells: nothing may sit on it"),
    ("wedge_plate", "2x4", None): Part("wedge_plate", "2x4", 1, "41769a/41770a", top="edge", bottom="edge",
                                       direction="studs",
                                       note="4 studs along one long edge; the other half tapers off"),
    ("cheese_slope", "1x1", None): Part("cheese_slope", "1x1", 2, "54200", top="none", direction="down"),
    ("curved_slope", "1x2", "black"): Part("curved_slope", "1x2", 2, "11477", top="none", direction="down"),
    ("curved_slope", "1x2", "medium_azure"): Part("curved_slope", "1x2", 4, "6091", top="low_end",
                                                  direction="down", low_end_height=3,
                                                  note="the curve peaks at 4 plates next to the stud end and "
                                                       "falls away to the other end; the stud end is a flat step "
                                                       "3 plates tall with one stud; down= names the stud end"),
    ("curved_slope", "1x3", None): Part("curved_slope", "1x3", 3, "50950", top="none", direction="down",
                                        note="a brick tall at the high end"),
    ("round_tile", "1x1", None): Part("round_tile", "1x1", 1, "98138", top="none"),
    ("edge_stud_tile", "2x2", None): Part("edge_stud_tile", "2x2", 1, "33909", top="edge", direction="studs",
                                          note="2 studs along one edge, the other half smooth"),
}
# The kit's black "1x4 hinge plate" isn't modelled: no LDraw part matches the
# book's drawing (two studs in the middle, bars at the ends), so designs may not use it.
EXCLUDED = {("plate", "hinge plate", "1x4"): "no LDraw part matches it, so its studs aren't known"}

LINE = re.compile(r"^(\d+)x(\d+) \((-?\d+),(-?\d+),(-?\d+)\) ([a-z_]+) ([a-z_]+)"
                  r"(?: (down|studs|clip)=([+-][xy]))?$")


def canonical(size: str) -> str:
    a, b = sorted(int(n) for n in size.split("x"))
    return f"{a}x{b}"


def part_for(code, size, color):
    """The Part for a code, size (any orientation) and colour, or None."""
    size = canonical(size)
    return PARTS.get((code, size, color)) or PARTS.get((code, size, None))


def inventory_key(code, size, color) -> tuple:
    family, shape = CODES[code]
    return family, shape, canonical(size), color


@dataclass
class Piece:
    line: int
    h: int                # studs along x
    w: int                # studs along y
    x: int
    y: int
    z: int                # plates
    code: str
    color: str
    direction: str = None   # "+x", "-y", ...
    part: Part = field(default=None, repr=False)

    @property
    def key(self):
        return inventory_key(self.code, f"{self.h}x{self.w}", self.color)

    def text(self) -> str:
        d = f" {self.part.direction}={self.direction}" if self.part and self.part.direction and self.direction else ""
        return f"{self.h}x{self.w} ({self.x},{self.y},{self.z}) {self.code} {self.color}{d}"

    def cells(self):
        return [(self.x + i, self.y + j) for i in range(self.h) for j in range(self.w)]

    def _edge(self, cell, sign_axis):
        """Is cell on the edge or end named by sign_axis ("+x", "-y", ...)?"""
        sign, axis = sign_axis[0], sign_axis[1]
        i, j = cell[0] - self.x, cell[1] - self.y
        if axis == "x":
            return i == (self.h - 1 if sign == "+" else 0)
        return j == (self.w - 1 if sign == "+" else 0)

    def cell_height(self, cell) -> int:
        """Plates this piece fills above its z at a cell."""
        p = self.part
        if p.top == "low_end" and self._edge(cell, self.direction):
            return p.low_end_height
        return p.height

    def studs(self):
        """{cell: height (plates above the table) of the stud's base}."""
        p = self.part
        if p.top == "all":
            return {c: self.z + p.height for c in self.cells()}
        if p.top == "edge":
            return {c: self.z + p.height for c in self.cells() if self._edge(c, self.direction)}
        if p.top == "low_end":
            return {c: self.z + p.low_end_height for c in self.cells() if self._edge(c, self.direction)}
        return {}

    def bottom(self):
        if self.part.bottom == "edge":
            return [c for c in self.cells() if self._edge(c, self.direction)]
        return self.cells()

    def voxels(self):
        """Every (x, y, plate) this piece fills, plus a clip's overhang."""
        out = {(cx, cy, self.z + k) for cx, cy in self.cells() for k in range(self.cell_height((cx, cy)))}
        if self.part.direction == "clip":
            sign, axis = self.direction[0], self.direction[1]
            step = 1 if sign == "+" else -1
            for cx, cy in self.cells():
                if self._edge((cx, cy), self.direction):
                    out.add((cx + step, cy, self.z) if axis == "x" else (cx, cy + step, self.z))
        return out


@dataclass
class Check:
    ok: bool
    pieces: list
    errors: list            # one line each, numbered by design line where possible
    shortfall: dict         # label -> how many more than owned
    counts: dict            # inventory key -> used
    parts: int = 0


def label(key) -> str:
    family, shape, size, color = key
    return f"{color.replace('_', ' ')} {size} {shape}" if not shape.startswith(size) else f"{color.replace('_', ' ')} {shape}"


def parse(text):
    """Design text -> (pieces, errors). Blank lines and # comments are skipped."""
    pieces, errors = [], []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = LINE.match(line)
        if not m:
            errors.append(f"line {n}: can't read {line!r}; expected 'HxW (x,y,z) code color [down|studs|clip=±x|±y]'")
            continue
        h, w, x, y, z = map(int, m.groups()[:5])
        code, color, dkey, dval = m.group(6), m.group(7), m.group(8), m.group(9)
        if code not in CODES:
            errors.append(f"line {n}: unknown piece code {code!r}; codes are {', '.join(CODES)}")
            continue
        part = part_for(code, f"{h}x{w}", color) if h > 0 and w > 0 else None
        if part is None:
            sizes = sorted({k[1] for k in PARTS if k[0] == code})
            errors.append(f"line {n}: you own no {code} of size {h}x{w}; a {code} comes in {', '.join(sizes)}"
                          + ("" if h > 0 and w > 0 else " (sizes start at 1)"))
            continue
        if part.direction and dkey != part.direction:
            errors.append(f"line {n}: a {code} needs '{part.direction}=±x' or '±y'" +
                          (f", not '{dkey}='" if dkey else ""))
            continue
        if not part.direction and dkey:
            errors.append(f"line {n}: a {code} takes no '{dkey}=' direction")
            continue
        piece = Piece(n, h, w, x, y, z, code, color, dval, part)
        if part.direction in ("down", "clip") and h * w > 1:
            long_axis = "x" if h > w else "y"
            if dval[1] != long_axis:
                errors.append(f"line {n}: {code} {h}x{w} runs along {long_axis}, so its {dkey}= must be ±{long_axis}")
                continue
        if part.direction == "studs" and part.code == "wedge_plate":
            short_axis = "x" if h < w else "y"
            if dval[1] != short_axis:
                errors.append(f"line {n}: a {h}x{w} wedge plate's studs run along a long edge, so studs= must be ±{short_axis}")
                continue
        pieces.append(piece)
    return pieces, errors


def validate(text, owned) -> Check:
    """owned: {inventory key: quantity} (see owned_from_items)."""
    pieces, errors = parse(text)
    counts = Counter(p.key for p in pieces)
    shortfall = {}
    for key, n in counts.items():
        have = owned.get(key, 0)
        if key[:3] in EXCLUDED:
            errors.append(f"{label(key)}: not usable ({EXCLUDED[key[:3]]})")
        elif n > have:
            shortfall[label(key)] = n - have
            errors.append(f"{label(key)}: uses {n}, owns {have}" + ("" if have else " (not in the inventory at all)"))
    taken = {}
    for p in pieces:
        if p.x < 0 or p.y < 0 or p.x + p.h > GRID or p.y + p.w > GRID:
            errors.append(f"line {p.line}: {p.text()} is off the {GRID}x{GRID} base")
        if p.z < 0 or p.z + p.part.height > MAX_PLATES:
            errors.append(f"line {p.line}: {p.text()} is below the table or too high")
        for v in sorted(p.voxels()):
            if v in taken and taken[v] != p.line:
                errors.append(f"line {p.line}: {p.text()} overlaps line {taken[v]} at stud ({v[0]},{v[1]}), plate {v[2]}")
                break
            taken[v] = p.line
    if pieces:
        _connectivity(pieces, errors)
    else:
        errors.append("the design has no pieces")
    return Check(not errors, pieces, errors, shortfall, dict(counts), sum(counts.values()))


def _connectivity(pieces, errors):
    """One model, held together by studs, standing on the table."""
    bottoms = {}
    for i, p in enumerate(pieces):
        for c in p.bottom():
            bottoms[(c[0], c[1], p.z)] = i
    parent = list(range(len(pieces)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, p in enumerate(pieces):
        for (cx, cy), top in p.studs().items():
            j = bottoms.get((cx, cy, top))
            if j is not None and j != i:
                parent[root(i)] = root(j)
    groups = {}
    for i in range(len(pieces)):
        groups.setdefault(root(i), []).append(i)
    if len(groups) > 1:
        main = max(groups.values(), key=len)
        for g in groups.values():
            if g is main:
                continue
            lines = ", ".join(str(pieces[i].line) for i in g)
            errors.append(f"line{'s' if len(g) > 1 else ''} {lines}: not held by any stud to the rest of the model (floating or only resting "
                          "on a smooth top, a slope or a jumper plate)")
    if min(p.z for p in pieces) != 0:
        errors.append("no piece stands on the table (the lowest z must be 0)")
    # a piece sitting where a jumper plate's off-grid stud is: not representable
    for p in pieces:
        if p.part.top == "off_grid":
            above = {(cx, cy, p.z + p.part.height) for cx, cy in p.cells()}
            for q in pieces:
                if q is not p and any((cx, cy, q.z) in above for cx, cy in q.bottom()):
                    errors.append(f"line {q.line}: sits on the jumper plate on line {p.line}, whose single stud is "
                                  "half a stud off the grid; nothing may go on a jumper plate")


def owned_from_items(items) -> dict:
    """Confirmed inventory rows -> {inventory key: quantity}."""
    owned = Counter()
    for i in items:
        owned[(i["family"], i["shape"], canonical(i["size"]) if i.get("size") else None, i["color"])] += i["quantity"]
    return dict(owned)


def usable_pieces(owned) -> list:
    """The owned pieces a design may use: (code, color, size, quantity, Part)."""
    reverse = {v: k for k, v in CODES.items()}
    out = []
    for (family, shape, size, color), n in sorted(owned.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][3])):
        code = reverse.get((family, shape))
        part = part_for(code, size, color) if code and size else None
        if part is not None:
            out.append((code, color, size, n, part))
    return out


# --- booklet ------------------------------------------------------------------------------

def turned(pieces):
    """The same model turned 180 degrees about the vertical (a rotation, not a
    mirror, so it is the same model): the booklet's pictures look at the
    +x/+y faces, and this shows the other two."""
    import copy
    wx = max(p.x + p.h for p in pieces)
    wy = max(p.y + p.w for p in pieces)
    flip = {"+x": "-x", "-x": "+x", "+y": "-y", "-y": "+y"}
    out = []
    for p in pieces:
        q = copy.copy(p)
        q.x, q.y = wx - (p.x + p.h), wy - (p.y + p.w)
        q.direction = flip.get(p.direction, p.direction)
        out.append(q)
    return out


def placements(pieces, turn=False):
    """Pieces -> booklet placements (backend/booklet.py), heights from LDraw.
    turn: draw the model turned 180 degrees (see turned)."""
    from . import booklet as bk
    out = []
    for p in (turned(pieces) if turn else pieces):
        family, shape = CODES[p.code]
        part = {"family": family, "shape": shape, "size": canonical(f"{p.h}x{p.w}"), "color": p.color}
        down = p.direction if p.part.direction == "down" else None
        if p.part.top == "low_end" and down:  # 6091's curve falls away from its stud end (LDraw)
            down = ("-" if down[0] == "+" else "+") + down[1]
        pl = bk.place(part, [p.x, p.y, p.z], along="x" if p.h >= p.w else "y", down=down)
        pl["dims"][2] = p.part.height
        out.append(pl)
    return out


# --- LDraw check --------------------------------------------------------------------------

def _ldraw_geometry(number, lib):
    """Footprint (studs along LDraw x and z), height (plates) and upright top
    stud cells (LDraw x, z in studs from the minimum corner) of a part."""
    import math
    dirs = [lib / "parts", lib / "p", lib / "parts" / "s", lib / "p" / "48"]

    def find(name):
        name = name.replace("\\", "/").lower()
        for d in (lib / "parts", lib / "p"):
            if (d / name).exists():
                return d / name
        for d in dirs:
            if (d / Path(name).name).exists():
                return d / Path(name).name
        return None

    pts, studs = [], []

    def walk(path, m, t, depth=0):
        for line in path.read_text(errors="ignore").splitlines():
            f = line.split()
            if not f:
                continue
            if f[0] == "1" and len(f) >= 15:
                pos = [float(v) for v in f[2:5]]
                a = [float(v) for v in f[5:14]]
                nt = [m[r * 3] * pos[0] + m[r * 3 + 1] * pos[1] + m[r * 3 + 2] * pos[2] + t[r] for r in range(3)]
                nm = [sum(m[r * 3 + k] * a[k * 3 + c] for k in range(3)) for r in range(3) for c in range(3)]
                base = Path(" ".join(f[14:]).replace("\\", "/")).name.lower()
                if re.match(r"^stud2?a?\.dat$", base) and nm[4] > 0.5:   # an upright top stud
                    studs.append(nt)
                sub = find(" ".join(f[14:]))
                if sub and depth < 12:
                    walk(sub, nm, nt, depth + 1)
            elif f[0] in ("2", "3", "4", "5"):
                n = {"2": 2, "3": 3, "4": 4, "5": 2}[f[0]]
                v = [float(x) for x in f[2:2 + 3 * n]]
                for k in range(n):
                    p = v[3 * k:3 * k + 3]
                    pts.append([m[r * 3] * p[0] + m[r * 3 + 1] * p[1] + m[r * 3 + 2] * p[2] + t[r] for r in range(3)])

    walk(find(f"{number}.dat"), [1, 0, 0, 0, 1, 0, 0, 0, 1], [0, 0, 0])
    xs, ys, zs = zip(*pts)
    top_y = min(ys)
    stud_planes = sorted({round(s[1]) for s in studs})
    if stud_planes and stud_planes[0] <= top_y + 5.5:  # a stud is 4 LDU; allow 1 LDU of clip above it
        # studs on top: the body runs from the stud plane down (a clip may poke out past it)
        height = round((max(ys) - stud_planes[0]) / 8)
    else:
        height = round((max(ys) - top_y) / 8)
    x0, z0 = min(xs), min(zs)
    cells = sorted({(math.floor((s[0] - x0) / 20), math.floor((s[2] - z0) / 20)) for s in studs})
    return round((max(xs) - x0) / 20), round((max(zs) - z0) / 20), height, cells, studs


def verify_against_ldraw(lib=LDRAW) -> list:
    """Re-read every modelled part from the LDraw library and compare
    footprint, height and top studs with PARTS. Returns the differences."""
    problems = []
    for (code, size, color), part in PARTS.items():
        for number in part.ldraw.split("/"):
            fx, fz, height, cells, studs = _ldraw_geometry(number, lib)
            a, b = sorted(int(n) for n in size.split("x"))
            footprint = tuple(sorted((fx, fz)))
            if code == "clip_plate":
                footprint = tuple(sorted((fx - 1, fz)))  # the clip reaches past the plate
            if footprint != (a, b):
                problems.append(f"{number} ({code}): footprint {footprint} vs {a}x{b}")
            if height != part.height:
                problems.append(f"{number} ({code}): height {height} plates vs {part.height}")
            expected = {"all": a * b, "none": 0, "edge": max(a, b) if code == "wedge_plate" else b,
                        "low_end": 1, "off_grid": 1}[part.top]
            if len(cells) != expected:
                problems.append(f"{number} ({code}): {len(cells)} top studs vs {expected}")
            if part.top == "off_grid" and studs and any(abs((s[0] % 20) - 10) < 0.5 for s in studs):
                problems.append(f"{number} ({code}): the stud is on the grid")
    return problems
