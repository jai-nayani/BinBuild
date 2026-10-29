# Full-loop spike

Branch `spike/full-loop`. It starts from `spike/image-guardrails` (54a1479),
which sits on `spike/inventory-loop` (5f6a355) and `spike/pwa-camera` (549af89).
`spike/constraint-path-a` (882ee3c) is merged in unchanged: Path A's module,
its 31 tests and the pre-generated designs are byte-identical to that commit.

One camera batch now goes through every stage, with no hand-editing of data
between stages:

```
5 photos ─▶ photo gate ─▶ classify (stub segmenter + Spark) ─▶ review ─▶ confirm ─┐   undo ↺
                                                                                   ▼
            booklet ◀─ build: known set (exact pieces) or BrickGPT design (Path A) ◀─ inventory split
                                                                                       generator-ready │ everything else
```

No new model calls. The photo gate, the inventory loop and Path A are the
verified pieces, reused as they are. Live BrickGPT generation stays off, and
SAM 3.1 stays a stub.

## What's new

| File | What it does |
|---|---|
| `backend/build_plan.py` | The build step. **Known set:** every piece checked against the confirmed inventory (exact family, shape, size and colour); missing pieces are named. **BrickGPT design:** only the generator-ready bricks go to Path A's `plan_build`, which runs unchanged on a pre-generated design. The result is fit, patched, a named shortfall, or "not connected". Colours are assigned afterwards from the owned bricks of each size. `options()` lists everything, buildable first. Standard library only. |
| `backend/booklet.py` | A booklet is JSON (parts, steps, placements) and renders to one self-contained printable HTML page. Each step has an isometric SVG drawing: the new parts in full colour, earlier ones faded, and a callout of the parts to find. Draws bricks, plates, tiles, round bricks and plates, and curved slopes. Hidden studs and faces are skipped. Standard library only. |
| `backend/sets/house-and-tree.json` | The control target: 7 pieces, 5 steps. |
| `backend/full_loop.py` | Runs one batch through every stage via the HTTP API, on a throwaway database. Spark is replaced by a recorded reply (see below). `python -m backend.full_loop` |
| `tests/fixtures/kit-batch-recorded.json` | The recorded run on the kit batch: Spark's 50 pieces, its 5 real-LEGO answers, and the 13 review corrections. |
| `backend/main.py` | The 501 placeholders (`/api/generate`, `/api/builds/{id}`) are replaced by the build endpoints below. |
| `backend/inventory_db.py` | `create_build` / `get_build` on the existing `builds` table. Each build stores the inventory it was planned against. |
| `app/` | A "What can I build?" screen, reachable from the scan screen and from Finished. It lists buildable options first, then the rest under "Not enough pieces yet" with what is missing. "Make the booklet" stores the build and links to its booklet page. |
| `tests/test_full_loop.py` | 22 tests (see Tests). |

## API

| Endpoint | |
|---|---|
| `GET /api/builds/options` | Inventory totals (all, generator-ready, other), plus every known set and pre-generated design with `fit` / `patched` / `short` / `not_connected` and a message naming what is missing. |
| `POST /api/builds` | `{"set": "house-and-tree"}` or `{"design": "train", "samples": 6}`. Plans against the confirmed inventory and stores the build. Answers 201 with the result. A build that fits gets `booklet_url` and `steps`; a shortfall gets `shortfall` (BrickGPT) or `missing` (set), and no booklet. Unknown set or design: 404. Neither or both: 422. |
| `GET /api/builds/{id}` | The stored build: request, result, booklet JSON, inventory snapshot. |
| `GET /api/builds/{id}/booklet` | The booklet page (HTML). A shortfall build has none: 404 with the message. |

## Run 1: one batch through every stage (the success criterion)

`python -m backend.full_loop` on the real kit batch `20261028-192429-119901`.
It runs on a throwaway database, through the same endpoints the phone uses.

| Stage | Result | Time |
|---|---|---|
| 1. Upload 5 photos + photo gate | 201, all 5 passed, ready | 1.3 s |
| 2. Classify | 1 Spark call, recorded reply played back: real LEGO yes ×5, 50 pieces | 0.7 s (the live call took 44.3 s) |
| 3. Review + confirm | The 13 recorded corrections and 37 accepts sent to the review endpoint; 50 pieces confirmed | 0.01 s |
| 4. Split + build + booklet | Generator-ready 2, everything else 48, unknown 0. House-and-tree: **fit**, booklet with 5 steps. BrickGPT train: **short**, shortfall named | 0.04 s |
| 5. Undo → rebuild → confirm → rebuild | 50 removed → house-and-tree **short** (all 7 missing) → confirmed again → **fit** | 0.01 s |

