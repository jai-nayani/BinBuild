# Inventory loop spike

Branch `spike/inventory-loop`, built on `spike/pwa-camera`. One phone batch goes
all the way into a SQLite inventory:

```
upload (5 photos) → classify (segmenter + Muse Spark) → review / correct → confirm → summary
                                                                  ↑ undo last batch
```

Tested on the real kit batch `data/batches/20261028-192429-119901/`: 50 pieces in
one flat layer on a dark table, 5 views (top, front, right, back, left).

## What's here

| File | What it does |
|---|---|
| `backend/inventory_db.py` | SQLite (`binbuild.db`, git-ignored): `batches`, `batch_photos`, `detections`, `inventory_items`, `builds`. Idempotent register/confirm, undo of the last confirmed batch, the two-layer summary. Standard library only. |
| `backend/inventory_vocab.py` | Generator types, families and BrickLink colour names, matching branch `spike/inventory-taxonomy` (reference only, not merged). Lenient normalising for model output, strict checks for corrections. |
| `backend/segmenter.py` | `Segmenter` interface (`segment(image) → [Region(bbox, mask)]`), the `WholePhotoSegmenter` stub, and `FixedRegionSegmenter` for hand-picked crops. |
| `backend/spark_client.py` | Muse Spark through Baseten only: `https://inference.baseten.co/v1`, model `meta-models/muse-spark-open-1026`. Key from `BASETEN_API_KEY` in the environment or `.env`; never printed, logged or put in an error. Standard library only. |
| `backend/inventory_pipeline.py` | Turns photos upright (EXIF), crops each region, sends it with the 4 side views as context, stores Spark's answer as proposed detections. Needs Pillow. |
| `backend/main.py` | The endpoints below. Upload now also hashes the photos and registers the batch. |
| `tests/test_inventory.py` | 32 stdlib `unittest` tests: database, review, confirm, undo, summary, vocabulary, Spark client (no network). |

## API

| Endpoint | |
|---|---|
| `POST /api/inventory/batch` | Unchanged for the phone. A byte-identical re-upload returns the existing batch with `"duplicate": true` (HTTP 200) instead of a second copy. |
| `POST /api/inventory/batch/{id}/classify` | Segment + Spark; stores proposals. A batch uploaded before the database existed is registered from its `batch.json`. Already classified → returned as is unless `?force=true`. `?context=false` skips the side views. About 45 s for 50 pieces. |
| `GET /api/inventory/batch/{id}/review` | Photos and proposals, with corrections so far. |
| `POST /api/inventory/batch/{id}/review` | `{"corrections": [{"detection_id", family?, shape?, size?, color?, plain?, count?, status?: "accepted"/"rejected"}], "additions": [{family, shape, size, color, plain, count}]}`. The first correction keeps the proposed values in `original`. |
| `POST /api/inventory/batch/{id}/confirm` | Copies kept pieces into the inventory. Repeating it adds nothing (`"already_confirmed": true`). |
| `POST /api/inventory/undo-last-batch[?batch_id=…]` | Removes the last confirmed batch's pieces and reopens it for review. With `batch_id`, a retried undo can't take out a second batch (409). |
| `GET /api/inventory/summary` (and `GET /api/inventory`) | Generator-ready: the 8 BrickGPT types × colour. Everything else: by family × colour. Unknown on its own. Plus the item list. |

A piece is generator-ready only when it is a **plain** brick (no side studs,
holes, rounding, …) in one of the 8 sizes. Plates and modified bricks never are.

## Results on the real batch

Reference: the human count is 50. The per-piece reference below is my own
reading of the 5 photos at full resolution (zoomed crops for the doubtful
pieces); only the total and the house-and-tree set came from a person.

### 1. About 15 pieces first (a 14-piece crop of the top view)

| Run | Count | Pieces needing a correction |
|---|---|---|
| Prompt v1, side views | 14 / 14 | 6: black curved slopes ×2 → tile, grey curved slope → white 1x4 tile, blue 1x1 cheese slope → tile, trans-clear 1x2 plate → 1x3, white 2x2 tile with studs on edge → plain plate |
| Prompt v1, no side views | 14 / 14 | 5: same except the trans-clear plate |
| Prompt v2, no side views | 14 / 14 | 6: as v1 with side views, but the grey slope keeps its colour |
| **Prompt v2, side views** | 14 / 14 | **3**: blue cheese slope → tile, grey curved slope → 1x4 tile, white 2x2 → plate |

