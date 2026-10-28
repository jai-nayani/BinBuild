# BinBuild

**BinBuild scans a bin of loose LEGO and generates new build guides using only the pieces you already own.**

Built with Meta SAM 3.1, Muse Spark, and inventory-constrained BrickGPT for the
Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026, indie track).

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

## Repo layout

```
backend/        FastAPI backend (inventory + generation API)
  main.py       App factory, health check, batch upload, inventory loop endpoints
  inventory_db.py        SQLite inventory (binbuild.db, git-ignored)
  inventory_vocab.py     Generator types, families, colour names
  segmenter.py           Segmenter interface + whole-photo stub (SAM 3.1 later)
  spark_client.py        Muse Spark via Baseten (key from .env, never logged)
  inventory_pipeline.py  Classify a batch: segment, ask Spark, store proposals
  photo_gate.py          Per-photo checks before any Spark call (blur, light, pieces, fakes)
  requirements.txt
tests/          Standard-library unit tests (python3 -m unittest discover -s tests)
app/            Phone client (PWA, no build step)
  index.html    Capture loop: snap → review → confirm → Finished
  app.js        5-photo batches, upload, retake pop-up, Identify (BACKEND_URL at the top)
  manifest.json PWA manifest
  sw.js         Service worker (offline app shell)
  icon.svg      App icon
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
[IMAGE-GUARDRAILS.md](IMAGE-GUARDRAILS.md). BrickGPT generation is still a stub.
No API keys or secrets live in this repo: the Baseten key is read from the
git-ignored `.env` (`BASETEN_API_KEY`).
