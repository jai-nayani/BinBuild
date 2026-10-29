# Integration spike

Branch `spike/integration`: one working app for the Oct 30 – Nov 1 kid trials.

```
aba3bbf spike/sam-3-1  (camera, guardrails, inventory loop, full loop, review screen, SAM opt-in, Path A)
  ├─ merge spike/manual-catalog  fde3fdd → f405008   (clean)
  └─ merge spike/wonder-designer eb82445 → 852585f   (one conflict: README.md, kept both)
```

Main is untouched (791b0a1), and there is no PR. No code had to be changed to
integrate; the merged tree passes every test as it is.

## The trial flow on the phone

1. **Snap 5 photos** (top, front, right, back, left). Each is reviewed: retake
   or use.
2. **Upload → photo gate.** A failed view opens a pop-up naming that view and
   the reason, with a Retake button for just that photo.
3. **Identify:** whole-photo Spark. SAM stays opt-in (`?segmenter=sam` or
   `BINBUILD_SEGMENTER=sam`); the default is the stub.
4. **Check the pieces:** dots on the photo; fix, remove or add pieces; then
   "Add N pieces to my inventory".
5. **Inventory totals** on the confirmed card: pieces, plain bricks, other
   pieces.
6. **What can I build?**
   - **Manual first:** house-and-tree highlighted as verified, with its fit
     check and 5-step booklet. The other 105 come by chapter, each with its
     status label and no fit claim, booklet or parts list.
   - **BrickGPT designs second** (Path A, pre-generated only).
7. **Booklet** for the verified build.
8. **Undo** takes the last batch back out (it's on the confirmed card).

The Wonder designer stays behind its CLI (`python -m backend.wonder_designer`),
and nothing in the app calls it. Simple House is not yet hand-built; its kill
trigger is the evening of Oct 31.

## Checks

### 1. The kit batch, end to end through the API

`python -m backend.full_loop` on `20261028-192429-119901`. It uses a
throwaway database and the recorded Spark reply (no Baseten call).

| Stage | Result |
|---|---|
| Upload + gate | all 5 photos passed |
| Classify | 50 pieces; real-LEGO check yes ×5 |
| Review + confirm | 13 corrections, 50 confirmed; equal row for row to the corrected inventory in INVENTORY-LOOP.md |
| What can I build? | first: house-and-tree **fit**, then the other 105 manual builds; first BrickGPT design: train **short** |
| Booklet | house-and-tree, 5 steps |
| BrickGPT | train: "Short of 35 bricks: 11× 1x1, 8× 1x2, 5× 1x6, 1× 1x8, 1× 2x2, 3× 2x4, 6× 2x6" |
| Undo → rebuild → confirm → rebuild | 50 removed → house-and-tree **short** → confirmed again → **fit** |

The same with `--sam` (recorded SAM replies) still reaches the corrected
inventory.

### 2. The phone layout at 375 px, through the app's own screens

**Setup:**
- A scratch copy of the backend on :8000, with its own database and data
  folder; the real `binbuild.db` was not touched.
- Spark played back from the recorded run, and only for the kit's own top
  photo.
- The browser has no camera, so the kit's 5 photos were fed into the app's
  camera input. The top photo went in darkened first, to try the gate.

**What happened:**
1. **Snap:** 5 photos, each through the "use photo" review; upload.
2. **Gate:** the dark top photo failed. The pop-up read "The top photo is
   unclear", "It's too dark. Turn on a light or move nearer a window.",
   "Please retake just this photo. Your other 4 photos are fine." with
   "📷 Retake top photo".
   - The retake with the real photo gave "✓ The top photo is clear now. All
     5 photos are clear".
3. **Identify:** the review screen opened by itself with 50 dots in 24 rows:
   "50 pieces · 6 plain bricks BrickGPT can use".
4. **Review:** the 13 corrections went through the screen's Fix dialog, 8
   rows in all. The screen then read "50 pieces · 2 plain bricks BrickGPT can
   use · 13 fixed by you".
5. **Confirm:** "✓ Added to your inventory … 50 pieces: 2 plain bricks
   BrickGPT can use, 48 other pieces".
   - The backend's inventory equals the corrected 50-piece inventory, row for
     row.
6. **What can I build?** "📕 From your manual (106 builds)":
   - house-and-tree first and highlighted: "Manual · chapter 2 · Go Wild in
     the City · page 28", "✓ Verified piece list", "✓ You can build this";
   - the only booklet button on the page;
   - 105 rows across chapters 1–4, none with a button;
   - then "🤖 BrickGPT designs (10)", with the train short by 35 named
     bricks.
7. **Booklet:** "Make the booklet", then "Open the booklet (5 steps)". It
   renders at phone width: the picture from page 28, 7 pieces, and 5 steps
   with a drawing each.
8. **Undo:** "↺ Took 50 pieces out of your inventory".
   - "What can I build?" then shows house-and-tree "Not enough pieces yet –
     Missing 1× lime 1x6 plate, 2× orange 1x2 brick, 2× black 1x2 curved
     slope, 1× light bluish gray 1x1 round brick, 1× lime 1x1 round plate",
     with no booklet button.

**Afterwards:** the real backend was restarted on this branch with the real
`binbuild.db`. It serves the same list: house-and-tree fit, and the manual
summary of 106 builds (1 verified, 18 drafts waiting, 87 not yet verified).

### 3. Tests

- **venv:** 144 tests in `tests/` plus Path A's 31, all passing. That's 104
  from the base, 19 from the manual catalog and 21 from Wonder.
- **System `python3`** (no Pillow or FastAPI): 57 skipped, the rest pass.
- **LDraw:** `verify_against_ldraw()` still finds no differences.

## On trial day

On the Mac, from the repo root on this branch:
```bash
.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
```
And in a second terminal:
```bash
python3 -m http.server 8080 --bind 0.0.0.0 --directory app
```

**On the phone:** open `http://<Mac's Wi-Fi address>:8080`, on the same
Wi-Fi. The backend dot should be green. TESTING.md sections 1–8 are the
step-by-step checks.

**Budget:** Identify calls Muse Spark live on Baseten, about 45 s and 25k
tokens per batch. SAM stays off unless you choose it.

## One line each

- **Merged cleanly:** the whole manual catalog (catalog, drafts, hand-check
  tool, "What can I build?", booklet changes) and the whole Wonder designer
  (format, validator, client, CLI, the Simple House design). The only file
  both touched was README.md.
- **Conflicted, and how it was resolved:** README.md alone. Both branches
  added a status paragraph in the same place, so both were kept. No code
  conflicts, and the merged tree passes every test unchanged.
- **Next blocker for the Oct 30 – Nov 1 kid trials:** the integrated app
  hasn't yet run on a real phone with live Spark. Every check above used
  recorded replies in a browser, so run one real batch on the phone at home
  before the first kid session.
