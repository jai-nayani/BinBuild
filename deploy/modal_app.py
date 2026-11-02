"""BinBuild on Modal: the FastAPI backend and the PWA at one public URL.

Deploy from the repo root:
    modal deploy deploy/modal_app.py

- One web function (modal.asgi_app) serves the API and the PWA's static files
  (BINBUILD_APP_DIR), so the page and the API share an origin: no CORS.
  max_containers=1: one container holds the database and the in-memory rate
  limits.
- An empty bin at every container start: nothing to build until a visitor
  scans a handful or taps "Use sample images" (backend/sample_bin.py: 5 small
  sample photos and their pre-computed pieces, no model call, no key needed).
  The image carries only backend/ (with those sample assets), app/ and the
  pre-generated Path A designs; never .env, binbuild.db, data/ or other photos.
- Secrets live in Modal, not in the repo or the image:
    binbuild-api-keys  BASETEN_API_KEY, META_MODEL_API_KEY (the paid APIs)
    binbuild-access    BINBUILD_ACCESS_KEY (the shared key for the routes
                       that spend credits, backend/guard.py)
  The app refuses to start without BINBUILD_ACCESS_KEY, so the paid routes
  can't come up open.
- "Generate a new design" (BINBUILD_WONDER) stays off.
"""

from pathlib import Path

import modal

REPO = Path(__file__).resolve().parent.parent
REMOTE = "/root"
SKIP = ["**/__pycache__/**", "**/*.pyc", "**/.DS_Store"]

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements(str(REPO / "backend" / "requirements.txt"))
    .env({
        "BINBUILD_DB": "/tmp/binbuild/binbuild.db",     # container-local: fresh at every start
        "BINBUILD_DATA_DIR": "/tmp/binbuild/data",
        "BINBUILD_APP_DIR": f"{REMOTE}/app",
    })
    .add_local_dir(REPO / "backend", f"{REMOTE}/backend", ignore=SKIP)
    .add_local_dir(REPO / "app", f"{REMOTE}/app", ignore=SKIP)
    .add_local_dir(REPO / "spike-constraint-kit" / "designs", f"{REMOTE}/spike-constraint-kit/designs", ignore=SKIP)
)

app = modal.App("binbuild", image=image)


@app.function(
    secrets=[modal.Secret.from_name("binbuild-api-keys"), modal.Secret.from_name("binbuild-access")],
    max_containers=1,
    scaledown_window=600,
    timeout=600,        # a classify with the SAM pass takes a few minutes
)
@modal.concurrent(max_inputs=32)
@modal.asgi_app(label="binbuild")
def web():
    import os

    if not os.environ.get("BINBUILD_ACCESS_KEY", "").strip():
        raise RuntimeError("BINBUILD_ACCESS_KEY is not set (Modal secret binbuild-access): "
                           "refusing to start with the paid routes open")
    os.environ.pop("BINBUILD_WONDER", None)

    from backend.main import app as api
    return api
