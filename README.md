# BinBuild

**BinBuild scans a bin of loose LEGO and generates new build guides using only the pieces you already own.**

**Built during the Meta AI Developer Hackathon (Oct 26 – Nov 4)** — indie track, with Meta SAM 3.1, Muse Spark, and inventory-constrained BrickGPT.

> Fan project, not affiliated with or endorsed by the LEGO Group. "LEGO" is a
> trademark of the LEGO Group.

## How it works

1. **Snap a handful** — lay pieces in one flat layer and take a top photo and
   four side photos. A quality gate checks each view.
2. **Review and confirm** — Muse Spark proposes pieces and centre points;
   SAM 3.1 cuts out masks and Spark checks the close-ups. You correct or
   rescan the proposals, then confirm the batch into the running inventory.
3. **Repeat until "Finished"** — sweep pieces aside and scan the next handful.
4. **Ask for a build** — Muse Wonder proposes a new model using supported,
   confirmed pieces. The validator checks the placements against the inventory;
   Spark can write the words for a step-by-step booklet. The kit's booklets
   remain available too.

BrickGPT's separate, pre-generated designs use eight plain brick types: 1×1,
1×2, 1×4, 1×6, 1×8, 2×2, 2×4, and 2×6. Wonder supports additional known
part shapes; unknown and unsupported pieces remain in the inventory but cannot
be used as exact placements until they can be identified and represented.

