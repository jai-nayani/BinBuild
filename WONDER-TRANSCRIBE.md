# Wonder transcription: parts lists for the builds that print none

Branch `spike/wonder-transcribe`, built on `spike/integration` (334714a).

87 builds in the manual picture a model but print no list of its elements.
Muse Wonder (`muse-wonder-1.0`, Meta Model API) read the manual's page photos
and proposed a parts list for each one that shows a fixed model. It could only
use the kit's owned pieces, within their exact counts.

**Result: 82 draft piece lists, all within the kit and all still unverified.**
- The other 5 of the 87 are pure activities (Chance Creatures, Mirror People,
  Reindeer, Long-Flight Airplane, Crazy Color Game). They have no draft and stay
  not-yet-piece-verified.
- Every draft says `"status": "draft"` and warns that it is not a verified
  piece list. The catalog still lists all 87 builds as not-yet-piece-verified.
- Drafts make no fit claim and get no booklet. A hand-check makes a draft
  verified and gives it a bin check, as with the 18 hand drafts.
- **100 builds are now one hand-check away from verified:** the 18 transcribed
  by hand plus these 82.

## How it works

```
page photo(s) ─┐
               ├─▶ Wonder (reasoning effort high) ──▶ reply ──▶ checker ──ok──▶ backend/manual/drafts/<id>.json
owned pieces ──┘                                ▲                   │ errors
 (21 kinds, exact counts,                       └── one retry ──────┘──▶ still wrong: nothing written
  what each one looks like)                        (same conversation, errors only, no images)
```

**What Wonder receives for each build:**
- the manual photo(s) of its page(s);
- the build's name and pages;
- the printed element total, where the page gives one;
- the kit's 50 pieces in 21 kinds. Each kind comes with its code, colour, size,
  exact count and a plain description of its shape (from the LDraw piece table
  in `backend/wonder_design.py`).

**What the checker rejects:**
- any line that is not an owned code, colour and size;
- any kind listed above its owned count;
- an unsure line with no reason;
- the wrong build id;
- an empty list for a fixed model.

Lines of the same kind are merged.

**What Wonder may say instead:** "no fixed model", with a reason. That writes
nothing.

