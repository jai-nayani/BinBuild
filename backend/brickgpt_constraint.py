"""Inventory constraint layer for BrickGPT designs (spike, Path A).

Path A is generate -> filter -> patch:

1. generate(category) returns a design. For this spike it is stubbed: it loads
   a pre-generated BrickGPT design from spike-constraint-kit/designs/.
2. Filter: a design fits a bin if, for every canonical brick type,
   used <= owned. Leftover pieces are fine.
3. Patch: if the design is short on some type, re-tile the footprint of a
   short brick with spare owned bricks at the same height. Counts and
   connectivity are re-checked after every swap; at most MAX_PATCH_ATTEMPTS
   swaps are tried per design.
4. Sample: plan_build draws up to N designs (DEFAULT_SAMPLES, range
   MIN_SAMPLES-MAX_SAMPLES) and returns the first that fits or patches.

Anything that still does not fit, or is not connected, comes back as a
Failure. A Failure names the shortfall and carries no design, so a rejected
design can never reach the caller. If all N samples fail, plan_build returns
the Failure whose design came closest to the bin (fewest short studs).

"Connected" means every brick is joined to every other brick through stud
contacts (overlapping footprints on adjacent layers). It is NOT a claim of
physical stability; that needs a hand-built test.

Run the full inventory x design matrix from the repo root:
    python3 -m backend.brickgpt_constraint
"""

from __future__ import annotations

import json
import random
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from math import ceil, comb
from pathlib import Path

GRID = 20  # BrickGPT works on a 20 x 20 x 20 grid
MAX_PATCH_ATTEMPTS = 20
TILINGS_PER_BRICK = 8  # fewest-piece tilings considered for each short brick
DEFAULT_SAMPLES, MIN_SAMPLES, MAX_SAMPLES = 6, 4, 8  # designs drawn per plan_build
SAMPLING_TRIALS = 100  # seeded shuffles per cell in the sampling report

BRICK_TYPES = ("1x1", "1x2", "1x4", "1x6", "1x8", "2x2", "2x4", "2x6")
CATEGORIES = (
    "basket", "bed", "bench", "birdhouse", "bookshelf", "bottle", "bowl",
    "bus", "camera", "car", "chair", "guitar", "jar", "mug", "piano", "pot",
    "sofa", "table", "tower", "train", "vessel",
)

KIT_DIR = Path(__file__).resolve().parent.parent / "spike-constraint-kit"
DESIGNS_DIR = KIT_DIR / "designs"

_LINE = re.compile(r"^(\d+)x(\d+) \((\d+),(\d+),(\d+)\)$")


def canonical(size: str) -> str:
    """'2x1' -> '1x2'. Orientation is not a different brick."""
    a, b = sorted(int(n) for n in size.lower().split("x"))
    kind = f"{a}x{b}"
    if kind not in BRICK_TYPES:
        raise ValueError(f"{size!r} is not one of the 8 supported brick types")
    return kind


@dataclass(frozen=True)
class Brick:
    """One brick: h studs along x, w studs along y, min corner at (x, y, z)."""

    h: int
    w: int
    x: int
    y: int
    z: int

    @property
    def kind(self) -> str:
        return canonical(f"{self.h}x{self.w}")

    def cells(self):
        return [(self.x + i, self.y + j) for i in range(self.h) for j in range(self.w)]

    def __str__(self) -> str:
        return f"{self.h}x{self.w} ({self.x},{self.y},{self.z})"


Design = tuple  # tuple[Brick, ...]


@dataclass
class Build:
    """A design that fits the bin and is connected."""

    category: str
    status: str  # "fit" or "patched"
    design: Design
    counts_before: dict
    counts_after: dict
    attempts: int = 0
    swaps: list = field(default_factory=list)


@dataclass
class Failure:
    """No buildable design. Deliberately has no `design` field."""

    category: str
    reason: str
    shortfall: dict  # type -> how many the generated design needed beyond the bin
    still_short: dict  # what was still short when patching stopped
    attempts: int = 0
    tried: list = field(default_factory=list)


# --- parse ------------------------------------------------------------------

def parse_design(text: str) -> Design:
    """Parse BrickGPT output: one `SIZE (x,y,z)` brick per line."""
    bricks, taken = [], set()
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        m = _LINE.match(line)
        if not m:
            raise ValueError(f"line {n}: can't parse {line!r}")
        brick = Brick(*map(int, m.groups()))
        brick.kind  # raises if outside the 8-type universe
        for x, y in brick.cells():
            if not (0 <= x < GRID and 0 <= y < GRID and 0 <= brick.z < GRID):
                raise ValueError(f"line {n}: {line} leaves the {GRID}^3 grid")
            if (x, y, brick.z) in taken:
                raise ValueError(f"line {n}: {line} overlaps another brick")
            taken.add((x, y, brick.z))
        bricks.append(brick)
    return tuple(bricks)


