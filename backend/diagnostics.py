"""One shape for every validator failure: how many, which part, exactly where.

    1 floating: Brick 2x4 @ Position(2,1,3)
    1 collision: Plate 2x1 @ Position(3,0,2) overlaps Brick 2x1 @ Position(3,0,1) at Position(3,0,2)
    1 off-grid: Plate 1x2 @ Position(19,19,0) — covers x 19-19, y 19-20; the base is 0-19 each way
    1 over-count: Brick 1x2 (orange) @ Position(3,0,1), Position(3,0,4), Position(0,1,0) — uses 3, owns 2
    1 bad stacking: Round Plate 1x1 @ Position(0,0,2) — sits on Jumper Plate 2x1 @ Position(0,0,1), ...

The count leads, then the check, then each part with its grid position, then
why. A position is the piece's minimum corner in the design's own grid (x
and y in studs, z in the design's layer unit), so the same (x,y,z) finds the
line in the design text. The validators (backend/wonder_design.py,
backend/brickgpt_constraint.py, backend/manual_verify.py) build every line
here so the shape can't drift. Standard library only.
"""


def position(x, y, z) -> str:
    return f"Position({x},{y},{z})"


def at(part, x, y, z) -> str:
    """'Brick 2x4 @ Position(2,1,3)'."""
    return f"{part} @ {position(x, y, z)}"


def many(part, spots) -> str:
    """One kind of part at several positions: 'Brick 1x2 @ Position(..), Position(..)'.
    With no positions (none placed), just the part."""
    return f"{part} @ " + ", ".join(position(*s) for s in spots) if spots else part


def line(count, check, where, why="") -> str:
    """'1 floating: Brick 2x4 @ Position(2,1,3)', plus ' — why' when given."""
    return f"{count} {check}: {where}" + (f" — {why}" if why else "")