Related work: BrickWright (Pun et al., 2026) generates LEGO builds with LLM agents in a plan-execute-validate loop — the same paradigm as our Wonder designer + validator; we add the inventory constraint (builds limited to exactly the pieces you own). [arXiv:2610.31651](https://arxiv.org/abs/2610.31651)

## Repo layout

```
backend/        FastAPI backend (inventory + generation API)
  main.py       App factory, health check, batch upload, inventory loop endpoints
  inventory_db.py        SQLite inventory (binbuild.db, git-ignored)
  inventory_vocab.py     Generator types, families, colour names
  segmenter.py           Segmenter interface: whole-photo stub, SAM 3.1 (one region per piece)
  sam_client.py          SAM 3.1 via the Meta Model API (key from .env, never logged)
  wonder_design.py       Supported piece geometry, design format, and validator
  wonder_client.py       Muse Wonder via the Meta Model API (key from .env, never logged)
  wonder_designer.py     Wonder designs from confirmed pieces, validated and retried
  designs/               Validated Wonder designs (not yet hand-built)
  spark_client.py        Muse Spark via Baseten (key from .env, never logged)
  step_writer.py         Spark words for checked booklet steps, with safe fallback
  inventory_pipeline.py  Classify a batch: segment, ask Spark, store proposals
  photo_gate.py          Per-photo checks before any Spark call (blur, light, pieces, fakes)
  sample_bin.py          Sample photos, verified pieces, and recorded SAM outlines; no model call
  sample/                Those 5 small photos (side views cropped to the tabletop) + kit.json
  build_plan.py          The build step: known sets, BrickGPT designs through Path A
  brickgpt_constraint.py Path A: generate (pre-generated designs) -> filter -> patch
  booklet.py             Step-by-step booklet: JSON + printable HTML page with drawings
  ldraw_render.py        The drawings: the kit's real part shapes, z-buffered at the book's angle
  ldraw_mesh.py          Builds ldraw_kit.json.gz (the kit's parts from the LDraw library)
  sets/                  Known sets with verified piece lists (house-and-tree)
  manual/catalog.json    Every build in the kit's manual: name, chapter, pages, piece-list status
  manual/drafts/         Draft piece lists read from the book (verified once two reads agree or a hand-check):
                         18 from the printed element boxes, the rest read by Muse Wonder from the pictures
  manual/photos.json     Which manual photo shows each page (file names only)
  manual_transcribe.py   Muse Wonder drafts parts lists for builds that print none (python -m backend.manual_transcribe)
  manual_verify.py       Second Wonder read per draft; auto booklet steps for the ones that agree (python -m backend.manual_verify)
  manual_check.py        Hand-check a draft and record its steps (python -m backend.manual_check)
  full_loop.py           One batch through every stage via the API (recorded Spark reply)
  requirements.txt
tests/          Standard-library unit tests (python3 -m unittest discover -s tests;
                Path A: python3 -m unittest backend.test_brickgpt_constraint)
spike-constraint-kit/  Pre-generated BrickGPT designs and Path A test inventories
app/            Phone client (PWA, no build step)
  index.html    Hero (scatter → identify → build, bricks snapping together), then the
                capture hub: a 3-column grid of 6 panels (tip out one flat layer + the
                5 photos) → review → Next: identify → check the pieces → Finished
  style.css     The look; plain CSS motion, nothing moves with reduced motion
  app.js        5-photo batches, two-pass Identify, review, and background design jobs
  manifest.json PWA manifest (standalone; PNG icons for home screens)
  sw.js         Service worker (offline app shell)
  icon.svg, icon-192.png, icon-512.png, icon-maskable-512.png,
  apple-touch-icon.png   App icons (180x180 for iPhone home screens)
```

## Run it locally

Backend (from the repo root):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Check it: `curl http://localhost:8000/health` → `{"status": "ok", ...}`.
API docs: http://localhost:8000/docs

PWA (from the repo root, in another terminal):

```bash
python3 -m http.server 8080 --bind 0.0.0.0 --directory app
```

Open http://localhost:8080 on the desktop, or `http://<this Mac's Wi-Fi
address>:8080` on a phone on the same Wi-Fi. The camera uses the native file
input (`capture="environment"`), which works over plain HTTP; the service
worker is optional and only runs on HTTPS or localhost. Uploaded batches are
saved under `data/batches/` (git-ignored). Step-by-step phone test:
[TESTING.md](TESTING.md).

## Build-week plan (Oct 26 – Nov 4)

- **Oct 26–27:** real-phone capture + one-batch identify-and-count; BrickGPT
  constraint prototype. Decision: if ID can't tell a 2×2 from a 2×4, narrow at
  once; if the constraint won't integrate, drop to the small tested catalog.
- **Oct 28–29:** full batch loop + review-and-confirm + "Finished" flow +
  inventory-constrained generation end to end.
- **Oct 30–Nov 1:** held-out evaluation + kid trials with the cousins (written
  parental OK first, hands-only footage).
- **Nov 2:** feature freeze; record the demo + backup video.
- **Nov 3–4:** submission. Aim midday Nov 4 — deadline 9:00 PM ET.

## Status

The app requests a whole-photo Muse Spark pass, then a SAM 3.1 mask and Spark
close-up pass, before the user reviews and confirms the proposed inventory.
A failed SAM pass leaves the whole-photo proposals available for review. The
sample bin provides the Oct 28 kit batch, verified labels, and recorded SAM
outlines from Oct 28 ET without a model call. The original recorded run still
needed 11 label corrections after the SAM pass. Details and prior recorded
measurements: [LIVE-LOOP.md](LIVE-LOOP.md), [SAM-3-1.md](SAM-3-1.md).

When Wonder is enabled, "What can I build?" offers new designs from supported
confirmed pieces. Generation runs as a polled background job; the validator
checks piece counts and represented connections, and Spark can write the
booklet's step text. If no design passes, the app reports the failure instead
of offering a booklet. Generated designs have not yet been hand-built. The
recorded Wonder example was made from the kit, not the viewer's bin. The
updated flow still needs a live check by the owner.

The repository's Modal configuration enables Wonder with up to three tries;
local use can set `BINBUILD_WONDER=1`. Updating this configuration does not
itself deploy the app. The public deploy requires the access key for paid
routes. With no key, the recorded example is available without a model call.

The kit's manual catalog and booklets remain available alongside generated
builds: [MANUAL-CATALOG.md](MANUAL-CATALOG.md). BrickGPT's separate path uses
pre-generated designs; live BrickGPT generation is off. On the phone, **Check
the pieces** supports correction, removal, addition, and an individual retake
for an unsure piece: [REVIEW-SCREEN.md](REVIEW-SCREEN.md). A step-by-step phone
test is in [TESTING.md](TESTING.md). Earlier spike documents describe the
behaviour and measurements of their original branches.

No API keys or secrets live in this repo: Baseten and Meta Model API keys are
read from the environment or the git-ignored `.env`.

Part shapes in the booklet drawings (`backend/ldraw_kit.json.gz`) come from the
[LDraw](https://www.ldraw.org) parts library, licensed CC BY 4.0.