The confirmed inventory equals the verified one in `binbuild.db`, row for
row: the 22 piece kinds in INVENTORY-LOOP.md, not the raw first count. Whole
run: about 2.6 s, 0 Baseten calls.

**What was replayed, and why that's honest:**
- **Classify.** The recorded reply is Spark's actual answer from the verified
  inventory-loop run on these 5 photos (50 pieces, 44.3 s, 8.9k prompt + 16.0k
  completion tokens).
- **The real-LEGO answers (yes ×5)** come from the image-guardrails run on the
  same photos, because the first run predates that check. So the replay
  combines two real runs.
- **Safety.** It is only played back when all 5 photos' sha256 match the ones
  it was recorded on. A test checks that it refuses other photos.
- **Review.** The 13 corrections are the ones a person made in the
  inventory-loop review. They go through `POST …/review` exactly as a review
  screen would send them.

## Run 2: the real database, through the app

The backend ran on the real `binbuild.db`, where this batch went through
upload, live Spark, review and confirm on Oct 28. The phone app's new
"What can I build?" screen (375 px wide) showed:
- "50 confirmed pieces in your inventory: 2 plain bricks BrickGPT can use, 48 other pieces."
- House and tree as buildable.
- The 10 BrickGPT designs under "Not enough pieces yet (10)".

"Make the booklet" stored build 1 and linked to its booklet page, which opened
with 5 steps. Build 2 (train) is stored as a shortfall.

## Control target: house-and-tree, **pass**

| Piece | Needed | In the corrected inventory |
|---|---|---|
| lime 1x6 plate | 1 | 1 |
| orange 1x2 brick | 2 | 2 |
| black 1x2 curved slope | 2 | 4 |
| light bluish gray 1x1 round brick ("grey round cylinder") | 1 | 4 |
| lime 1x1 round plate | 1 | 4 |

**The booklet:**
- A cover picture of the finished model and "Find these 7 pieces", with a
  small drawing of each.
- Then 5 steps, each with its parts callout, a picture and one plain sentence:
  1. green plate (the grass);
  2. 2 orange bricks side by side at one end (the walls);
  3. 2 black curved slopes, tall ends meeting in the middle (the roof);
  4. skip a stud, grey round brick (the trunk);
  5. green round plate on top (the treetop).
- It's 100 KB, has no scripts, prints, and reads at phone width.

**The arrangement is BinBuild's own.** Only the piece list came from the kit.
If the kit's picture puts them differently, the placements in
`backend/sets/house-and-tree.json` are the one thing to change.

## Stretch target: BrickGPT on the kit, **named shortfall (pass)**

The kit's generator-ready layer is 2 orange 1x2 bricks. The other 48 pieces
are plates, slopes, tiles and modified bricks, which BrickGPT's 8 brick types
can't use. Every pre-generated design falls short, and each shortfall is named.

Train (the smallest design, 37 bricks) through `plan_build` with N=6 took 1.2 ms:

> Short of 35 bricks: 11× 1x1, 8× 1x2, 5× 1x6, 1× 1x8, 1× 2x2, 3× 2x4, 6× 2x6. Bricks BrickGPT can use in your bin: 2× 1x2.
> (not patchable: short bricks cover 165 studs but spare pieces only 0)

All 10, closest first (short studs = the size of the shortfall):

| Design | Result | Short studs | Short |
|---|---|---|---|
| train | short | 165 | 1x1:11 1x2:8 1x6:5 1x8:1 2x2:1 2x4:3 2x6:6 |
| chair | short | 304 | 1x1:30 1x2:28 1x6:1 1x8:5 2x2:6 2x4:5 2x6:9 |
| bench | short | 314 | 1x1:10 1x2:12 1x4:5 1x8:7 2x2:5 2x4:5 2x6:12 |
| bed | short | 473 | 1x1:9 1x2:3 1x4:6 1x6:5 1x8:9 2x2:4 2x4:2 2x6:25 |
| car | short | 543 | 1x1:27 1x2:30 1x4:3 1x6:8 1x8:2 2x2:15 2x4:4 2x6:24 |
| bus | short | 564 | 1x1:10 1x2:1 1x4:8 1x6:10 1x8:7 2x2:2 2x4:3 2x6:31 |
| table | short | 570 | 1x1:12 1x2:15 1x4:1 1x6:4 1x8:14 2x2:12 2x4:2 2x6:27 |
| sofa | short | 674 | 1x1:8 1x2:10 1x4:3 1x6:5 1x8:17 2x2:3 2x4:6 2x6:34 |
| tower | not connected | 158 | the design has a separate 5-brick stack |
| bottle | not connected | 344 | the design has a lone 1x1 |

