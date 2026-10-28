"""BinBuild backend — FastAPI skeleton.

Health check, batch photo upload (POST /api/inventory/batch saves a batch's
photos on disk), and placeholder routes for the rest of the inventory and
generation API. The SAM 3.1 / Muse Spark / BrickGPT integration lands in later
spikes; until then those routes answer 501 "not implemented yet".

Run locally from the repo root (--host 0.0.0.0 so a phone on the same Wi-Fi
can reach it):
    uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
"""

import json
import os
import secrets
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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


def _save_photo(photo: UploadFile, dest: Path) -> int:
    """Copy one upload to disk in chunks, enforcing the size cap. Returns bytes."""
    size = 0
    with dest.open("wb") as out:
        while chunk := photo.file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_PHOTO_BYTES:
                raise HTTPException(413, f"{photo.filename!r} is over {MAX_PHOTO_BYTES // 2**20} MB")
            out.write(chunk)
    if size == 0:
        raise HTTPException(422, f"{photo.filename!r} is empty")
    return size


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

        Saves them under data/batches/<batch_id>/ with a batch.json manifest and
        returns the new batch_id. A batch is written to a hidden temp folder and
        renamed into place only when every photo is saved, so a failed upload
        leaves nothing behind. No identification yet: SAM 3.1 + Muse Spark and
        the review/confirm endpoints come in the next spike.
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
                size = _save_photo(photo, partial / name)
                saved.append({
                    "view": view, "file": name, "bytes": size,
                    "content_type": photo.content_type, "original_filename": photo.filename,
                })
            manifest = {"batch_id": batch_id, "created_at": created.isoformat(), "photos": saved}
            (partial / "batch.json").write_text(json.dumps(manifest, indent=2))
            partial.rename(batches / batch_id)
        except BaseException:
            shutil.rmtree(partial, ignore_errors=True)
            raise
        return {"batch_id": batch_id, "photos_saved": len(saved), "photos": saved}

    @app.get("/api/inventory", status_code=501)
    async def get_inventory():
        """Return the full confirmed inventory (two-layer: generator-ready
        bricks by type x color, plus unsupported pieces by family/color).

        Placeholder: no inventory exists yet.
        """
        return JSONResponse(status_code=501, content={"detail": NOT_IMPLEMENTED})

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
