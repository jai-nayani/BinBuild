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
  main.py       App factory, health check, API route stubs
  requirements.txt
app/            Phone client (PWA, no build step)
  index.html    Capture loop: snap → review → confirm → Finished
  app.js        Batch state + placeholder wiring
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
uvicorn backend.main:app --reload --port 8000
```

Check it: `curl http://localhost:8000/health` → `{"status": "ok", ...}`.
API docs: http://localhost:8000/docs

PWA (from the repo root, in another terminal):

```bash
python3 -m http.server 8080 --directory app
```

Open http://localhost:8080 on your phone (same Wi-Fi) or desktop. Camera
capture needs a secure context — `localhost` counts, or serve over HTTPS.

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

Scaffold only: the FastAPI skeleton and the PWA shell are in place. SAM 3.1,
Muse Spark, and BrickGPT integration land in the Oct 26–27 spike. No API keys
or secrets live in this repo.
