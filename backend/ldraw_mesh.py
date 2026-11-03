"""Real part shapes for the booklet pictures, read from the LDraw library.

`python -m backend.ldraw_mesh` flattens the parts below from the LDraw library
(~/Downloads/ldraw) into backend/ldraw_kit.json.gz: per part, its triangles,
edge lines and conditional lines (the silhouettes of round surfaces), in
LDraw units with LDraw axes (y points down, a stud is 20 wide, a plate 8
tall). The deploy has no LDraw library, so that file is committed.

Triangles come out counter-clockwise seen from outside (BFC), so a picture can
drop the faces turned away from the camera; faces from files that are not
BFC-certified are marked two-sided. Faces that look straight down are dropped:
the pictures always look from above.

LDraw parts: ldraw.org, CC BY 4.0.
"""

import gzip
import json
import sys
from pathlib import Path

MESHES = Path(__file__).parent / "ldraw_kit.json.gz"

# The kit's parts, the plain sizes BrickGPT and the known sets use, and the
# printed eye tile. Anything else is drawn from the primitives (see ldraw_render).
PARTS = [
    "3004", "3062b", "4070", "32952", "30414", "3023b", "3666", "3022", "3020", "6141", "63868",
    "3794b", "41769a", "41770a", "54200", "11477", "6091", "50950", "98138", "98138p07", "33909",
    "3005", "3622", "3010", "3009", "3008", "3003", "3002", "3001", "2456", "3007",
    "3024", "3623", "3710", "3460", "3021", "3795", "3034",
    "3070b", "3069b", "63864", "2431", "3068b",
]
PRIMITIVES = ["stud.dat", "box5.dat"]


def _ldconfig(lib):
    """LDraw colour code -> (face hex, edge hex)."""
    colors = {}
    for line in (lib / "LDConfig.ldr").read_text(errors="ignore").splitlines():
        f = line.split()
        if len(f) > 7 and f[1] == "!COLOUR":
            colors[int(f[f.index("CODE") + 1])] = (f[f.index("VALUE") + 1], f[f.index("EDGE") + 1])
    return colors


class _Library:
    def __init__(self, lib):
        self.lib = lib
        self.colors = _ldconfig(lib)
        self.cache = {}

    def lines(self, name):
        name = name.strip().replace("\\", "/")
        if name not in self.cache:
            for d in ("parts", "p"):
                for n in (name, name.lower()):
                    if (self.lib / d / n).exists():
                        self.cache[name] = (self.lib / d / n).read_text(errors="ignore").splitlines()
                        break
                if name in self.cache:
                    break
            else:
                raise FileNotFoundError(name)
        return self.cache[name]

    def color(self, code, current):
        """A colour token: "main", "main_edge" or "#rrggbb"."""
        if code == "16":
            return current
        if code == "24":
            if current == "main":
                return "main_edge"
            edge = [e for v, e in self.colors.values() if v.lower() == current.lower()]
            return edge[0] if edge else "#333333"
        if code.lower().startswith("0x2"):
            return "#" + code[3:]
        return self.colors.get(int(code), ("#ff00ff", "#333333"))[0]


def _mat(m, v):
    return [m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
            m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
            m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2]]


def _mul(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(3)) for c in range(3)] for r in range(3)]


def _det(m):
    return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
            - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))


