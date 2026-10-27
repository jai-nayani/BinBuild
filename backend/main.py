"""BinBuild backend — FastAPI skeleton.

Scaffold only: health check plus placeholder routes for the inventory and
generation API. The SAM 3.1 / Muse Spark / BrickGPT integration lands in the
Oct 26-27 spike; until then every API route answers 501 "not implemented yet".

Run locally from the repo root:
    uvicorn backend.main:app --reload --port 8000
"""

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse

NOT_IMPLEMENTED = "Not implemented yet — lands in the Oct 26-27 spike."


def create_app() -> FastAPI:
    app = FastAPI(
        title="BinBuild",
        description=(
            "Scan a bin of loose LEGO and generate new build guides using "
            "only the pieces you already own."
        ),
        version="0.1.0",
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

    @app.post("/api/inventory/batch", status_code=501)
    async def create_inventory_batch(
        batch_id: str = Form(...),
        photos: list[UploadFile] = File(...),
    ):
        """Accept one batch of photos (top + 4 sides of a scattered handful).

        Placeholder: stores nothing yet. The real handler will run SAM 3.1 +
        Muse Spark over the photos and return the pieces found for review.
        """
        return JSONResponse(
            status_code=501,
            content={
                "detail": NOT_IMPLEMENTED,
                "batch_id": batch_id,
                "photos_received": len(photos),
            },
        )

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
