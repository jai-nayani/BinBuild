# BinBuild

**BinBuild scans a bin of loose LEGO and generates new build guides using only the pieces you already own.**

**Built during the Meta AI Developer Hackathon (Oct 26 – Nov 4)** — indie track, with Meta SAM 3.1, Muse Spark, and inventory-constrained BrickGPT.

> Fan project, not affiliated with or endorsed by the LEGO Group. "LEGO" is a
> trademark of the LEGO Group.

## How it works

1. **Snap a handful** — lay pieces on the table, take a photo with your phone.
2. **Review and confirm** — the app names every piece it finds; you correct or
   rescan, then confirm the batch into the running inventory.
3. **Repeat until "Finished"** — sweep pieces aside, snap the next handful.
4. **Ask for a build** — the app invents a brand-new model designed using only
   the pieces in your bin, and hands you a step-by-step booklet.

Only 8 brick types feed generation (BrickGPT's library): 1×1, 1×2, 1×4, 1×6,
1×8, 2×2, 2×4, 2×6. Every other piece still gets an inventory record under a
broad family (plate, slope, wheel, …) or "unknown" — never forced into the
nearest brick category.

Related work: BrickWright (Pun et al., 2026) generates LEGO builds with LLM agents in a plan-execute-validate loop — the same paradigm as our Wonder designer + validator; we add the inventory constraint (builds limited to exactly the pieces you own). [arXiv:2610.31651](https://arxiv.org/abs/2610.31651)

## Repo layout

```
backend/        FastAPI backend (inventory + generation API)
  main.py       App factory, health check, batch upload, inventory loop endpoints
  inventory_db.py        SQLite inventory (binbuild.db, git-ignored)
  inventory_vocab.py     Generator types, families, colour names
  segmenter.py           Segmenter interface: whole-photo stub, SAM 3.1 (one region per piece)
  sam_client.py          SAM 3.1 via the Meta Model API (key from .env, never logged)
  wonder_design.py       Designs with every kind of owned piece: format, LDraw geometry, validator
  wonder_client.py       Muse Wonder via the Meta Model API (key from .env, never logged)
  wonder_designer.py     Wonder designs from the bin, validated, retried, booklet (parallel track)
  designs/               Validated Wonder designs (not yet hand-built)
  spark_client.py        Muse Spark via Baseten (key from .env, never logged)
  inventory_pipeline.py  Classify a batch: segment, ask Spark, store proposals
  photo_gate.py          Per-photo checks before any Spark call (blur, light, pieces, fakes)
  sample_bin.py          "Use sample images": the kit batch's 5 photos and verified pieces, pre-computed
  sample/                Those 5 small photos (side views cropped to the tabletop) + kit.json
  build_plan.py          The build step: known sets, BrickGPT designs through Path A
  brickgpt_constraint.py Path A: generate (pre-generated designs) -> filter -> patch
  booklet.py             Step-by-step booklet: JSON + printable HTML page with drawings
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
  app.js        5-photo batches, upload, retake pop-up, Identify, Check the pieces,
                What can I build? (BACKEND_URL at the top)
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

The capture loop and the inventory loop work end to end on a real batch:
upload, classify with Muse Spark (whole-photo stub segmenter until SAM 3.1),
review, confirm into SQLite, undo, summary. Results and API:
[INVENTORY-LOOP.md](INVENTORY-LOOP.md). Every photo is checked before any
Spark call, and a failed photo is retaken on its own:
[IMAGE-GUARDRAILS.md](IMAGE-GUARDRAILS.md). The build step is wired on: the
confirmed inventory goes to a known set or, through Path A, to a pre-generated
BrickGPT design, and a build that fits gets a step-by-step booklet; one that
doesn't gets a named shortfall. One batch runs through every stage with
`python -m backend.full_loop`: [FULL-LOOP.md](FULL-LOOP.md). Live BrickGPT
generation is off. SAM 3.1 (Meta Model API) is wired in behind the same
segmenter interface: one mask per piece, close-ups checked by Spark, outlines
in review. It is opt-in (`?segmenter=sam` or `BINBUILD_SEGMENTER=sam`); results
on the kit batch: [SAM-3-1.md](SAM-3-1.md).
The build API still lists every build in the manual that came with the kit
(106; 41 have a verified piece list and a bin check — house-and-tree
hand-checked, 40 more verified by two independent Muse Wonder reads of the
page agreeing on every line, 11 in all with a validated step-by-step
booklet), then BrickGPT designs: [MANUAL-CATALOG.md](MANUAL-CATALOG.md).
In the app, "What can I build?" is a sideways carousel of just those 11
booklet builds — each card the booklet's finished-model picture, its name
and piece count — and tapping a card opens its step-by-step booklet, with
Back returning to the same card. (The paintbrush has a verified piece list
but no booklet: the book's brush lies on its side, which the physical
validator cannot express, so it stays honestly labelled booklet-less.) Nothing is shown there until pieces are
confirmed (or the sample bin is loaded and confirmed).
Draft parts lists for the builds that print none were read from the pictures
by Muse Wonder: [WONDER-TRANSCRIBE.md](WONDER-TRANSCRIBE.md); the second
reads and auto-generated booklets: [MANUAL-VERIFY.md](MANUAL-VERIFY.md). The
60 drafts whose reads differ wait in the hand-check queue, differing lines
first.
A hand-check records the build's steps too, so a hand-checked build gets a
booklet like house and tree; the retake pop-up fix from the Oct 31 trial is in
[TRIAL-FIXES.md](TRIAL-FIXES.md).
Everything above is integrated into one app on `spike/integration`, with the
trial-day run sheet: [INTEGRATION.md](INTEGRATION.md).
Parallel track: Muse Wonder designs new models from every kind of piece in
the bin (not just BrickGPT's 8 bricks), checked by a validator against the
owned pieces and LDraw geometry: [WONDER-DESIGNER.md](WONDER-DESIGNER.md).
With `BINBUILD_WONDER=1` (off by default, and off for the kid trials) "What
can I build?" gains a third section, "Generate a new design", wired to that
designer: [WONDER-IN-APP.md](WONDER-IN-APP.md).
On the phone, **Check the pieces** reviews an identified batch (dots on the
photo, fix / remove / add, then add to the inventory, with undo); a piece
Spark flagged unsure also gets **Retake this piece** — one clean close-up of
just that piece, named again on its own, its row updated where it sits:
[REVIEW-SCREEN.md](REVIEW-SCREEN.md). Phone test steps: [TESTING.md](TESTING.md).
No API keys or secrets live in this repo: the Baseten and Meta Model API keys
are read from the git-ignored `.env` (`BASETEN_API_KEY`, `META_MODEL_API_KEY`).
