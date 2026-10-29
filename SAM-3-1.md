# SAM 3.1 spike

Branch `spike/sam-3-1`, built on `spike/review-screen` (e05a560). The
whole-photo segmenter stub now has a real SAM 3.1 implementation behind the
same `Segmenter` interface.

```
whole-photo pass (Spark: real-LEGO check, 50 labels, a centre point per piece)
  → SAM 3.1: one mask per point          (Meta Model API, 16 points per request)
  → one close-up per piece, outside its mask darkened, on numbered contact sheets
  → Spark checks each whole-photo label against its close-up
  → review (outlines on the photo) → confirm → build → booklet
```

The 50 points come from the verified whole-photo run, the same `region.point`
values the review screen already shows. The photo gate, review/confirm/undo,
the build step and the review screen are unchanged. Live generation stays off.

## The Model API, as documented

Everything below is from Meta's docs at dev.meta.ai; nothing was guessed.

| | From the docs | Page |
|---|---|---|
| Model | `sam-3.1` | /docs/models |
| Endpoint | `POST https://api.meta.ai/v1/responses`, `Authorization: Bearer <key>` | /docs/sam/segmenting |
| Point prompt | text tokens `<0f>1<\|point;x=..;y=..;w=..;h=..\|>`, in pixels of the image sent | /docs/sam/segmenting |
| Limit | 16 prompted objects per request | /docs/sam/segmenting |
| Reply | per object, one box and one box-local mask, under the prompt's id; masks are base85 with a range-coded payload | /docs/sam/reading-segmentation |
| Decoder | Meta's `meta-sam-parser` 0.1.0 (Python, no dependencies, SAM License). I read its source before installing it: no network or shell calls. | /docs/sam/client-libraries |
| Price | $2.50 per 1,000 images; 3,000 requests per minute | /docs/pricing-rate-limits |

**Key handling.** `META_MODEL_API_KEY` (or the docs' name, `MODEL_API_KEY`)
comes from the environment or from the git-ignored `.env`.
- Without it, the request fails before any call: "SAM 3.1 is not set up: no
  Meta Model API key: put META_MODEL_API_KEY=<key> in .env on this Mac"
  (HTTP 503).
- The key is never printed or logged, and it is scrubbed from errors.

## What was run, and what it cost

**Model API: 5 requests in total.**
- One probe: 2 points, 2.0 s.
- The batch: 4 requests (16 + 16 + 16 + 2 points), 2.5 + 4.6 + 2.9 + 1.2 =
  11.2 s, sent one after another.
- Each reply reported `images_processed: 1`.
- Cost: $0.01 for the batch ($0.0125 with the probe).
- The batch's requests now go in parallel. That should take about as long as
  the slowest one (~5 s), but I haven't measured it live.

**Baseten (Spark) to name the close-ups:** 8 calls, in two runs of 4 sheets
each, the sheets sent at once.

| Run | Time | Tokens |
|---|---|---|
| Close-ups alone | 53 s | 26.2k prompt + 36.0k completion |
| Close-ups checking the whole-photo labels (the default) | 48 s | 27.7k prompt + 28.4k completion |

**Per batch:** the SAM pass adds about a minute (SAM ~11 s, the close-up
check ~48 s, local cropping ~4 s) to the 44 s whole-photo pass.

## Masks: 50 of 50

- Every point got a mask. Confidence ran 0.84–0.97 (median 0.95); the lowest
  were 27, 10 and 36, all of which look right.
- No two masks overlap (no double count), and no point fell on bare table.
- I checked every mask on an overlay of the photo, and zoomed in on the outline
  for the hard cases:
  - the orange bricks: the glow beside them is light on the table, outside the
    mask;
  - the three transparent plates;
  - touching pieces: 11/13, 21/22, 30/31.
- **No piece has a mask worse than the whole-photo count.**

## Classification against the corrected inventory

The reference is each piece's verified label (INVENTORY-LOOP.md, 13
corrections). "Needs a correction" means family, size, colour or plain is
wrong; shape wording alone is counted apart.

| | Whole photo (baseline) | SAM close-ups alone | SAM close-ups checking the whole-photo labels (default) |
|---|---|---|---|
| Pieces counted | 50 | 50 | 50 |
| Need a correction | **13** | 33 | **11** |
| Fixed vs the baseline | — | 3 (12, 41, 49) | 2 (12, 49) |
| Broken vs the baseline | — | 23 | **0** |
| "Plain" generator-ready bricks (true: 2) | 6 | 1 | 3 |

**Close-ups alone were worse.** Each tile is zoomed to fill its square, so:
- size is lost: every 1x1 round part became "2x2", and 1x2 plates became 1x3;
- colour loses its reference: grey became white, black became trans-black,
  orange became yellow, magenta became dark pink.

So the default sends Spark each close-up with the whole-photo label. Spark
keeps that label unless the close-up clearly shows otherwise.

**What the close-ups fixed:**
- 12: trans-clear plate, 1x3 → 1x2.
- 49: blue 1x4 brick; side studs found, no longer plain.
- 7 and 8: lime tall bricks, now not plain. Their size is still wrong, but they
  no longer count as BrickGPT bricks.

