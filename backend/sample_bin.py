"""The sample bin: 5 sample photos and their already-verified pieces.

The photos are the Oct 28 kit batch (20261028-192429-119901: top, front,
right, back, left of the 50-piece scatter), turned upright, shrunk and
re-compressed as small demo assets with no camera metadata. The four side
views are cropped to the tabletop: the room behind the pieces (screens, a
bed, photos on the wall, a person's arm) is left out of a public demo. Only
the top view is ever drawn on, and it is kept whole. The pieces are
the verified result of the inventory-loop spike on those photos: Muse Spark's
recorded reply (tests/fixtures/kit-batch-recorded.json) plus the 13
corrections made in its review. Both are pre-computed into backend/sample/,
so loading the sample makes no classification call and no paid API call.

"Use sample images" in the app loads it as one batch, ready for review:
the 5 photos (all passed the photo check when they were taken), the pieces as
proposals with the review's corrections applied. From there the normal flow
runs: review, confirm, "What can I build?". Loading is idempotent: the sample
is one fixed batch, so loading it twice never adds its pieces twice.

Rebuild the assets (needs the original batch under data/, git-ignored):
    python -m backend.sample_bin make
"""

import hashlib
import io
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import inventory_db as db

HERE = Path(__file__).resolve().parent
SAMPLE_DIR = HERE / "sample"
MANIFEST = SAMPLE_DIR / "kit.json"
SOURCE_BATCH = "20261028-192429-119901"
BATCH_ID = "20261028-192429-5a3b1e"   # its own id: never the original batch, which a real bin may hold
VIEWS = ("top", "front", "right", "back", "left")
LONG_EDGE = 1280   # px: enough for the review screen's dots, small enough to ship
QUALITY = 70
# Side views keep only the tabletop: the fraction of the upright photo cut off the top.
CROP_TOP = {"front": 0.36, "right": 0.28, "back": 0.40, "left": 0.33}
CLASSIFIER = ("sample: the kit batch's verified pieces from the inventory-loop spike (Oct 28), "
              "pre-computed; no model call")


def manifest() -> dict:
    return json.loads(MANIFEST.read_text())


def info() -> dict:
    """What the sample is, for the app's "Use sample images" button."""
    m = manifest()
    return {"batch_id": m["batch_id"], "photos": len(m["photos"]), "pieces": len(m["detections"]),
            "from_batch": m["from_batch"]}


def load(conn, data_dir) -> dict:
    """The sample as a batch, loading it the first time. Returns the batch and
    whether it was loaded now (False: it was already there, in any state)."""
    m = manifest()
    batch_id = m["batch_id"]
    existing = conn.execute("SELECT id FROM batches WHERE id = ?", (batch_id,)).fetchone()
    folder = Path(data_dir) / "batches" / batch_id
    if not folder.is_dir():   # its photos, where the review screen reads them
        folder.parent.mkdir(parents=True, exist_ok=True)
        partial = folder.parent / f".{batch_id}.partial"
        shutil.rmtree(partial, ignore_errors=True)
        partial.mkdir()
        for p in m["photos"]:
            shutil.copyfile(SAMPLE_DIR / p["file"], partial / p["file"])
        (partial / "batch.json").write_text(json.dumps({"batch_id": batch_id, "sample": True, "photos": [
            {k: p[k] for k in ("view", "file", "bytes", "sha256")} for p in m["photos"]]}, indent=2))
        partial.rename(folder)
    if existing:
        return {"batch": db.get_batch(conn, batch_id), "loaded": False}
    gate = {"passed": True, "reasons": [], "metrics": {"sample": True}}
    photos = [{**{k: p[k] for k in ("view", "file", "sha256", "bytes")}, "gate": gate} for p in m["photos"]]
    db.register_batch(conn, batch_id, datetime.now(timezone.utc).isoformat(), photos, db.photos_fingerprint(photos))
    db.replace_detections(conn, batch_id, m["detections"], CLASSIFIER)
    ids = [r["id"] for r in conn.execute("SELECT id FROM detections WHERE batch_id = ? ORDER BY id", (batch_id,))]
    db.review_batch(conn, batch_id,
                    corrections=[{"detection_id": ids[c["piece"]], **c["fix"]} for c in m["corrections"]])
    return {"batch": db.get_batch(conn, batch_id), "loaded": True}


# --- building the assets -----------------------------------------------------------

def make(source=None, recorded=None):
    """Shrink the source batch's photos into backend/sample/ and pre-compute
    its verified pieces, sized to the shrunk top photo."""
    from PIL import Image, ImageOps

    from .inventory_pipeline import to_detection
    from .segmenter import Region

    repo = HERE.parent
    source = Path(source or repo / "data" / "batches" / SOURCE_BATCH)
    recorded = json.loads(Path(recorded or repo / "tests" / "fixtures" / "kit-batch-recorded.json").read_text())
    if recorded["batch_id"] != SOURCE_BATCH:
        raise SystemExit(f"the recording is of {recorded['batch_id']}, not {SOURCE_BATCH}")
    SAMPLE_DIR.mkdir(exist_ok=True)
    photos = []
    for n, view in enumerate(VIEWS, 1):
        original = source / f"{n}-{view}.jpg"
        if hashlib.sha256(original.read_bytes()).hexdigest() != recorded["photos_sha256"][view]:
            raise SystemExit(f"{original} is not the photo the recorded run read")
        with Image.open(original) as im:
            upright = ImageOps.exif_transpose(im).convert("RGB")
        if view in CROP_TOP:
            upright = upright.crop((0, round(upright.height * CROP_TOP[view]), upright.width, upright.height))
        upright.thumbnail((LONG_EDGE, LONG_EDGE), Image.LANCZOS)
        out = io.BytesIO()
        upright.save(out, "JPEG", quality=QUALITY, optimize=True, progressive=True)   # no EXIF: no camera, no place
        name = f"{n}-{view}.jpg"
        (SAMPLE_DIR / name).write_bytes(out.getvalue())
        photos.append({"view": view, "file": name, "bytes": len(out.getvalue()),
                       "sha256": hashlib.sha256(out.getvalue()).hexdigest(),
                       "width": upright.width, "height": upright.height})
    top = photos[0]
    whole = Region((0, 0, top["width"], top["height"]), whole_photo=True)
    detections = [to_detection(piece, whole) for piece in recorded["reply"]["pieces"]]
    fields = ("family", "shape", "size", "color", "plain")
    corrections = [{"piece": r["piece"], "fix": {k: r[k] for k in fields}} for r in recorded["review"]]
    MANIFEST.write_text(json.dumps({
        "about": f"Sample bin: the Oct 28 kit batch's 5 photos, shrunk to {LONG_EDGE} px (side views cropped to the "
                 "tabletop), and its verified pieces (Spark's recorded reply plus the review's corrections), "
                 "pre-computed. "
                 "Built by python -m backend.sample_bin make.",
        "from_batch": SOURCE_BATCH, "batch_id": BATCH_ID, "photos": photos,
        "detections": detections, "corrections": corrections}, indent=1) + "\n")
    return photos


if __name__ == "__main__":
    if sys.argv[1:] != ["make"]:
        raise SystemExit("usage: python -m backend.sample_bin make")
    for p in make():
        print(f"{p['file']}: {p['width']}x{p['height']}, {p['bytes'] // 1024} KB")