**Ranking.** Designs with a loose part are listed last, as REPORT.md
suggested. "Not connected" is a flaw in the design that no bin can fix.

**The BrickGPT booklet path is tested, but not on this bin.** On Path A's
test inventories:
- the chair fits and gets a booklet with one step per layer: 86 bricks in two
  colours, never more of a colour than owned;
- the train patches, and the booklet notes the swapped bricks.

## Stub vs real

| Piece | In this spike |
|---|---|
| Photo gate | Real: runs on the 5 photos every time (1.3 s for all 5, upload included). |
| Segmenter | Stub (whole photo). SAM 3.1 per-piece masks and crops are still the known gap; nothing here fakes them. |
| Spark | Real in run 2 (Oct 28); a recorded reply in run 1, by design: no new tokens. |
| Review | A person's corrections. Run 1 sends the recorded ones through the API. The app has no review screen yet. |
| Path A | Real and unchanged, on pre-generated designs; live generation is off. |
| Booklet | Real, for known sets and for Path A designs that fit. |

## Limits

- **One viewpoint.** Each picture shows the model from the front right; parts
  hidden behind others aren't shown. Step order (bottom up) is what keeps
  them reachable.
- **Approximate drawings.** Curved slopes and round parts are simplified
  shapes. Colours are approximations chosen by eye.
- **No stability check.** "Connected" (Path A) is not "stable", and nobody has
  built a BrickGPT booklet yet. The booklet says so.
- **BrickGPT colours are assigned, not designed:** largest owned pool first,
  in bands from the bottom up.
- **Known sets match the review's exact words.** If review calls a piece
  "round 1x1 brick" instead of "round brick", it won't count. The fix is a
  shape vocabulary (the taxonomy branch has one).
- **One known set.** For the trials, each extra set is one JSON file.
- **BrickGPT can't use most real pieces.** On this kit, BrickGPT can't build
  anything: 48 of 50 pieces are outside its 8 types. Kid bins with mostly
  plain bricks will do better. Bins like this one need known sets, or
  generation over more part types.

## Tests

`tests/test_full_loop.py`, 22 tests (standard-library unittest):
- **booklets:** placement sizes; hidden studs aren't drawn; a page with one
  picture per step, every part named and no scripts;
- **build plans on the corrected kit inventory:**
  - house-and-tree fits;
  - a missing piece is named and there is no booklet;
  - a different colour counts as a different piece;
  - shape spelling is normalised;
  - only generator-ready bricks reach BrickGPT;
  - train is short by exactly the table above;
  - chair fits with one step per layer and never over-uses a colour;
  - a patched design is noted in its booklet;
  - tower is not connected;
  - unknown requests fail;
  - options come in the right order;
- **API:** build and booklet; a shortfall has no booklet (404 with the
  message); bad requests; options; undo makes the set short, and confirming
  again restores it;
- **the whole loop:**
  - on drawn photos with one review correction;
  - on the real kit batch when it's on disk: 50 pieces, 22 kinds equal to the
    corrected inventory, house fits, train short;
  - the recorded reply refuses photos it wasn't recorded on.

**Totals:**
- venv: 83 tests in `tests/` plus Path A's 31, all passing:
  `python3 -m unittest discover -s tests` and
  `python3 -m unittest backend.test_brickgpt_constraint`.
- System `python3` without Pillow or FastAPI: 36 skipped, the rest pass.

## Next blocker for the Oct 30 – Nov 1 kid trials

The phone has no review-and-confirm screen: a kid's batch stops at "waiting
for review", and its pieces only reach the inventory (and so "What can I
build?") through the API. (Built next, on `spike/review-screen`:
[REVIEW-SCREEN.md](REVIEW-SCREEN.md).)
