"""BinBuild backend — FastAPI.

Health check, batch photo upload, and the inventory loop on top of it:
classify a batch (segmenter + Muse Spark), review and correct the proposals,
confirm them into the SQLite inventory, undo the last confirmed batch, and
read the inventory summary. Then the build step: what can be built from the
confirmed inventory (a known set, or a pre-generated BrickGPT design fitted
with Path A), and a step-by-step booklet for a build that fits. Live BrickGPT
generation is off.

Every photo goes through the photo gate (backend/photo_gate.py) when it is
uploaded. A batch with a failed photo answers with a "retake" list (which
view, why, what to do); the phone retakes just that photo, and classify and
confirm refuse until every photo has passed.

Run locally from the repo root (--host 0.0.0.0 so a phone on the same Wi-Fi
can reach it):
    uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
"""

import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from . import booklet, build_plan, inventory_db, inventory_vocab, photo_gate
from .sam_client import SamClient, SamError
from .segmenter import COUNT_VIEW, WholePhotoSegmenter
from .spark_client import SparkClient, SparkError

# One batch = one handful of pieces: top view + 4 sides, uploaded in this order.
BATCH_VIEWS = ("top", "front", "right", "back", "left")
# Uploaded batches land in data/batches/<batch_id>/ (git-ignored).
DATA_DIR = Path(os.environ.get("BINBUILD_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
MAX_PHOTO_BYTES = 30 * 1024 * 1024  # a 48 MP phone JPEG is ~15-25 MB
PHOTO_SUFFIXES = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
    "image/heic": ".heic", "image/heif": ".heif",
}
BATCH_ID = re.compile(r"\d{8}-\d{6}-[0-9a-f]{6}")
# Segmenter for classify when the request doesn't name one: "stub" (whole photo)
# or "sam" (SAM 3.1 close-ups after the whole-photo pass; needs META_MODEL_API_KEY).
DEFAULT_SEGMENTER = os.environ.get("BINBUILD_SEGMENTER", "stub")
# Shapes offered when fixing a piece in review (any text is accepted).
SHAPES = ("brick", "plate", "tile", "slope", "curved slope", "1x1 slope (cheese)", "inverted slope", "round brick",
          "round plate", "round tile", "brick with studs on side", "headlight brick", "plate with clip",
          "jumper plate", "hinge plate", "wedge plate", "tile with studs on edge", "arch", "wheel", "tyre")


def _save_photo(photo: UploadFile, dest: Path) -> tuple:
    """Copy one upload to disk in chunks, enforcing the size cap.
    Returns (bytes, sha256 hex)."""
    size = 0
    digest = hashlib.sha256()
    with dest.open("wb") as out:
        while chunk := photo.file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_PHOTO_BYTES:
                raise HTTPException(413, f"{photo.filename!r} is over {MAX_PHOTO_BYTES // 2**20} MB")
            digest.update(chunk)
            out.write(chunk)
    if size == 0:
        raise HTTPException(422, f"{photo.filename!r} is empty")
    return size, digest.hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _batch_dir(batch_id: str) -> Path:
    if not BATCH_ID.fullmatch(batch_id):
        raise HTTPException(404, f"no batch {batch_id!r}")
    return DATA_DIR / "batches" / batch_id


def _ensure_registered(conn, batch_id: str) -> dict:
    """The batch's database row, registering a batch that is on disk but not
    yet in the database (e.g. uploaded before the database existed)."""
    folder = _batch_dir(batch_id)
    try:
        return inventory_db.get_batch(conn, batch_id)
    except inventory_db.NotFound:
        pass
    manifest = folder / "batch.json"
    if not manifest.is_file():
        raise HTTPException(404, f"no batch {batch_id!r}")
    data = json.loads(manifest.read_text())
    photos = []
    for p in data["photos"]:
        if Path(p["file"]).name != p["file"]:
            raise HTTPException(422, f"bad photo name in {batch_id}/batch.json")
        photos.append({"view": p["view"], "file": p["file"], "bytes": p["bytes"],
                       "sha256": p.get("sha256") or _sha256_file(folder / p["file"])})
    fingerprint = inventory_db.photos_fingerprint(photos)
    if inventory_db.batch_by_fingerprint(conn, fingerprint):
        fingerprint = None  # the same photos are already registered under another id
    batch, _ = inventory_db.register_batch(conn, batch_id, data["created_at"], photos, fingerprint)
    return batch


def _check(conn, path, sha256, batch_id, view, earlier=None) -> dict:
    """The photo gate on one saved photo, plus the duplicate check: the same
    bytes may not appear twice in a batch or in any other batch (re-sending an
    old photo would count its pieces twice). earlier: {sha256: view} of photos
    already checked in this upload."""
    result = photo_gate.check_photo(path)
    reasons, metrics = list(result.reasons), dict(result.metrics)
    if earlier and sha256 in earlier:
        same = {"batch_id": batch_id, "view": earlier[sha256]}
    else:
        same = inventory_db.photo_with_hash(conn, sha256, exclude_batch=batch_id, exclude_view=view)
    if same:
        reasons.append("duplicate")
        metrics["duplicate_of"] = same
    return {"passed": not reasons, "reasons": sorted(reasons, key=photo_gate.ORDER.index), "metrics": metrics}


def _ensure_checked(conn, batch_id):
    """Run the gate on photos that predate it (uploaded before it existed)."""
    folder = _batch_dir(batch_id)
    for p in inventory_db.batch_photos(conn, batch_id):
        if p["gate_status"] is None:
            inventory_db.set_photo_gate(conn, batch_id, p["view"],
                                        _check(conn, folder / p["file"], p["sha256"], batch_id, p["view"]))


def _photo_state(conn, batch_id) -> dict:
    """Per-photo check results, whether the batch is ready, and what to retake."""
    photos = inventory_db.batch_photos(conn, batch_id)
    return {
        "photos": [{k: p[k] for k in ("view", "file", "bytes", "sha256", "gate_status", "gate_reasons", "retakes")}
                   for p in photos],
        "ready": all(p["gate_status"] == "passed" for p in photos),
        "retake": [photo_gate.retake_notice(p["view"], p["gate_reasons"])
                   for p in photos if p["gate_status"] != "passed"],
    }


def _count_photo(conn, batch_id):
    """The counted (top) photo for the review screen: where to load it, and
    its upright size in pixels, the frame Spark's piece points are in."""
    photo = next((p for p in inventory_db.batch_photos(conn, batch_id) if p["view"] == COUNT_VIEW), None)
    if photo is None:
        return None
    from PIL import Image
    try:
        with Image.open(_batch_dir(batch_id) / photo["file"]) as image:
            width, height = image.size
            if image.getexif().get(0x0112) in (5, 6, 7, 8):  # EXIF rotation by 90 degrees
                width, height = height, width
    except OSError:
        return None
    return {"view": COUNT_VIEW, "width": width, "height": height,
            "url": f"/api/inventory/batch/{batch_id}/photos/{COUNT_VIEW}?size=1600&v={photo['sha256'][:12]}"}


def _write_manifest(conn, batch_id):
    folder = _batch_dir(batch_id)
    manifest = json.loads((folder / "batch.json").read_text())
    manifest["photos"] = [{k: p[k] for k in ("view", "file", "bytes", "sha256", "gate_status", "gate_reasons", "retakes")}
                          for p in inventory_db.batch_photos(conn, batch_id)]
    (folder / "batch.json").write_text(json.dumps(manifest, indent=2))


class Correction(BaseModel):
    detection_id: int
    family: Optional[str] = None
    shape: Optional[str] = None
    size: Optional[str] = None
    color: Optional[str] = None
    plain: Optional[bool] = None
    count: Optional[int] = Field(default=None, ge=1)
    status: Optional[Literal["accepted", "rejected"]] = None


class Addition(BaseModel):
    family: str
    shape: str = ""
    size: Optional[str] = None
    color: str = "unknown"
    plain: bool = False
    count: int = Field(default=1, ge=1)


class Review(BaseModel):
    corrections: list[Correction] = []
    additions: list[Addition] = []


class BuildRequest(BaseModel):
    set: Optional[str] = None     # a known set, e.g. "house-and-tree"
    design: Optional[str] = None  # a BrickGPT category with a pre-generated design, e.g. "train"
    samples: int = Field(default=6, ge=4, le=8)


def _build_reply(build) -> dict:
    """A stored build without the booklet's drawing data, plus where to read the booklet."""
    result = {k: v for k, v in build["result"].items() if k != "booklet"}
    reply = {"build_id": build["id"], "created_at": build["created_at"], "request": build["request"], **result}
    if "booklet" in build["result"]:
        reply["booklet_url"] = f"/api/builds/{build['id']}/booklet"
        reply["steps"] = len(build["result"]["booklet"]["steps"])
    return reply


def create_app() -> FastAPI:
    app = FastAPI(
        title="BinBuild",
        description=(
            "Scan a bin of loose LEGO and generate new build guides using "
            "only the pieces you already own."
        ),
        version="0.1.0",
    )
    # The PWA is served from another port (and, on a phone, another host), so
    # the browser needs CORS to read API responses. Wide open for LAN testing.
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"],
    )

    @app.exception_handler(inventory_db.NotFound)
    async def not_found(request, err):
        return JSONResponse(status_code=404, content={"detail": str(err)})

    @app.exception_handler(inventory_db.PhotosNotReady)
    async def photos_not_ready(request, err):
        retake = [photo_gate.retake_notice(p["view"], p["gate_reasons"]) for p in err.photos]
        detail = retake[0]["message"] if len(retake) == 1 else (
            f"{len(retake)} photos are unclear ({', '.join(r['view'] for r in retake)}). Please retake just those photos.")
        return JSONResponse(status_code=422, content={"detail": detail, "ready": False, "retake": retake})

    @app.exception_handler(inventory_db.Conflict)
    async def conflict(request, err):
        return JSONResponse(status_code=409, content={"detail": str(err)})

    @app.get("/")
    async def root():
        return {
            "service": "binbuild",
            "status": "scaffold",
            "docs": "/docs",
            "health": "/health",
        }

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "binbuild", "version": "0.1.0"}

    @app.post("/api/inventory/batch", status_code=201)
    def create_inventory_batch(photos: list[UploadFile] = File(...)):
        """Accept one batch: exactly 5 photos, in order top, front, right, back, left.

        Saves them under data/batches/<batch_id>/ with a batch.json manifest,
        checks every photo with the photo gate, registers the batch in the
        inventory database and returns the new batch_id with "ready" (all 5
        passed) and "retake" (one entry per failed photo: view, reason, tip,
        message). A batch is written to a hidden temp folder and renamed into
        place only when every photo is saved, so a failed upload leaves nothing
        behind. Re-sending the exact same 5 photos (a retried upload) returns
        the existing batch with "duplicate": true instead of a second copy.
        """
        if len(photos) != len(BATCH_VIEWS):
            raise HTTPException(
                422, f"a batch is exactly {len(BATCH_VIEWS)} photos "
                     f"({', '.join(BATCH_VIEWS)}); got {len(photos)}",
            )
        for photo in photos:
            if not (photo.content_type or "").startswith("image/"):
                raise HTTPException(422, f"{photo.filename!r} is not an image ({photo.content_type})")

        created = datetime.now(timezone.utc)
        batch_id = f"{created:%Y%m%d-%H%M%S}-{secrets.token_hex(3)}"
        batches = DATA_DIR / "batches"
        partial = batches / f".{batch_id}.partial"
        partial.mkdir(parents=True)
        try:
            saved = []
            for n, (view, photo) in enumerate(zip(BATCH_VIEWS, photos), 1):
                suffix = PHOTO_SUFFIXES.get(photo.content_type, ".img")
                name = f"{n}-{view}{suffix}"
                size, sha256 = _save_photo(photo, partial / name)
                saved.append({
                    "view": view, "file": name, "bytes": size, "sha256": sha256,
                    "content_type": photo.content_type, "original_filename": photo.filename,
                })
            fingerprint = inventory_db.photos_fingerprint(saved)
            with closing(inventory_db.connect()) as conn:
                existing = inventory_db.batch_by_fingerprint(conn, fingerprint)
                if existing is None:
                    earlier = {}
                    for p in saved:
                        p["gate"] = _check(conn, partial / p["file"], p["sha256"], batch_id, p["view"], earlier)
                        earlier.setdefault(p["sha256"], p["view"])
                        p["gate_status"] = "passed" if p["gate"]["passed"] else "failed"
                        p["gate_reasons"] = p["gate"]["reasons"]
                    manifest = {"batch_id": batch_id, "created_at": created.isoformat(),
                                "photos": [{k: v for k, v in p.items() if k != "gate"} for p in saved]}
                    (partial / "batch.json").write_text(json.dumps(manifest, indent=2))
                    partial.rename(batches / batch_id)
                    try:
                        inventory_db.register_batch(conn, batch_id, created.isoformat(), saved, fingerprint)
                    except sqlite3.IntegrityError:
                        # The same photos were registered by a concurrent upload.
                        shutil.rmtree(batches / batch_id, ignore_errors=True)
                        existing = inventory_db.batch_by_fingerprint(conn, fingerprint)
                        if existing is None:
                            raise
                if existing is not None:
                    shutil.rmtree(partial, ignore_errors=True)
                    _ensure_checked(conn, existing["id"])
                    state = _photo_state(conn, existing["id"])
                    return JSONResponse(status_code=200, content={
                        "batch_id": existing["id"], "photos_saved": len(state["photos"]), "duplicate": True, **state,
                    })
                state = _photo_state(conn, batch_id)
        except BaseException:
            shutil.rmtree(partial, ignore_errors=True)
            raise
        return {"batch_id": batch_id, "photos_saved": len(saved), **state}

    @app.post("/api/inventory/batch/{batch_id}/photos/{view}")
    def retake_batch_photo(batch_id: str, view: str, photo: UploadFile = File(...)):
        """Retake one photo of a batch. Checks the new photo with the photo gate
        and replaces only that view: the other photos keep their results. Any
        proposals made from the old photos are dropped, so the batch must be
        classified again. The old photo is kept under replaced/. Answers with
        "passed" for this photo, plus "ready" and "retake" for the batch."""
        if view not in BATCH_VIEWS:
            raise HTTPException(404, f"no view {view!r}; views are {', '.join(BATCH_VIEWS)}")
        if not (photo.content_type or "").startswith("image/"):
            raise HTTPException(422, f"{photo.filename!r} is not an image ({photo.content_type})")
        folder = _batch_dir(batch_id)
        with closing(inventory_db.connect()) as conn:
            batch = _ensure_registered(conn, batch_id)
            if batch["status"] == "confirmed":
                raise HTTPException(409, f"batch {batch_id} is confirmed; undo it before retaking a photo")
            current = next(p for p in inventory_db.batch_photos(conn, batch_id) if p["view"] == view)
            suffix = PHOTO_SUFFIXES.get(photo.content_type, ".img")
            incoming = folder / f".retake-{view}{suffix}.partial"
            try:
                size, sha256 = _save_photo(photo, incoming)
                gate = _check(conn, incoming, sha256, batch_id, view)
                name = f"{BATCH_VIEWS.index(view) + 1}-{view}{suffix}"
                replaced = folder / "replaced"
                replaced.mkdir(exist_ok=True)
                old = folder / current["file"]
                kept_as = replaced / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S%f}-{current['file']}"
                if old.exists():
                    old.rename(kept_as)
                incoming.rename(folder / name)
            finally:
                incoming.unlink(missing_ok=True)
            try:
                inventory_db.replace_photo(conn, batch_id, view, name, sha256, size, gate)
            except BaseException:
                (folder / name).unlink(missing_ok=True)
                if kept_as.exists():
                    kept_as.rename(old)
                raise
            _write_manifest(conn, batch_id)
            notice = {} if gate["passed"] else photo_gate.retake_notice(view, gate["reasons"])
            return {"batch_id": batch_id, "view": view, "passed": gate["passed"], **notice,
                    **_photo_state(conn, batch_id)}

    @app.post("/api/inventory/batch/{batch_id}/classify")
    def classify_inventory_batch(batch_id: str, force: bool = False, context: bool = True,
                                 segmenter: Optional[Literal["stub", "sam"]] = None):
        """Find and name the pieces in a batch's top photo and store them as
        proposals for review. Classifier: Muse Spark on Baseten, with the 4
        side photos as context unless context=false. Segmenter:
        - stub: the whole photo in one call (about a minute);
        - sam: after the whole-photo pass, Spark's centre points prompt SAM 3.1
          (Meta Model API) for one mask per piece, and Spark checks each
          piece's close-up (about a minute more).
        Default: BINBUILD_SEGMENTER, else stub. A batch that already has
        proposals is returned as is unless force=true; with segmenter=sam, a
        whole-photo result nobody has reviewed yet gets just the SAM pass. If
        SAM fails, the whole-photo proposals stay and the error says so."""
        use = segmenter or DEFAULT_SEGMENTER
        with closing(inventory_db.connect()) as conn:
            batch = _ensure_registered(conn, batch_id)
            if batch["status"] == "confirmed":
                raise HTTPException(409, f"batch {batch_id} is confirmed; undo it before classifying again")
            _ensure_checked(conn, batch_id)
            done_with_sam = "sam-3.1" in (batch["classifier"] or "")
            if batch["status"] == "classified" and not force and (use == "stub" or done_with_sam):
                return {"classified": False, "reason": "already classified; pass force=true to run again",
                        **inventory_db.batch_review(conn, batch_id), **_photo_state(conn, batch_id)}
            # A failed photo stops here, before any Baseten or Model API call (422 with the retake list).
            inventory_db.require_photos_passed(conn, batch_id)
            from . import inventory_pipeline  # needs Pillow; keep the rest of the app importable without it
            sam = None
            if use == "sam":
                try:
                    sam = SamClient.from_env()
                except SamError as err:
                    raise HTTPException(503, f"SAM 3.1 is not set up: {err}")
            try:
                spark = SparkClient.from_env()
                run = {}
                if batch["status"] != "classified" or force:
                    run = inventory_pipeline.classify_batch(
                        conn, batch_id, _batch_dir(batch_id), WholePhotoSegmenter(), spark, context=context)
            except SparkError as err:
                raise HTTPException(502, f"Spark failed: {err}")
            if sam is not None:
                try:
                    sam_run = inventory_pipeline.refine_with_sam(
                        conn, batch_id, _batch_dir(batch_id), sam, spark, context=context)
                except (SamError, SparkError) as err:
                    raise HTTPException(502, f"The SAM pass failed, so the whole-photo proposals are kept "
                                             f"for review: {err}")
                sam_run["sam"].pop("recorded", None)
                run = {**run, "sam_pass": sam_run}
            return {"classified": True, "run": run, **inventory_db.batch_review(conn, batch_id),
                    **_photo_state(conn, batch_id)}

    @app.get("/api/inventory/batches")
    def list_inventory_batches():
        """Every batch, newest first: uploaded, classified (waiting for
        review) or confirmed, with its pieces and whether undo would take it
        out. Lets the phone find batches still waiting for review after a
        reload."""
        with closing(inventory_db.connect()) as conn:
            return {"batches": inventory_db.list_batches(conn)}

    @app.get("/api/inventory/batch/{batch_id}/photos/{view}")
    def get_batch_photo(batch_id: str, view: str, size: int = 1600):
        """One photo of a batch, turned upright (EXIF) and scaled down to at
        most `size` pixels on its long side, for the review screen."""
        if view not in BATCH_VIEWS:
            raise HTTPException(404, f"no view {view!r}; views are {', '.join(BATCH_VIEWS)}")
        folder = _batch_dir(batch_id)
        with closing(inventory_db.connect()) as conn:
            _ensure_registered(conn, batch_id)
            photo = next(p for p in inventory_db.batch_photos(conn, batch_id) if p["view"] == view)
        from io import BytesIO
        from PIL import Image, ImageOps
        side = min(max(size, 64), 4096)
        try:
            with Image.open(folder / photo["file"]) as image:
                image.draft("RGB", (side, side))  # decode JPEGs at a reduced size: much faster
                upright = ImageOps.exif_transpose(image).convert("RGB")
        except OSError:
            raise HTTPException(404, f"the {view} photo of batch {batch_id} can't be read")
        upright.thumbnail((side, side))
        out = BytesIO()
        upright.save(out, "JPEG", quality=82)
        return Response(out.getvalue(), media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=86400"})

    @app.get("/api/inventory/vocab")
    def get_inventory_vocab():
        """The words a review may use: families, colours (with a swatch
        colour), the 8 BrickGPT sizes, and suggested shapes."""
        with closing(inventory_db.connect()) as conn:
            seen = [r[0] for r in conn.execute("SELECT DISTINCT shape FROM detections WHERE shape != ''")]
        return {
            "families": list(inventory_vocab.FAMILIES),
            "colors": [{"name": c, "hex": booklet.HEX.get(c, booklet.HEX["unknown"])} for c in inventory_vocab.COLORS],
            "generator_types": list(inventory_vocab.GENERATOR_TYPES),
            "shapes": sorted(set(SHAPES) | set(seen)),
        }

    @app.get("/api/inventory/batch/{batch_id}/review")
    def get_batch_review(batch_id: str):
        """A batch's photos (with their check results) and proposed pieces,
        with any corrections so far, plus the counted photo to point at them
        on (count_photo: url and upright size; piece points are in that frame)."""
        with closing(inventory_db.connect()) as conn:
            _ensure_registered(conn, batch_id)
            _ensure_checked(conn, batch_id)
            return {**inventory_db.batch_review(conn, batch_id), **_photo_state(conn, batch_id),
                    "count_photo": _count_photo(conn, batch_id)}

    @app.post("/api/inventory/batch/{batch_id}/review")
    def post_batch_review(batch_id: str, review: Review):
        """Correct proposals before confirming: change a piece's family, shape,
        size, colour, plain flag or count; accept or reject it; or add pieces
        the classifier missed. The first correction keeps the proposed values
        in 'original'. Not allowed once the batch is confirmed (undo first)."""
        with closing(inventory_db.connect()) as conn:
            _ensure_registered(conn, batch_id)
            try:
                return inventory_db.review_batch(
                    conn, batch_id,
                    corrections=[c.model_dump() for c in review.corrections],
                    additions=[a.model_dump() for a in review.additions],
                )
            except ValueError as err:
                raise HTTPException(422, str(err))

    @app.post("/api/inventory/batch/{batch_id}/confirm")
    def confirm_inventory_batch(batch_id: str):
        """Add the batch's kept pieces (everything not rejected) to the
        inventory. Confirming again changes nothing ("already_confirmed").
        Refused (422, with the retake list) while any photo needs a retake."""
        with closing(inventory_db.connect()) as conn:
            _ensure_registered(conn, batch_id)
            _ensure_checked(conn, batch_id)
            result = inventory_db.confirm_batch(conn, batch_id)
            return {**result, "summary": inventory_db.inventory_summary(conn)}

    @app.post("/api/inventory/undo-last-batch")
    def undo_last_inventory_batch(batch_id: Optional[str] = None):
        """Take the most recently confirmed batch back out of the inventory and
        reopen it for review. Pass batch_id to make a retry safe: the undo then
        only happens while that batch is still the last confirmed one."""
        with closing(inventory_db.connect()) as conn:
            result = inventory_db.undo_last_batch(conn, expected_batch_id=batch_id)
            if result is None:
                raise HTTPException(409, "no confirmed batch to undo")
            return {**result, "summary": inventory_db.inventory_summary(conn)}

    @app.get("/api/inventory/summary")
    def get_inventory_summary():
        """The confirmed inventory: the 8 generator-ready BrickGPT brick types
        by colour, then every other piece by broad family and colour, and
        unknown pieces on their own."""
        with closing(inventory_db.connect()) as conn:
            return inventory_db.inventory_summary(conn)

    @app.get("/api/inventory")
    def get_inventory():
        """Same as /api/inventory/summary."""
        return get_inventory_summary()

    @app.get("/api/builds/options")
    def get_build_options():
        """Everything there is to build, manual first:
        - every build in the manual that came with the kit (kind "manual"):
          a verified build is checked against the confirmed inventory ("fit"
          or "short", with what is missing) and can get a booklet; every other
          one is "unverified": listed with its chapter and pages, its piece
          list not yet verified, no fit claim and no booklet;
        - then the pre-generated BrickGPT designs, with "fit", "patched",
          "short" or "not_connected"."""
        with closing(inventory_db.connect()) as conn:
            summary = inventory_db.inventory_summary(conn)
        found = build_plan.options(summary["items"])
        manual = [o for o in found if o["kind"] == "manual"]
        count = lambda status: sum(o["piece_status"] == status for o in manual)  # noqa: E731
        return {"inventory": {"total_pieces": summary["total_pieces"],
                              "generator_ready": summary["generator_ready"]["total"],
                              "other": summary["other"]["total"] + summary["unknown"]["total"]},
                "manual": {"builds": len(manual), "verified": count("verified"),
                           "diagram_readable": count("diagram-readable"),
                           "not_yet_piece_verified": count("not-yet-piece-verified"),
                           "read_from": build_plan.manual_catalog()["read_from"]},
                "options": found}

    @app.get("/api/manual")
    def get_manual():
        """The manual catalog: every build in the book, its chapter and pages,
        and the status of its piece list. No parts lists."""
        return build_plan.manual_catalog()

    @app.post("/api/builds", status_code=201)
    def create_build(request: BuildRequest):
        """Plan a build from the confirmed inventory and store it: a known set
        ({"set": "house-and-tree"}) or a BrickGPT design fitted with Path A
        ({"design": "train"}). A plan that fits comes with a booklet
        (booklet_url); one that doesn't comes back as a named shortfall, with
        no booklet."""
        if bool(request.set) == bool(request.design):
            raise HTTPException(422, "ask for exactly one of: a known set ('set') or a BrickGPT design ('design')")
        asked = {"set": request.set} if request.set else {"design": request.design, "samples": request.samples}
        with closing(inventory_db.connect()) as conn:
            summary = inventory_db.inventory_summary(conn)
            try:
                result = build_plan.plan(asked, summary["items"])
            except KeyError as err:
                raise HTTPException(404, err.args[0])
            build = inventory_db.create_build(conn, asked, build_plan.snapshot(summary), result)
            return _build_reply(build)

    @app.get("/api/builds/{build_id}")
    def get_build(build_id: int):
        """A stored build: the plan, the inventory it was planned against and,
        if it fits, the booklet's steps."""
        with closing(inventory_db.connect()) as conn:
            build = inventory_db.get_build(conn, build_id)
        return {**_build_reply(build), "booklet": build["result"].get("booklet"),
                "inventory_snapshot": build["inventory_snapshot"]}

    @app.get("/api/builds/{build_id}/booklet", response_class=HTMLResponse)
    def get_build_booklet(build_id: int):
        """The booklet as one printable page: a picture for every step."""
        with closing(inventory_db.connect()) as conn:
            build = inventory_db.get_build(conn, build_id)
        if "booklet" not in build["result"]:
            raise HTTPException(404, f"build {build_id} doesn't fit the inventory, so it has no booklet: "
                                     f"{build['result']['message']}")
        return HTMLResponse(booklet.render_html(build["result"]["booklet"]))

    return app


app = create_app()
