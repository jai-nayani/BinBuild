# Wonder in the app

Branch `spike/wonder-in-app`, built on `spike/integration` (334714a). The
Wonder designer, until now behind its CLI, is wired into "What can I build?"
as **"Generate a new design"**. It is behind a flag, `BINBUILD_WONDER=1`,
which is **off by default** and stays off for the kid trials.

## What a tap does

```
"What can I build?"  ──(flag on)──▶ 3rd section: ✨ New design from your pieces
   pick a target (a simple house / a little car / an animal / a robot / a boat) ─▶ [✨ Generate a new design]
        │ one tap = one generation; nothing runs without it
        ▼
POST /api/builds/wonder ─▶ the CONFIRMED inventory (every owned kind, exact counts, LDraw geometry: the CLI's prompt)
        ─▶ Muse Wonder ─▶ validator ─▶ errors back to Wonder ─▶ … at most 5 tries
        ├─ passes ─▶ stored as a build (with its inventory and batches) ─▶ title, parts list, "📖 Open the booklet"
        └─ never passes ─▶ stored as a build ─▶ the named shortfall (e.g. "Short of 1× orange 1x2 brick"), no design shown
```

- **The screen.** The section explains what a tap costs: about 2 minutes
  and $0.25 a try, at most 5 tries, a second try only if the check fails.
  - While it runs, the button is disabled and counts the seconds.
  - Below it, "Designs made before" lists the last 5 generations, with
    their booklets.
- **Nothing unvalidated reaches the screen.** A design gets a parts list,
  placements and a booklet only if it passed the validator on the owned
  pieces. It is checked again just before it is stored.
  - A failure stores and shows only the message, the shortfall and the last
    try's problems. It never shows the rejected design's lines, parts or
    booklet.
- **One at a time.** A second tap while one is running gets "a new design
  is already being made" (409).
  - Without a Model API key: 503, before any call.
  - With an empty inventory: 422.
  - If Wonder itself fails: 502, and the lock is released.
- **Saved like any other build,** in the `builds` table:
  - request `{"wonder": true, "target": …}`;
  - the inventory snapshot, plus the confirmed batch ids it came from;
  - the result, with its tries, time and cost.
  - Its booklet is `GET /api/builds/{id}/booklet`, as for house-and-tree.
- **The CLI is unchanged** (`python -m backend.wonder_designer`), and so are
  Simple House and its "not yet hand-built" status.

## Flag off = exactly as before

- **"What can I build?"**
  - `GET /api/builds/options` has the same keys as before (`inventory`,
    `manual`, `options`); the `wonder` block is only added when the flag is
    on.
  - The screen has the same two sections: manual first with house-and-tree
    highlighted, then BrickGPT. It still has 105 manual rows and one
    booklet button, and no Wonder section.
  - Checked in the browser at 375 px.
- **`POST /api/builds/wonder`** answers 404 ("start the backend with
  BINBUILD_WONDER=1") without touching Wonder.
- **The real backend** has been put back on this branch with the flag off.

## Checks

**Tests:** `tests/test_wonder_app.py`, 8, on recorded or written replies
only:
- flag off: same build list, 404, no Wonder call;
- flag on: the build list adds the section and calls nothing;
- the recorded live run: a validated Simple House with 20 parts and
  placements, a booklet, stored with its batch, and listed under "Designs made
  before";
- a fix on try 2 passes;
- five failures give "No design fits your pieces after 5 tries. Short of 1×
  orange 1x2 brick.", with no booklet, parts, placements or design;
- failures without a shortfall;
- no key (503), a too-short target (422), a second tap while busy (409), an
  empty inventory (422);
- a Wonder error (502, with the lock released).

**Phone (375 px), recorded replies:**
- **Setup:** a scratch backend with the flag on, a copy of the real database,
  and Wonder played back from the recorded live run.
- **What it showed:** the third section below the BrickGPT designs. Generate
  gave "Simple House · Muse Wonder", "✓ Checked: only your pieces, all held
  by studs", 10 part lines, "📖 Open the booklet (5 steps)", and "1 try,
  $0.20".

**One live call, through the app at 375 px:**
- **Setup:** a scratch backend with the flag on, on a copy of the real
  database left with only the kit batch. That's exactly the corrected 50-piece
  inventory; see the note below for why the copy.
- **The tap:** Generate, with "a simple house".
  - The button showed "Designing a simple house… N s" and the
    keep-this-screen-open note.
- **Result:** after 107 s, **"Small House with Pitched Roof"**:
  - passed the validator on try 1;
  - **$0.16** (one Muse Wonder call);
  - 18 owned pieces in 9 kinds: 1 orange 1x2 brick, 2 blue side-stud bricks,
    1 headlight brick, 1 round brick, 4 purple 1x2 plates, 2 magenta 2x2
    plates, 2 azure 2x4 plates, 4 black curved slopes, 1 round tile;
  - stored as build 5 with batch `20261028-192429-119901`;
  - its 5-step booklet renders at phone width.

  It has the same build as Simple House: a 4×4 base, a wall course, a deck,
  a pitched roof and a chimney.

**Totals:** 152 tests in `tests/` plus Path A's 31, all passing in the venv.
With the system `python3`, 65 are skipped and the rest pass.

## A note on your real inventory

`binbuild.db` now holds a **second confirmed batch**, `20261029-221736-54cd20`.
- **What it is:** new photos from a phone, uploaded at 18:17 local today,
  identified by live Spark, with 1 correction, confirmed at 18:20.
- **Effect:** the inventory is now 100 pieces, 7 of them plain bricks
  BrickGPT can use.
- **The risk:** if it was the same 50-piece kit scanned again, those pieces
  are counted twice. Undo it before generating, or Wonder will design from
  pieces you don't have.
- **What I did:** I didn't touch it. The live call used a copy without it.

## One line each

- **What the live call cost and took:** one Muse Wonder call, through the
  app on the 50-piece kit inventory: $0.16 and 107 s, passing on try 1.
- **Where the Generate option sits:** in "What can I build?", a third section
  "✨ New design from your pieces", below the BrickGPT designs. It appears only
  with `BINBUILD_WONDER=1`; manual first, BrickGPT second and the
  house-and-tree highlight are unchanged.
- **What the Oct 31 kill trigger needs to see to flip the flag on:** Simple
  House (`backend/designs/wonder-simple-house.txt`) built by a person from
  the kit, following its booklet, standing on its own and holding together
  as the booklet says. If not, the flag stays off and the demo stays manual
  catalog plus BrickGPT.

**Turning it on**, after the kill trigger, on the Mac:
```bash
BINBUILD_WONDER=1 .venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

## Limits

- **One request per generation.** A 5-try worst case is about 10 minutes on
  one open request. The phone waits up to 15 minutes; leaving the screen
  loses the answer, but the design is still stored, under "Designs made
  before".
- **Booklet view.** The pictures look from the +x/+y corner, so a
  generated house may show its back; the CLI's `--turn` isn't offered in the
  app.
- **Targets are a short fixed list.** No free text on the phone.
- **The kill trigger rests on one hand-build.** It judges one design;
  later designs are validated the same way but not hand-built.