**What a draft holds:** it has the same fields as the 18 hand drafts, plus:
- `read_by`;
- `seen` (what Wonder saw);
- `count_note`;
- `count_check` (printed total against the list's total), where a total is
  printed.

| File | |
|---|---|
| `backend/manual_transcribe.py` | The transcriber: scope, prompt, checker, retry, draft writer, CLI. |
| `backend/manual/photos.json` | Which manual photo shows which page (87 pages, 48 photos). File names only; the photos stay on the Mac. |
| `backend/wonder_client.py` | `respond()` now takes images (sent as data URLs). |
| `backend/booklet.py` | The printable checklist covers the Wonder drafts, as described under "Hand-checking". |
| `backend/manual/drafts/*.json` | 82 new drafts (the 18 hand drafts are untouched). |
| `tests/test_manual_transcribe.py` | 13 tests. |
| `tests/fixtures/wonder-transcribe-recorded.json` | 3 of Wonder's live replies, replayed in the tests. |

Rerun one build (replaces only an earlier Wonder draft, never a hand draft or
a hand-checked one):

```
python -m backend.manual_transcribe --builds snappy-crab --force
```

## Pilot first: good after two prompt fixes

The pilot used 3 builds with printed totals (submarine 15, sailing ship 8,
snappy crab 9).

Every reply passed the checker on the first try: owned pieces only and no
count exceeded. The unsure lines were sensible. Comparing the crab with its
photo turned up a problem the checker cannot catch, which was caused by my
prompt.

1. **The crab's body is the kit's black 1x4 hinge plate.** I had left the
   hinge plate out because it matches no LDraw part. Wonder still had to
   reach the printed 9, so it filled the gap with a blue side-stud brick and
   two black curved slopes. Fixes:
   - The hinge plate is now in the transcription list. A parts list needs no
     LDraw geometry, unlike a Wonder design. **This deviates from "49 usable
     pieces": transcription uses the kit's 50.**
   - The prompt now says never to add or swap pieces to reach a printed number.
     A mismatch goes in `count_note` instead.

   On the rerun the crab listed the hinge plate, with an unsure line saying its
   middle is hidden behind the body.
2. **Wonder skipped examples inside activities inconsistently.** In the main
   run it drafted the dog face but called the rabbit, frog and giraffe faces
   "no fixed model". 33 builds were skipped this way. The cause was my rule,
   which named "build your own" pages as having no fixed model. Fix:
   - A named example that is pictured as one model counts as a fixed model.
   - "No fixed model" is only for variants mixed together, a model described
     only in words, or one too small or hidden to read.

   On the rerun all 33 became drafts.

After the fixes:
- All 4 printed totals match: submarine 15/15, sailing ship 8/8, mini-tugboat
  10/10, snappy crab 9/9.
- I compared the sailing ship, mini-tugboat and crab with their photos, and the
  lists agree with what the pictures show.
- Across all 118 calls the checker rejected nothing, so no retry was needed.

## What the 82 drafts look like

- **Kinds:** 52 examples, 14 showcases, 13 build boosts, 3 puzzles.
- **Size:** 3 to 22 elements each, median 8. 723 elements in all.
- **543 of the 723 elements (75%) are marked unsure.** Only one draft
  (Bake-a-cake-ephant) has no unsure lines. That is deliberate: Wonder was told
  to flag every doubt. Of the 385 unsure lines:
  - about 290 are about hidden pieces;
  - about 160 are about colours the book prints differently (lime looks
    yellow, light grey near-white, dark purple near-blue);
  - 20 say no listed piece matched well, so Wonder gave the closest one and
    described what it actually saw.
- **73 drafts have a count note**, mostly saying how many pieces are probably
  hidden.
- **The hinge plate appears in 14 drafts:** crab, frog face, the two mermaids,
  shark, scaredy bat and others. The kit has one, so each of those builds needs
  it once.

**Limits:**
- Wonder reads a picture of the finished model. Pieces fully inside a model
  can be missing, and the hand-check is where they get found.
- The drafts use only the kit's pieces. If the book's model needs a piece the
  kit doesn't have, the draft shows the closest owned piece as an unsure line,
  not the missing piece.

## Hand-checking (unchanged flow, now 100 drafts)

The same tools cover the new drafts:
- `python -m backend.manual_check` lists all 100 drafts. `<id>` shows one,
  `--sure` and `--set` fix lines, and `--done --by NAME` records the check.
  `--done` is refused while unsure lines remain.
- `GET /api/manual/checklist` is the printable page with all 100 cards:
  - the header counts the Wonder drafts (82);
  - an intro note says Wonder lists come from the picture, so build the model
    before ticking;
  - each Wonder card has a "read by Muse Wonder" badge, the page's printed total
    where there is one, and Wonder's count note.
- A hand-checked Wonder draft becomes **verified** with a bin check
  ("Build it from the book: …"), still without a booklet. A test covers this.

## Cost and time

| Run | Builds | Calls | Cost | Wall time |
|---|---|---|---|---|
| Pilot | 3 | 3 | $0.40 | 114 s |
| Crab rerun (hinge plate fix) | 1 | 1 | $0.22 | 126 s |
| Main run | 79 | 79 | $7.42 | 589 s |
| Pilot rerun (no-padding fix) | 2 | 2 | $0.28 | 93 s |
| Skipped-examples rerun | 33 | 33 | $3.38 | 275 s |
| **Total** | | **118** | **$11.69** | **20 min** (111 min of model time, 4–6 in parallel) |

That averages about $0.14 per final draft, within the approved $0.20–0.30 per
build. The reruns cost $3.88 of the total.

## Safety

- The key comes from `META_MODEL_API_KEY` in `.env`. It is never printed,
  logged or committed.
- Only the manual's page photos were sent. The old phone test batch was not
  touched.
- The converted photos (`data/manual-photos/`) and the run logs
  (`data/manual-transcribe/`) are in git-ignored `data/`.
- Text inside the manual's pictures is treated as part of the book, never as
  an instruction.

## Tests

- **`tests/test_manual_transcribe.py`** has 13 tests and makes no Model API
  call. It covers:
  - the scope (82 builds, every one with a photo) and the 50-piece list;
  - the checker's rules;
  - the retry loop and "no fixed model";
  - the draft format;
  - that hand and hand-checked drafts are never overwritten;
  - that a hand-checked Wonder draft gets a bin check and no booklet;
  - three recorded live replies that replay into the committed drafts.
- **`tests/test_manual_catalog.py`** splits drafts into 18 hand and 82 Wonder.
  Every Wonder draft is checked to be for a not-yet build that isn't an
  activity, to carry the warning, and to match the printed total where one
  exists.
- **Results:**
  - venv: 158 tests pass;
  - `backend.test_brickgpt_constraint`: 31 pass;
  - system `python3` (no Pillow): 158 run, 67 skipped, the rest pass.

## Next blocker

People with the kit to hand-check. 100 drafts at 5–10 minutes each is more
than the trials allow, so pick the builds the kids will try. Start with:
- the 4 whose printed totals match (submarine, sailing ship, mini-tugboat,
  snappy crab);
- the 7 hand drafts with no unsure lines.
