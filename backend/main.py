"""BinBuild backend — FastAPI.

Health check, batch photo upload, and the inventory loop on top of it:
classify a batch (segmenter + Muse Spark), review and correct the proposals,
confirm them into the SQLite inventory, undo the last confirmed batch, and
read the inventory summary. Generation (BrickGPT) still answers 501.

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
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import inventory_db
from .segmenter import WholePhotoSegmenter
from .spark_client import SparkClient, SparkError

NOT_IMPLEMENTED = "Not implemented yet — lands in the Oct 26-27 spike."

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


def _fingerprint(photos) -> str:
    """Same photos in the same views -> same fingerprint (catches re-uploads)."""
    return hashlib.sha256("\n".join(f"{p['view']}:{p['sha256']}" for p in photos).encode()).hexdigest()


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
    fingerprint = _fingerprint(photos)
    if inventory_db.batch_by_fingerprint(conn, fingerprint):
        fingerprint = None  # the same photos are already registered under another id
    batch, _ = inventory_db.register_batch(conn, batch_id, data["created_at"], photos, fingerprint)
    return batch


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
        registers the batch in the inventory database and returns the new
        batch_id. A batch is written to a hidden temp folder and renamed into
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
            fingerprint = _fingerprint(saved)
            with closing(inventory_db.connect()) as conn:
                existing = inventory_db.batch_by_fingerprint(conn, fingerprint)
                if existing is None:
                    manifest = {"batch_id": batch_id, "created_at": created.isoformat(), "photos": saved}
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
                    kept = inventory_db.batch_photos(conn, existing["id"])
                    return JSONResponse(status_code=200, content={
                        "batch_id": existing["id"], "photos_saved": len(kept), "duplicate": True,
                        "photos": [{k: p[k] for k in ("view", "file", "bytes", "sha256")} for p in kept],
                    })
        except BaseException:
            shutil.rmtree(partial, ignore_errors=True)
            raise
        return {"batch_id": batch_id, "photos_saved": len(saved), "photos": saved}

    @app.post("/api/inventory/batch/{batch_id}/classify")
    def classify_inventory_batch(batch_id: str, force: bool = False, context: bool = True):
        """Find and name the pieces in a batch's top photo and store them as
        proposals for review. Segmenter: the whole-photo stub until SAM 3.1 is
        wired in. Classifier: Muse Spark on Baseten, with the 4 side photos as
        context unless context=false. A batch that already has proposals is
        returned as is unless force=true. Takes about a minute."""
        with closing(inventory_db.connect()) as conn:
            batch = _ensure_registered(conn, batch_id)
            if batch["status"] == "confirmed":
                raise HTTPException(409, f"batch {batch_id} is confirmed; undo it before classifying again")
            if batch["status"] == "classified" and not force:
                return {"classified": False, "reason": "already classified; pass force=true to run again",
                        **inventory_db.batch_review(conn, batch_id)}
            from . import inventory_pipeline  # needs Pillow; keep the rest of the app importable without it
            try:
                spark = SparkClient.from_env()
                run = inventory_pipeline.classify_batch(
                    conn, batch_id, _batch_dir(batch_id), WholePhotoSegmenter(), spark, context=context)
            except SparkError as err:
                raise HTTPException(502, f"Spark failed: {err}")
            return {"classified": True, "run": run, **inventory_db.batch_review(conn, batch_id)}

    @app.get("/api/inventory/batch/{batch_id}/review")
    def get_batch_review(batch_id: str):
        """A batch's photos and proposed pieces, with any corrections so far."""
        with closing(inventory_db.connect()) as conn:
            _ensure_registered(conn, batch_id)
            return inventory_db.batch_review(conn, batch_id)

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
        inventory. Confirming again changes nothing ("already_confirmed")."""
        with closing(inventory_db.connect()) as conn:
            _ensure_registered(conn, batch_id)
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

    @app.post("/api/generate", status_code=501)
    async def generate_build(payload: dict):
        """Request a new build from the confirmed inventory.

        Placeholder: the real handler will run inventory-constrained BrickGPT
        and return a build id to poll.
        """
        return JSONResponse(
            status_code=501,
            content={"detail": NOT_IMPLEMENTED, "request": payload},
        )

    @app.get("/api/builds/{build_id}", status_code=501)
    async def get_build(build_id: str):
        """Return a generated build (status + step-by-step booklet)."""
        return JSONResponse(
            status_code=501,
            content={"detail": NOT_IMPLEMENTED, "build_id": build_id},
        )

    return app


app = create_app()