Prompt v2 adds three general notes on how pieces look from straight above
(slopes can look like tiles; transparent parts show the tube underneath; partial
studs mean not plain). It was written after these crop runs, so the crop results
for v2 are not independent.

### 2. Full 50 (whole-photo stub, prompt v2, side views, through the API)

**Count: 50 / 50.** 44 s, 8.9k prompt + 16.0k completion tokens, one call.
Every one of Spark's 50 centre points lands on a distinct piece with the right label.

13 of 50 pieces needed a correction:

| Spark said | Correct | Pieces |
|---|---|---|
| lime 1x2 brick, plain (generator-ready) | lime tall 1x1 brick with 2 studs on side, not plain | 2 |
| blue 1x4 brick, plain (generator-ready) | blue 1x4 brick with 4 studs on side, not plain | 2 |
| trans-clear 1x3 plate | trans-clear 1x2 plate | 3 |
| lime 1x3 plate with clip | lime 1x2 plate with clip | 1 |
| black 1x2 tile | black curved slope | 1 |
| light bluish gray 1x3 tile | light bluish gray curved slope | 1 |
| medium azure 1x1 tile | medium blue 1x1 cheese slope | 2 |
| white 2x2 plate, plain | white 2x2 tile with 2 studs on edge | 1 |

The first two rows matter most: without review they would have put 4 pieces
into the generator layer that are not plain bricks (Spark's generator layer was
6; the correct one is 2).

The same photo without side views also counted 50 but needed 14 corrections
(it also called the blue 1x4s plates and the magenta plates bright pink).

### Confirmed inventory (after review)

| Layer | Pieces | By colour |
|---|---|---|
| Generator-ready 1x2 | 2 | orange 2 |
| Other generator types | 0 | |
| brick (round, modified) | 10 | light bluish gray 6, lime 2, blue 2 |
| plate | 23 | lime 7, white 4, dark purple 4, trans-clear 3, magenta 2, medium azure 2, black 1 |
| slope | 10 | black 4, light bluish gray 2, medium azure 2, medium blue 2 |
| tile | 5 | white 5 |
| unknown | 0 | |
| **Total** | **50** | |

House-and-tree set (7 pieces), all present: lime 1x6 plate 1/1, orange 1x2
brick 2/2, black curved slope 4/2, grey round 1x1 brick 4/1, lime 1x1 round
plate 4/1. Spark had all of these right before review.

Checked through the API on the real batch: confirm twice (second adds 0),
review of a confirmed batch (409), duplicate upload of the same 5 photos (same
batch id, no new folder), undo with the wrong expected batch (409), undo
(50 removed), retried undo (409), re-confirm (50 back).

## Stub vs real SAM

Working now with the stub: the whole loop, the database, review, confirm, undo
and summary. Counting a clean single layer of about 50 well-separated pieces
was exact, and Spark's centre points were accurate enough to locate each piece.

Still needs SAM 3.1:
- **Per-piece masks and crops.** The review screen can only point at a piece
  (Spark's centre point), not outline or crop it.
- **Size and shape at full resolution.** Most corrections were fine detail
  seen small in a whole photo: studs on a side face, a tube through clear
  plastic, a curve read as flat. A SAM crop per piece lets Spark see each one
  close up. That needs a single-piece prompt; the current prompt counts many
  pieces at once.
- **Counting that doesn't depend on the classifier.** With SAM the count is the
  number of masks, and Spark only names them. Touching pieces, piles and
  batches much bigger than 50 are untested with the stub; one call already
  used 16k output tokens for 50 pieces.
- **Matching across views.** Linking a piece in the top view to the same piece
  in the side views needs per-view segments.

Spark's centre points (stored as `region.point` on each detection) can be the
point prompts for SAM, so the interface change is small: a `SamSegmenter`
returns one `Region` per mask, and the pipeline already crops and classifies per
region.

## Run

```bash
.venv/bin/pip install -r backend/requirements.txt     # adds Pillow
python3 -m unittest discover -s tests -v                # from the repo root
B=20261028-192429-119901
curl -X POST localhost:8000/api/inventory/batch/$B/classify
curl localhost:8000/api/inventory/batch/$B/review
curl -X POST localhost:8000/api/inventory/batch/$B/confirm
curl localhost:8000/api/inventory/summary
```
