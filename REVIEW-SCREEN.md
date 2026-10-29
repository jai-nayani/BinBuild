# Review screen spike

Branch `spike/review-screen`, built on `spike/full-loop` (584c9f2). It closes
the gap FULL-LOOP.md named: on the phone, a batch used to stop at "waiting for
review", and its pieces only reached the inventory through the API. Now the
whole loop runs on the phone:

```
5 photos → photo check → Identify → Check the pieces → Add to my inventory → What can I build? → booklet
                                         ↑ fix / remove / add            ↺ undo
```

No new model calls, and nothing changes in the review rules: the screen uses
the existing review, confirm and undo endpoints.

## The screen

**Check the pieces** opens on its own after Identify. It can also be reached
from **Finished**, which now lists every batch on the backend, so a batch is
found again after a reload.

- **The top photo, pinned while the list scrolls,** with one dot per piece
  (Spark's centre point, in the piece's colour).
  - Tap a row: its pieces get yellow rings, the rest fade, and the caption
    names them.
  - Tap a dot: that one piece gets a big ring and its row is selected.
- **A summary line:** "50 pieces · 6 plain bricks BrickGPT can use · 2 fixed
  by you · 1 removed". It updates after every change.
- **Pieces grouped by kind,** plain bricks first: "4× lime 1x1 round plate",
  with badges "BrickGPT brick", "fixed" and "added by you".
- **Row actions:**
  - **✎ Fix all N** and **✕ Remove all N** act on the whole row.
  - **One by one ▾** lists each piece, with **✎ Fix** and **✕ Remove**, and
    "show on photo".
  - Removed pieces move to "Removed: not added to your inventory", with
    **↩ Put back**.
- **The fix form:**
  - It shows what the piece is now, then: kind of piece (plain words, e.g.
    "Tile (smooth, no studs)"), shape (with suggestions), size in studs,
    colour (with a swatch) and **Plain**.
  - A live line says whether BrickGPT can build with it ("✓ A plain 1x4
    brick: BrickGPT can build with it" or "BrickGPT can't build with this
    one… It still goes into your inventory").
- **＋ Add a piece Spark missed,** with How many.
- **✓ Add N pieces to my inventory,** pinned at the bottom.
  - It first marks every untouched piece as accepted, so the record shows a
    person looked at the whole batch, then confirms.
  - The confirmed card then shows the new totals ("Your inventory now has 56
    pieces: 7 plain bricks BrickGPT can use, 49 other pieces"), with **What
    can I build?**, **Scan the next handful** and **↺ Undo**.
  - Undo reopens the batch to check again. Only the last batch added can be
    undone; an older one says so.

## Backend additions

| Endpoint | |
|---|---|
| `GET /api/inventory/batches` | Every batch, newest first: state (uploaded / classified / confirmed), pieces (not removed), photos passed, and `undoable` (the batch an undo would take out). |
| `GET /api/inventory/batch/{id}/photos/{view}?size=1600` | One photo, turned upright (EXIF) and scaled down. The kit's 12 MP top photo comes back as a 1200×1600 JPEG of 262 KB in 0.15 s (Pillow's draft mode decodes it at reduced size). |
| `GET /api/inventory/batch/{id}/review` | Adds `count_photo`: the URL of the top photo plus its upright size in pixels, which is the frame Spark's piece points are in. |
| `GET /api/inventory/vocab` | Families, colours (each with a swatch colour), the 8 BrickGPT sizes, and suggested shapes (a fixed list plus every shape already in the database). |

## How it was checked

**In the browser at phone width (375 px).**
- **Setup:** a scratch backend (its own database and data folder; the real
  `binbuild.db` untouched), seeded with the real kit batch. The batch was
  uploaded and classified with the recorded Spark reply (no Baseten call).
- **What the screen showed:**
  - 50 dots landed on the 50 pieces, in 24 rows, with "50 pieces · 6 plain
    bricks BrickGPT can use". 6 is Spark's raw count, before review.
  - Selecting the blue 1x4 row ringed both blue bricks, and the photo stayed
    pinned while the list scrolled.
  - Fixing that row through the form (shape "brick with 4 studs on side",
    Plain unticked) took plain bricks from 6 to 4.
  - The user then tapped dots and confirmed that batch themselves in the pane.
    That's a fair test of confirm, but the review was only partly done, so
    that scratch inventory has 4 plain bricks, not the verified 2.
- **A second scratch batch (drawn photos, 5 pieces):**
  - fixing one piece of a row of three;
  - remove, put back, and remove again;
  - adding 2 missed pieces;
  - Add to inventory, the confirmed card and its totals;
  - Undo, which reopened the batch;
  - adding it again;
  - undoing the older batch, which was refused with the message.

**`tests/test_review_api.py`, 5 tests:**
- **The batch list:** states, removed pieces not counted, only the last
  confirmed batch is undoable.
- **The counted photo:** served upright and scaled. Spark's "at 0.5, 0.5"
  lands at the middle of the upright frame. A photo with an EXIF rotation is
  served portrait, with portrait dimensions.
- **The vocabulary.**
- **The screen's exact request sequence:**
  - fix a whole row, which leaves the generator layer;
  - fix one piece;
  - remove, put back, remove;
  - add 2;
  - accept the untouched pieces, then confirm, giving exactly the expected
    inventory;
  - review locked after confirm;
  - undo of the older batch refused, undo of the newer one reopens it.

**Totals:** 88 tests in `tests/` plus Path A's 31, all passing in the venv.
With the system `python3`, 40 are skipped for lack of Pillow or FastAPI and
the rest pass.

## Limits

- **Dots, not outlines.** Pieces show as Spark's centre points. Outlines and
  close-up crops per piece need SAM 3.1. Pieces added by hand have no dot.
- **Crowding.** 50 dots on a 375 px phone are tight; selecting a row is the
  readable way in.
- **One reviewer at a time.** Two phones reviewing the same batch: the last
  save wins.
- **Identify still lives on the scan screen.** A batch uploaded but not
  identified before a reload is listed, but can't be identified from Finished.
- **Not yet tried on a real phone with live Spark.** The browser tests used
  the recorded reply. TESTING.md section 8 is the phone checklist.
- **Review effort.** 13 of the kit's 50 pieces needed a fix. That's a lot for
  a child alone; plan on an adult checking with them.

## Next blocker for the Oct 30 – Nov 1 kid trials

There's too little to build. "What can I build?" has one known set, and the
smallest pre-generated BrickGPT design needs 37 plain bricks, so most real
kid bins will show nothing buildable.
