"""A fresh demo database for the public deploy.

The kit's 50 pieces as one confirmed batch (the kit batch after review and
confirm, INVENTORY-LOOP.md; the same list the tests use), and nothing else:
no photos, no builds, nothing from a local binbuild.db. The pieces go in the
way a person adds pieces by hand: a batch with no photos, the pieces added in
review, then confirmed. deploy/modal_app.py calls seed() when a container
starts, so every container starts from this. Standard library only.
"""

from contextlib import closing
from pathlib import Path

from . import inventory_db as db

BATCH_ID = "20261102-000000-de0000"
CREATED_AT = "2026-11-02T00:00:00+00:00"

# family, shape, size, colour, quantity, BrickGPT type (plain bricks only)
KIT = [
    ("brick", "headlight brick", "1x1", "light_bluish_gray", 2, None),
    ("brick", "round brick", "1x1", "light_bluish_gray", 4, None),
    ("brick", "tall 1x1 brick with 2 studs on side", "1x1", "lime", 2, None),
    ("brick", "brick", "1x2", "orange", 2, "1x2"),
    ("brick", "brick with 4 studs on side", "1x4", "blue", 2, None),
    ("plate", "round plate", "1x1", "lime", 4, None),
    ("plate", "plate", "1x2", "dark_purple", 4, None),
    ("plate", "plate with clip", "1x2", "lime", 2, None),
    ("plate", "plate", "1x2", "trans_clear", 3, None),
    ("plate", "jumper plate", "1x2", "white", 2, None),
    ("plate", "hinge plate", "1x4", "black", 1, None),
    ("plate", "plate", "1x6", "lime", 1, None),
    ("plate", "plate", "2x2", "magenta", 2, None),
    ("plate", "plate", "2x4", "medium_azure", 2, None),
    ("plate", "wedge plate", "2x4", "white", 2, None),
    ("slope", "1x1 slope (cheese)", "1x1", "medium_blue", 2, None),
    ("slope", "curved slope", "1x2", "black", 4, None),
    ("slope", "curved slope", "1x2", "medium_azure", 2, None),
    ("slope", "curved slope", "1x3", "light_bluish_gray", 2, None),
    ("tile", "round printed tile", "1x1", "white", 4, None),
    ("tile", "tile with 2 studs on edge", "2x2", "white", 1, None),
]


def seed(path=None) -> bool:
    """Create the demo database at path (default: inventory_db.DB_PATH).
    Returns False, changing nothing, if a database is already there."""
    path = Path(path or db.DB_PATH)
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(db.connect(path)) as conn:
        db.register_batch(conn, BATCH_ID, CREATED_AT, photos=[])
        db.review_batch(conn, BATCH_ID, additions=[
            {"family": family, "shape": shape, "size": size, "color": color, "plain": bool(kind), "count": n}
            for family, shape, size, color, n, kind in KIT])
        db.confirm_batch(conn, BATCH_ID)
    return True
