"""SQLite inventory: batches, their photos, detections, confirmed pieces, builds.

The database is binbuild.db in the repo root (git-ignored); BINBUILD_DB
overrides the path. Standard library only.

A batch moves through three states:
    uploaded    photos on disk and registered here
    classified  detections proposed (by Spark or by hand), open for review
    confirmed   detections copied into inventory_items; review is locked

Idempotency:
- registering a batch id twice returns the existing batch;
- a byte-identical re-upload of the same photos is found by its fingerprint;
- confirming a confirmed batch adds nothing and says so;
- undo can name the batch it expects to undo, so a retried undo can't remove
  a second batch.
Undo removes the most recently confirmed batch's inventory rows and reopens
the batch for review, so it can be corrected and confirmed again.
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import inventory_vocab as vocab

DB_PATH = Path(os.environ.get("BINBUILD_DB", Path(__file__).resolve().parent.parent / "binbuild.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS batches (
    id             TEXT PRIMARY KEY,
    created_at     TEXT NOT NULL,
    fingerprint    TEXT UNIQUE,       -- sha256 over the photos' sha256s, in view order
    status         TEXT NOT NULL DEFAULT 'uploaded'
                   CHECK (status IN ('uploaded', 'classified', 'confirmed')),
    classifier     TEXT,              -- e.g. 'spark:meta-models/muse-spark-open-1026 + stub-whole-photo'
    classified_at  TEXT,
    classify_error TEXT,
    confirmed_at   TEXT,
    confirm_seq    INTEGER UNIQUE,    -- confirmation order, for undo
    undone_at      TEXT
);
CREATE TABLE IF NOT EXISTS batch_photos (
    id       INTEGER PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
    view     TEXT NOT NULL,
    file     TEXT NOT NULL,
    sha256   TEXT NOT NULL,
    bytes    INTEGER NOT NULL,
    UNIQUE (batch_id, view)
);
CREATE TABLE IF NOT EXISTS detections (
    id             INTEGER PRIMARY KEY,
    batch_id       TEXT NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
    photo_id       INTEGER REFERENCES batch_photos(id),
    region         TEXT,              -- JSON: {"bbox": [x0, y0, x1, y1], "point": [x, y] | null}
    source         TEXT NOT NULL CHECK (source IN ('spark', 'manual')),
    family         TEXT NOT NULL,
    shape          TEXT NOT NULL DEFAULT '',
    size           TEXT,              -- 'WxL' in studs, smaller side first
    color          TEXT NOT NULL,
    plain          INTEGER NOT NULL DEFAULT 0,  -- 1: standard part, nothing added
    generator_type TEXT,              -- one of the 8 BrickGPT types, else NULL
    count          INTEGER NOT NULL CHECK (count >= 1),
    confidence     REAL,
    status         TEXT NOT NULL DEFAULT 'proposed'
                   CHECK (status IN ('proposed', 'accepted', 'corrected', 'rejected')),
    original       TEXT,              -- JSON: the proposed values before the first correction
    raw            TEXT,              -- JSON: the model's item as returned
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS detections_batch ON detections (batch_id);
CREATE TABLE IF NOT EXISTS inventory_items (
    id             INTEGER PRIMARY KEY,
    batch_id       TEXT NOT NULL REFERENCES batches(id),
    detection_id   INTEGER UNIQUE REFERENCES detections(id),
    family         TEXT NOT NULL,
    shape          TEXT NOT NULL DEFAULT '',
    size           TEXT,
    color          TEXT NOT NULL,
    generator_type TEXT,
    quantity       INTEGER NOT NULL CHECK (quantity >= 1),
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS inventory_items_batch ON inventory_items (batch_id);
CREATE TABLE IF NOT EXISTS builds (
    id                 INTEGER PRIMARY KEY,
    created_at         TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'requested',
    request            TEXT NOT NULL,  -- JSON: what was asked for
    inventory_snapshot TEXT,           -- JSON: generator-ready counts the build may use
    result             TEXT            -- JSON: the generated build
);
"""

EDITABLE = ("family", "shape", "size", "color", "plain", "count")


class NotFound(LookupError):
    pass