**Still needing a person (11):**
- 7, 8: called 1x2, really 1x1 tall bricks with side studs.
- 17, 28: cheese slopes; 17 still called a tile, and both medium azure instead
  of medium blue.
- 30, 31: curved slopes still called tiles.
- 35, 47: trans-clear plates still 1x3.
- 40: tile with studs on edge, still called a plate; the size also went
  2x2 → 1x2.
- 41: clip plate still 1x3.
- 46: the other blue side-stud brick, still plain.

One piece needs only a shape-wording fix.

## The whole loop with SAM

`python -m backend.full_loop --sam` runs on the real kit batch through the API
the phone uses, with no hand edits. SAM's and Spark's replies are played back
from `tests/fixtures/kit-batch-sam-recorded.json`; a reply is used only for
the exact request it was recorded for.

1. Upload: all 5 photos pass the gate.
2. Classify: the whole-photo pass, then SAM gives 50 masks for 50 points, and
   4 close-up sheets are checked.
3. Review: 11 corrections plus 1 shape wording, then confirm. The inventory
   equals the verified one, row for row.
4. Build: house-and-tree fits and gets its 5-step booklet; the BrickGPT train
   is a named shortfall.
5. Undo, then confirm again, works.

Without `--sam` the loop is unchanged: 13 corrections, same inventory.

## How to turn it on

- **One request:** `POST /api/inventory/batch/{id}/classify?segmenter=sam`.
- **Everywhere (the phone included):** start the backend with
  `BINBUILD_SEGMENTER=sam`.
- **How it runs:** a batch already classified by the whole-photo pass (and not
  yet reviewed) gets just the SAM pass.
- **If SAM fails:** the whole-photo proposals stay for review, and the error
  says so.
- **The default is still the stub,** so the trials don't take the extra
  minute unless you choose it.

**On the review screen,** each piece SAM cut out gets its outline on the
photo; the selected row's outlines turn yellow. Dots stay for tapping.

## Code

| File | |
|---|---|
| `backend/sam_client.py` | The Model API client: documented request, Meta's parser, key from `.env`, outline tracing (straight runs collapsed: 144 KB → 52 KB for 50 pieces). |
| `backend/segmenter.py` | `SamSegmenter`: same `segment(image) → [Region]` interface; one region per point. `Region` gains an optional `point`. |
| `backend/inventory_pipeline.py` | `refine_with_sam`: masks, close-ups, contact sheets, Spark's check, overlapping-mask flags. Plus `mask_overlay` for checking by eye. |
| `backend/spark_client.py` | `tile_prompt` / `name_tiles`. The whole-photo prompt is byte-identical to before. |
| `backend/main.py` | `segmenter=sam` on classify; `BINBUILD_SEGMENTER`. |
| `backend/full_loop.py` | `--sam`, `ReplaySam`. The review now brings each piece to its verified label and counts the corrections. |
| `app/` | Outlines on the review photo. |
| `tests/test_sam.py` | 16 tests (below). |

`tests/test_sam.py`:
- **Client:** the documented request; one_bit replies built with Meta's
  encoder, and the recorded lossless replies, both parse; the key from `.env`,
  a clear error without it, never in an error; at most 16 points.
- **Segmenter:** chunking, scaling back to the photo, a point with no mask.
- **SAM pass:**
  - one proposal per point named from its close-up;
  - the whole-photo label kept where there's no mask;
  - overlapping masks flagged;
  - hints sent;
  - refused after review or confirm;
  - nothing sent while a photo needs a retake.
- **API:** no key gives 503 before any call; an unknown segmenter gives 422.
- **Full loop on the kit batch:** with SAM and without.

Totals: 104 tests in `tests/` plus Path A's 31, all passing in the venv. With
the system `python3` (no Pillow, FastAPI or parser), 56 are skipped and the
rest pass.

## Limits

- **SAM confirms the count; it doesn't make it.** Point prompts can't find a
  piece the whole-photo pass missed (none were missed here). SAM's text-prompt
  mode could count independently; that's untested.
- **One batch:** a flat layer of well-separated pieces on a dark table. Piles,
  touching clusters and light tables are untested.
- **11 of 50 pieces still need a person.** Side studs, curved versus flat tops
  and transparent stud counts remain the hard cases.
- **Cost of the extra pass:** about one minute and ~56k Spark tokens per batch,
  on top of the whole-photo pass, for 2 fewer corrections.

## One line each

- **Model API cost/time:** 4 SAM requests for the batch, 11.2 s, $0.01 ($2.50
  per 1,000 images). The close-up check adds 4 Spark calls (48 s, ~56k
  tokens), about a minute per batch in all.
- **What SAM improved:** a clean, separate mask for all 50 pieces, shown as
  outlines in review, and 2 fewer corrections (11 instead of 13) with nothing
  made worse. False BrickGPT bricks fell from 4 to 1.
- **What it didn't:** the count (50 points in, 50 masks out; it can't find
  missed pieces) and 11 corrections still needed. Close-ups without the
  whole-photo labels were much worse (33 of 50).
- **Next blocker for the Oct 30 – Nov 1 kid trials:** too little to build.
  "What can I build?" has one known set, and the smallest BrickGPT design
  needs 37 plain bricks, so most real kid bins will show nothing buildable.