def load_inventory(source) -> dict:
    """Inventory as {canonical type: count}; accepts a path or a dict."""
    raw = source if isinstance(source, dict) else json.loads(Path(source).read_text())
    inventory = dict.fromkeys(BRICK_TYPES, 0)
    for size, count in raw.items():
        if not isinstance(count, int) or count < 0:
            raise ValueError(f"bad count for {size!r}: {count!r}")
        inventory[canonical(size)] += count
    return inventory


# --- filter -----------------------------------------------------------------

def count_bricks(design: Design) -> dict:
    counts = Counter(b.kind for b in design)
    return {t: counts[t] for t in BRICK_TYPES if counts[t]}


def shortfall(design: Design, inventory: dict) -> dict:
    """{type: how many short}; empty means the design fits."""
    used = count_bricks(design)
    return {t: n - inventory.get(t, 0) for t, n in used.items() if n > inventory.get(t, 0)}


def spare(design: Design, inventory: dict) -> dict:
    used = count_bricks(design)
    return {t: n - used.get(t, 0) for t, n in inventory.items() if n > used.get(t, 0)}


# --- connectivity -----------------------------------------------------------

def parts(design: Design) -> list:
    """Groups of brick indices joined by stud contacts (adjacent layers)."""
    at = {}
    for i, b in enumerate(design):
        for x, y in b.cells():
            at[(x, y, b.z)] = i
    parent = list(range(len(design)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, b in enumerate(design):
        for x, y in b.cells():
            j = at.get((x, y, b.z + 1))
            if j is not None:
                parent[root(i)] = root(j)
    groups = {}
    for i in range(len(design)):
        groups.setdefault(root(i), []).append(i)
    return sorted(groups.values(), key=len, reverse=True)


def is_connected(design: Design) -> bool:
    return len(parts(design)) == 1


# --- patch ------------------------------------------------------------------

def tilings(h: int, w: int, available: dict, limit: int = TILINGS_PER_BRICK) -> list:
    """Ways to cover an h-by-w footprint with available bricks, fewest pieces first.

    Each tiling is a list of (dh, dw, ox, oy): a dh-by-dw piece offset (ox, oy)
    from the footprint's corner. Iterative deepening on the piece count keeps
    the order exact without enumerating every tiling of a big footprint.
    """
    shapes = []
    for kind, n in available.items():
        if n <= 0:
            continue
        a, b = map(int, kind.split("x"))
        for dh, dw in {(a, b), (b, a)}:
            if dh <= h and dw <= w:
                shapes.append((dh * dw, dh, dw, kind))
    shapes.sort(reverse=True)
    if not shapes:
        return []
    biggest = shapes[0][0]
    free = [[True] * w for _ in range(h)]
    left = dict(available)
    found = []

    def fill(placed, depth, cells_free):
        if len(found) >= limit:
            return
        if cells_free == 0:
            if len(placed) == depth:
                found.append(list(placed))
            return
        if len(placed) + ceil(cells_free / biggest) > depth:
            return
        ox, oy = next((i, j) for i in range(h) for j in range(w) if free[i][j])
        for area, dh, dw, kind in shapes:
            if left[kind] == 0 or ox + dh > h or oy + dw > w:
                continue
            spots = [(ox + i, oy + j) for i in range(dh) for j in range(dw)]
            if not all(free[i][j] for i, j in spots):
                continue
            for i, j in spots:
                free[i][j] = False
            left[kind] -= 1
            placed.append((dh, dw, ox, oy))
            fill(placed, depth, cells_free - area)
            placed.pop()
            left[kind] += 1
            for i, j in spots:
                free[i][j] = True

    for depth in range(2, h * w + 1):
        fill([], depth, h * w)
        if len(found) >= limit:
            break
    return found[:limit]


def _studs(kind: str) -> int:
    a, b = map(int, kind.split("x"))
    return a * b


def _hopeless(design: Design, inventory: dict):
    """Why no patch can work, found before spending any attempts; else None."""
    short = shortfall(design, inventory)
    avail = spare(design, inventory)
    need = sum(_studs(t) * n for t, n in short.items())
    have = sum(_studs(t) * n for t, n in avail.items())
    if need > have:
        return f"short bricks cover {need} studs but spare pieces only {have}"
    stuck = [t for t in short if not tilings(*map(int, t.split("x")), avail, limit=1)]
    if stuck:
        return f"no spare pieces can tile a {'/'.join(stuck)} footprint"
    return None


def _candidates(design: Design, inventory: dict) -> list:
    """Every (brick index, replacement pieces) swap worth trying, best first.

    A tiling is skipped (not counted as an attempt) if one of its pieces would
    have no stud contact above or below: it could never be connected.
    """
    short = shortfall(design, inventory)
    avail = spare(design, inventory)
    occupied = {(x, y, b.z) for b in design for x, y in b.cells()}
    found = []
    for i, b in enumerate(design):
        if b.kind not in short:
            continue
        for tiling in tilings(b.h, b.w, avail):
            pieces = [Brick(dh, dw, b.x + ox, b.y + oy, b.z) for dh, dw, ox, oy in tiling]
            contacts = [
                sum((x, y, b.z + dz) in occupied for x, y in p.cells() for dz in (-1, 1))
                for p in pieces
            ]
            if min(contacts) == 0:
                continue
            found.append(((len(pieces), -sum(contacts), i), i, pieces))
    found.sort(key=lambda c: c[0])
    return [(i, pieces) for _, i, pieces in found]


def patch(design: Design, inventory: dict, max_attempts: int = MAX_PATCH_ATTEMPTS):
    """Try to re-tile short bricks until the design fits.

    Returns (patched design or None, attempts used, log of what was tried,
    what was still short when it stopped). The half-patched design is never
    returned.
    """
    attempts, log = 0, []
    while shortfall(design, inventory):
        hopeless = _hopeless(design, inventory)
        if hopeless:
            log.append(hopeless)
            return None, attempts, log, shortfall(design, inventory)
        candidates = _candidates(design, inventory)
        if not candidates:
            log.append("every way to re-tile a short brick leaves a piece floating")
            return None, attempts, log, shortfall(design, inventory)
        for i, pieces in candidates:
            if attempts >= max_attempts:
                log.append(f"hit the {max_attempts}-attempt cap")
                return None, attempts, log, shortfall(design, inventory)
            attempts += 1
            trial = design[:i] + design[i + 1:] + tuple(pieces)
            swap = f"{design[i]} -> {' + '.join(f'{p.h}x{p.w}' for p in pieces)}"
            # Counts can't go over (tilings only draw on spare), but re-check anyway.
            short_now = shortfall(design, inventory)
            over = {t: n for t, n in shortfall(trial, inventory).items()
                    if n > short_now.get(t, 0)}
            if over:
                log.append(f"attempt {attempts}: {swap}: over inventory on {over}")
            elif not is_connected(trial):
                log.append(f"attempt {attempts}: {swap}: disconnects the build")
            else:
                log.append(f"attempt {attempts}: {swap}: ok")
                design = trial
                break
        else:
            log.append("every candidate swap disconnects the build")
            return None, attempts, log, shortfall(design, inventory)
    return design, attempts, log, {}


# --- generate + the whole pipeline ------------------------------------------

def generate(category: str, designs_dir: Path = DESIGNS_DIR) -> Design:
    """Generate step. STUB: loads a pre-generated BrickGPT design from disk.

    Live BrickGPT plugs in here: same signature, same return type.
    """
    if category not in CATEGORIES:
        raise ValueError(f"BrickGPT doesn't know {category!r}")
    path = Path(designs_dir) / f"{category}.txt"
    if not path.exists():
        raise FileNotFoundError(f"no pre-generated design for {category!r} in {designs_dir}")
    return parse_design(path.read_text())


def fit_design(design: Design, inventory: dict, category: str = "",
               max_attempts: int = MAX_PATCH_ATTEMPTS):
    """Filter, then patch. Returns a Build or a Failure, never a rejected design."""
    before = count_bricks(design)
    short = shortfall(design, inventory)
    if not design:
        return Failure(category, "empty design", short, short)
    groups = parts(design)
    if len(groups) > 1:
        sizes = "+".join(str(len(g)) for g in groups)
        return Failure(category, f"not connected: {len(groups)} separate parts ({sizes} bricks)",
                       short, short)
    if not short:
        return Build(category, "fit", design, before, before)
    patched, attempts, log, still = patch(design, inventory, max_attempts)
    if patched is None:
        verdict = "not patchable" if attempts == 0 else "patch failed"
        return Failure(category, f"{verdict}: {log[-1]}", short, still, attempts, log)
    return Build(category, "patched", patched, before, count_bricks(patched), attempts,
                 [line for line in log if line.endswith(": ok")])


def short_studs(counts: dict) -> int:
    """Size of a shortfall in studs, so a missing 2x6 outweighs a missing 1x1."""
    return sum(_studs(t) * n for t, n in counts.items())


def plan_build(category: str, inventory: dict, generate=generate,
               max_attempts: int = MAX_PATCH_ATTEMPTS, samples: int = DEFAULT_SAMPLES):
    """generate -> filter -> patch, drawing up to `samples` designs for one category.

    Returns the first sample that fits or patches; later samples are never
    generated. If every sample fails, returns the Failure with the fewest short
    studs in its generated design (ties: fewest still short after patching,
    then the earlier sample), with that sample's own attempt log. A design
    that fits on counts but is not connected has 0 short studs, so it ranks
    first among failures.

    A repeated design (the stub returns the same one every call) still counts
    as a draw, but its result is reused rather than patched again.
    """
    if not MIN_SAMPLES <= samples <= MAX_SAMPLES:
        raise ValueError(f"samples must be {MIN_SAMPLES}-{MAX_SAMPLES}, got {samples}")
    failures, seen = [], {}
    for _ in range(samples):
        design = tuple(generate(category))
        if design not in seen:
            seen[design] = fit_design(design, inventory, category, max_attempts)
        result = seen[design]
        if isinstance(result, Build):
            return result
        failures.append(result)
    return min(failures, key=lambda f: (short_studs(f.shortfall), short_studs(f.still_short)))


# --- matrix runner ------------------------------------------------------------

def _fmt(counts: dict) -> str:
    return " ".join(f"{t}:{n}" for t, n in counts.items() if n) or "-"


def main() -> None:
    designs = sorted(p.stem for p in DESIGNS_DIR.glob("*.txt"))
    for inv_path in sorted(KIT_DIR.glob("test-inventory-*.json")):
        inventory = load_inventory(inv_path)
        print(f"\n### {inv_path.name} ({sum(inventory.values())} bricks: {_fmt(inventory)})\n")
        print("| design | bricks | result | attempts | ms | counts before | counts after / shortfall |")
        print("|---|---|---|---|---|---|---|")
        for category in designs:
            start = time.perf_counter()
            design = generate(category)
            result = fit_design(design, inventory, category)
            ms = (time.perf_counter() - start) * 1000
            if isinstance(result, Build):
                outcome, after = result.status, _fmt(result.counts_after)
            else:
                outcome = f"FAILED: {result.reason}"
                after = f"short {_fmt(result.shortfall)}" if result.shortfall else "-"
                if result.still_short != result.shortfall:
                    after += f"; still short {_fmt(result.still_short)} after patching"
            print(f"| {category} | {len(design)} | {outcome} | {result.attempts} | {ms:.1f} "
                  f"| {_fmt(count_bricks(design))} | {after} |")
    sampling_report()


def sampling_report(trials: int = SAMPLING_TRIALS) -> None:
    """plan_build with N samples drawn from the kit designs in a random order.

    The stub has one design per category, so N samples of one category are all
    the same design. As a stand-in for N different live samples, each trial
    shuffles the 10 kit designs and hands them out in that order, ignoring the
    category: this measures "build anything from this bin", not one category.
    """
    designs = [generate(p.stem) for p in sorted(DESIGNS_DIR.glob("*.txt"))]
    print(f"\n### Sampling: {len(designs)} kit designs in random order, "
          f"{trials} seeded shuffles per row\n")
    print("| inventory | N | builds found | exact rate | mean draws | mean ms |")
    print("|---|---|---|---|---|---|")
    for inv_path in sorted(KIT_DIR.glob("test-inventory-*.json")):
        inventory = load_inventory(inv_path)
        buildable = sum(isinstance(fit_design(d, inventory), Build) for d in designs)
        for n in range(MIN_SAMPLES, MAX_SAMPLES + 1):
            rng = random.Random(n)  # same shuffles for every inventory at a given N
            found = draws = 0
            start = time.perf_counter()
            for _ in range(trials):
                order = rng.sample(designs, len(designs))
                remaining = iter(order)
                result = plan_build("any", inventory, lambda _c: next(remaining), samples=n)
                found += isinstance(result, Build)
                draws += len(order) - sum(1 for _ in remaining)  # draws = designs consumed
            ms = (time.perf_counter() - start) * 1000 / trials
            # A trial succeeds iff one of its first n designs is buildable.
            exact = 1 - comb(len(designs) - buildable, n) / comb(len(designs), n)
            print(f"| {inv_path.name} | {n} | {found}/{trials} | {exact:.1%} "
                  f"| {draws / trials:.2f} | {ms:.1f} |")


if __name__ == "__main__":
    main()