class Conflict(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(path=None) -> sqlite3.Connection:
    """Open the database (creating the tables if needed). Autocommit; writes
    that touch several rows go through _write()."""
    conn = sqlite3.connect(str(path or DB_PATH), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


@contextmanager
def _write(conn):
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def _batch_row(conn, batch_id):
    row = conn.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
    if row is None:
        raise NotFound(f"no batch {batch_id!r}")
    return row


def get_batch(conn, batch_id) -> dict:
    return dict(_batch_row(conn, batch_id))


def batch_by_fingerprint(conn, fingerprint):
    row = conn.execute("SELECT * FROM batches WHERE fingerprint = ?", (fingerprint,)).fetchone()
    return dict(row) if row else None


def register_batch(conn, batch_id, created_at, photos, fingerprint=None):
    """Record an uploaded batch. photos: dicts with view, file, sha256, bytes.
    Returns (batch, created); an id already registered is returned unchanged."""
    with _write(conn):
        row = conn.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
        if row is not None:
            return dict(row), False
        conn.execute(
            "INSERT INTO batches (id, created_at, fingerprint) VALUES (?, ?, ?)",
            (batch_id, created_at, fingerprint),
        )
        conn.executemany(
            "INSERT INTO batch_photos (batch_id, view, file, sha256, bytes) VALUES (?, ?, ?, ?, ?)",
            [(batch_id, p["view"], p["file"], p["sha256"], p["bytes"]) for p in photos],
        )
    return get_batch(conn, batch_id), True


def batch_photos(conn, batch_id) -> list:
    rows = conn.execute("SELECT * FROM batch_photos WHERE batch_id = ? ORDER BY id", (batch_id,))
    return [dict(r) for r in rows]


def _detection_values(d) -> dict:
    """Validate one detection's piece fields and derive its generator type."""
    family = vocab.check_family(d["family"])
    color = vocab.check_color(d["color"])
    size = vocab.check_size(d.get("size"))
    plain = bool(d.get("plain", False))
    count = int(d.get("count", 1))
    if count < 1:
        raise ValueError(f"count must be at least 1; got {count}")
    return {
        "family": family, "shape": str(d.get("shape") or "")[:80], "size": size, "color": color,
        "plain": int(plain), "generator_type": vocab.generator_type(family, size, plain), "count": count,
    }


def _insert_detection(conn, batch_id, d, source, status):
    v = _detection_values(d)
    photo_id = None
    if d.get("photo_view"):
        row = conn.execute(
            "SELECT id FROM batch_photos WHERE batch_id = ? AND view = ?", (batch_id, d["photo_view"])
        ).fetchone()
        photo_id = row["id"] if row else None
    region = d.get("region")
    raw = d.get("raw")
    conn.execute(
        "INSERT INTO detections (batch_id, photo_id, region, source, family, shape, size, color, plain,"
        " generator_type, count, confidence, status, raw, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (batch_id, photo_id, json.dumps(region) if region is not None else None, source,
         v["family"], v["shape"], v["size"], v["color"], v["plain"], v["generator_type"], v["count"],
         d.get("confidence"), status, json.dumps(raw) if raw is not None else None, _now()),
    )


def replace_detections(conn, batch_id, detections, classifier):
    """Store a classifier's proposals for a batch, replacing earlier ones."""
    with _write(conn):
        if _batch_row(conn, batch_id)["status"] == "confirmed":
            raise Conflict(f"batch {batch_id} is confirmed; undo it before classifying again")
        conn.execute("DELETE FROM detections WHERE batch_id = ?", (batch_id,))
        for d in detections:
            _insert_detection(conn, batch_id, d, "spark", "proposed")
        conn.execute(
            "UPDATE batches SET status = 'classified', classifier = ?, classified_at = ?,"
            " classify_error = NULL WHERE id = ?",
            (classifier, _now(), batch_id),
        )


def record_classify_error(conn, batch_id, message):
    conn.execute("UPDATE batches SET classify_error = ? WHERE id = ?", (str(message)[:2000], batch_id))


def _detection_dict(row) -> dict:
    d = dict(row)
    d["plain"] = bool(d["plain"])
    for key in ("region", "original", "raw"):
        d[key] = json.loads(d[key]) if d[key] else None
    return d


def review_batch(conn, batch_id, corrections=(), additions=()):
    """Apply a person's review. corrections: dicts with detection_id plus any
    of EDITABLE and/or status 'accepted' / 'rejected'. additions: pieces the
    classifier missed, same fields as a detection."""
    with _write(conn):
        batch = _batch_row(conn, batch_id)
        if batch["status"] == "confirmed":
            raise Conflict(f"batch {batch_id} is confirmed; undo it before changing the review")
        for c in corrections:
            row = conn.execute(
                "SELECT * FROM detections WHERE id = ? AND batch_id = ?", (c["detection_id"], batch_id)
            ).fetchone()
            if row is None:
                raise NotFound(f"no detection {c['detection_id']} in batch {batch_id}")
            current = {k: row[k] for k in EDITABLE}
            current["plain"] = bool(current["plain"])
            wanted = dict(current, **{k: c[k] for k in EDITABLE if c.get(k) is not None})
            values = _detection_values(wanted)
            values["plain"] = bool(values["plain"])
            changed = any(values[k] != current[k] for k in EDITABLE)
            original = row["original"]
            if changed and original is None:
                original = json.dumps(current)
            if c.get("status") == "rejected":
                status = "rejected"
            elif original is not None:
                status = "corrected"
            else:
                status = "accepted"
            conn.execute(
                "UPDATE detections SET family = ?, shape = ?, size = ?, color = ?, plain = ?,"
                " generator_type = ?, count = ?, status = ?, original = ? WHERE id = ?",
                (values["family"], values["shape"], values["size"], values["color"], int(values["plain"]),
                 values["generator_type"], values["count"], status, original, row["id"]),
            )
        for a in additions:
            _insert_detection(conn, batch_id, a, "manual", "accepted")
        if additions and batch["status"] == "uploaded":
            conn.execute("UPDATE batches SET status = 'classified' WHERE id = ?", (batch_id,))
    return batch_review(conn, batch_id)


def batch_review(conn, batch_id) -> dict:
    batch = get_batch(conn, batch_id)
    detections = [
        _detection_dict(r)
        for r in conn.execute("SELECT * FROM detections WHERE batch_id = ? ORDER BY id", (batch_id,))
    ]
    kept = [d for d in detections if d["status"] != "rejected"]
    return {
        "batch": batch,
        "photos": batch_photos(conn, batch_id),
        "detections": detections,
        "pieces": sum(d["count"] for d in kept),
        "corrections": sum(1 for d in detections if d["status"] in ("corrected", "rejected") or d["source"] == "manual"),
    }


def confirm_batch(conn, batch_id) -> dict:
    """Copy a batch's kept detections into the inventory. Safe to repeat."""
    with _write(conn):
        batch = _batch_row(conn, batch_id)
        if batch["status"] == "confirmed":
            (pieces,) = conn.execute(
                "SELECT COALESCE(SUM(quantity), 0) FROM inventory_items WHERE batch_id = ?", (batch_id,)
            ).fetchone()
            return {"batch_id": batch_id, "already_confirmed": True, "pieces_added": 0, "pieces_in_batch": pieces}
        rows = conn.execute(
            "SELECT * FROM detections WHERE batch_id = ? AND status != 'rejected' ORDER BY id", (batch_id,)
        ).fetchall()
        if not rows:
            raise Conflict(f"batch {batch_id} has no pieces to confirm; classify it or add pieces first")
        now = _now()
        conn.executemany(
            "INSERT INTO inventory_items (batch_id, detection_id, family, shape, size, color, generator_type,"
            " quantity, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(batch_id, r["id"], r["family"], r["shape"], r["size"], r["color"], r["generator_type"],
              r["count"], now) for r in rows],
        )
        conn.execute("UPDATE detections SET status = 'accepted' WHERE batch_id = ? AND status = 'proposed'", (batch_id,))
        (seq,) = conn.execute("SELECT COALESCE(MAX(confirm_seq), 0) + 1 FROM batches").fetchone()
        conn.execute(
            "UPDATE batches SET status = 'confirmed', confirmed_at = ?, confirm_seq = ?, undone_at = NULL"
            " WHERE id = ?",
            (now, seq, batch_id),
        )
    pieces = sum(r["count"] for r in rows)
    return {"batch_id": batch_id, "already_confirmed": False, "pieces_added": pieces, "pieces_in_batch": pieces}