def flatten(lib: _Library, name):
    """One part as {"tris": [...], "lines": [...], "cond": [...]}: each entry
    is (colour, points, two_sided) for tris, (colour, points) for the rest."""
    out = {"tris": [], "lines": [], "cond": []}

    def walk(name, m, t, color, invert, certified_chain, depth):
        certified, ccw, invert_next = False, True, False
        for raw in lib.lines(name):
            f = raw.split()
            if not f:
                continue
            if f[0] == "0":
                if len(f) > 2 and f[1] == "BFC":
                    opts = f[2:]
                    certified = certified or "CERTIFY" in opts
                    if "NOCERTIFY" in opts:
                        certified = False
                    ccw = False if "CW" in opts else True if "CCW" in opts else ccw
                    invert_next = invert_next or "INVERTNEXT" in opts
                continue
            col = lib.color(f[1], color)
            if f[0] == "1":
                v = [float(x) for x in f[2:14]]
                local = [v[3:6], v[6:9], v[9:12]]
                nt = [a + b for a, b in zip(_mat(m, v[0:3]), t)]
                if depth < 16:
                    walk(" ".join(f[14:]), _mul(m, local), nt, col, invert ^ invert_next,
                         certified_chain and certified, depth + 1)
                invert_next = False
                continue
            n = {"2": 2, "3": 3, "4": 4, "5": 4}.get(f[0])
            if not n:
                continue
            v = [float(x) for x in f[2:2 + 3 * n]]
            pts = [[a + b for a, b in zip(_mat(m, v[3 * k:3 * k + 3]), t)] for k in range(n)]
            if f[0] == "2":
                out["lines"].append((col, pts))
            elif f[0] == "5":
                out["cond"].append((col, pts))
            else:
                flip = (_det(m) < 0) ^ invert ^ (not ccw)
                if flip:
                    pts = pts[::-1]
                faces = [pts] if n == 3 else [pts[:3], [pts[0], pts[2], pts[3]]]
                for face in faces:
                    out["tris"].append((col, face, not (certified_chain and certified)))

    walk(name, [[1, 0, 0], [0, 1, 0], [0, 0, 1]], [0, 0, 0], "main", False, True, 0)
    return out


def _normal(face):
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = face
    ux, uy, uz, vx, vy, vz = bx - ax, by - ay, bz - az, cx - ax, cy - ay, cz - az
    return uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx


def pack(flat) -> dict:
    """Compact JSON form: flat coordinate lists rounded to 0.01 LDU, colours
    as indices into a shared palette (-1 main, -2 main edge)."""
    palette = []

    def ci(col):
        if col == "main":
            return -1
        if col == "main_edge":
            return -2
        if col not in palette:
            palette.append(col)
        return palette.index(col)

    tris, tc, two = [], [], []
    for col, face, two_sided in flat["tris"]:
        nx, ny, nz = _normal(face)
        length = (nx * nx + ny * ny + nz * nz) ** 0.5
        if length < 1e-9:
            continue
        if not two_sided and ny / length > 0.999:  # outward and straight down (LDraw y points down)
            continue
        if two_sided:
            two.append(len(tc))
        tris += [round(c, 2) for p in face for c in p]
        tc.append(ci(col))
    lines = [round(c, 2) for _, pts in flat["lines"] for p in pts for c in p]
    cond = [round(c, 2) for _, pts in flat["cond"] for p in pts for c in p]
    return {"tris": tris, "tc": tc, "two": two, "lines": lines, "lc": [ci(c) for c, _ in flat["lines"]],
            "cond": cond, "cc": [ci(c) for c, _ in flat["cond"]], "palette": palette}


def build(lib_path, out=MESHES):
    lib = _Library(Path(lib_path))
    meshes = {}
    for name in PARTS:
        meshes[name] = pack(flatten(lib, f"{name}.dat"))
    for name in PRIMITIVES:
        meshes[name] = pack(flatten(lib, name))
    data = {"source": "LDraw parts library (ldraw.org), CC BY 4.0", "meshes": meshes}
    with gzip.open(out, "wt", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"))
    return meshes


if __name__ == "__main__":
    from .wonder_design import LDRAW
    lib = Path(sys.argv[1]) if len(sys.argv) > 1 else LDRAW
    meshes = build(lib)
    for name, m in meshes.items():
        print(f"{name:10} {len(m['tc']):5} tris {len(m['lc']):4} lines {len(m['cc']):4} cond")
    print(MESHES, MESHES.stat().st_size, "bytes")