def undo_last_batch(conn, expected_batch_id=None):
    """Take the most recently confirmed batch back out of the inventory and
    reopen it for review. Returns None when nothing is confirmed. With
    expected_batch_id, refuses (Conflict) unless that batch is the last one."""
    with _write(conn):
        row = conn.execute(
            "SELECT * FROM batches WHERE status = 'confirmed' ORDER BY confirm_seq DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        if expected_batch_id is not None and row["id"] != expected_batch_id:
            raise Conflict(f"the last confirmed batch is {row['id']}, not {expected_batch_id}")
        (pieces,) = conn.execute(
            "SELECT COALESCE(SUM(quantity), 0) FROM inventory_items WHERE batch_id = ?", (row["id"],)
        ).fetchone()
        conn.execute("DELETE FROM inventory_items WHERE batch_id = ?", (row["id"],))
        conn.execute(
            "UPDATE batches SET status = 'classified', confirmed_at = NULL, confirm_seq = NULL, undone_at = ?"
            " WHERE id = ?",
            (_now(), row["id"]),
        )
    return {"batch_id": row["id"], "pieces_removed": pieces}


def inventory_summary(conn) -> dict:
    """The confirmed inventory in two layers: the 8 generator-ready brick types
    by colour, then everything else by broad family and colour, with unknown
    pieces on their own."""
    rows = conn.execute(
        "SELECT family, shape, size, color, generator_type, SUM(quantity) AS quantity FROM inventory_items"
        " GROUP BY family, shape, size, color, generator_type ORDER BY family, size, color, shape"
    ).fetchall()
    generator = {t: {"total": 0, "colors": {}} for t in vocab.GENERATOR_TYPES}
    families = {}
    unknown = {"total": 0, "colors": {}}
    for r in rows:
        if r["generator_type"]:
            group = generator[r["generator_type"]]
        elif r["family"] == "unknown":
            group = unknown
        else:
            group = families.setdefault(r["family"], {"total": 0, "colors": {}})
        group["total"] += r["quantity"]
        group["colors"][r["color"]] = group["colors"].get(r["color"], 0) + r["quantity"]
    (confirmed,) = conn.execute("SELECT COUNT(*) FROM batches WHERE status = 'confirmed'").fetchone()
    gen_total = sum(g["total"] for g in generator.values())
    other_total = sum(f["total"] for f in families.values())
    return {
        "total_pieces": gen_total + other_total + unknown["total"],
        "batches_confirmed": confirmed,
        "generator_ready": {"total": gen_total, "types": generator},
        "other": {"total": other_total, "families": dict(sorted(families.items()))},
        "unknown": unknown,
        "items": [dict(r) for r in rows],
    }
