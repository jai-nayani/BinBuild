# Manual verification: a second read for every draft (Nov 1)

On `spike/integration`. Every draft piece list (82 read by Muse Wonder from
the pictured model, 18 transcribed from the book's "Elements you'll need"
box) got an **independent second Wonder read**, and the ones where the two
reads agree got **auto-generated booklet steps**. No hand-checks were
replaced: a person with the kit can still verify any build, and hand-checked
drafts are never touched by this tooling.

**Result: 40 of 100 drafts verified, 11 of them with a step-by-step booklet.
The other 60 stay unverified in the hand-check queue, each with the exact
lines where its two reads differ.**

## How it works

```
draft ──▶ second read (fresh Wonder conversation, same page photo(s), same
          owned-pieces constraint, same checker as the first read, no sight
          of the first list)
            ├─ agrees on every line (kind + count) ─▶ verified:
            │    "What can I build?" bin-checks it like house and tree
            └─ differs on any line, or gives no list ─▶ stays a draft;
                 the differences head its hand-check card
verified ──▶ steps: Wonder writes the pictured model in the validated
             design format, using exactly the verified list
               ├─ validator passes (stud grid, nothing floating, no
               │   overlaps, exactly the list) AND a separate Wonder
               │   conversation judges the drawn model the same as the
               │   book's picture ─▶ steps recorded, booklet generated
               └─ otherwise, after at most 5 retries ─▶ verified without
                    a booklet, with the reason named on the build's card
```

- **The picture check exists because the validator can't judge likeness.**
  In the pilot, Super Sprinter's design passed the stud rules only by moving
  its legs on top of its body. A second, separate Wonder conversation now
  compares drawings of the finished model (two opposite corners) with the
  page photo and sends differences back like validator errors.
- **Honest exits, no forcing.** Wonder may answer `Cannot: <why>` when the
  pictured model is held by clips, bars or side studs, or shows a piece on
  its side. A list containing the black 1x4 hinge plate gets no call at all:
  the validator has no geometry for it (no LDraw match), so its steps could
  not be checked.
- **What "verified" means here, and its limit.** Two independent
  conversations with the same model, same photos and same checker agreeing
  on every line is evidence, not proof: both reads can share a blind spot.
  Every such build says so in the app ("two reads of the page agree"), its
  booklet notes that nobody has built it from these steps yet, and a
  hand-check still overrides it. This is deliberately weaker than
  house-and-tree's hand-checked status, and the app labels them differently.

## Results

| | |
|---|---|
| Drafts given a second read | 100 / 100 |
| Two reads agree → verified | **40** (11 of the 18 hand drafts, 29 of the 82 Wonder drafts) |
| Verified with a booklet | **11**: apple-visitor, binoculars, birthday-cake-message, blueberry-cake, flying-bug, guitar, milky-way-shake-maker, paintbrush, rabbit-both-ears, radar-dish-station, stingray |
| Verified, no booklet | 29, each naming why (below) |
| Still in the hand-check queue | 60, differences listed first on each card |

**Why 29 verified builds have no booklet** (the reason is shown in the app,
never a fake booklet):
- **15** — the pictured model can't be written as pieces held by studs:
  eyes and faces mounted on side studs, flat lays butted edge-to-edge
  (e.g. dog-face, submarine's periscope, town-square-puzzle-2).
- **9** — the list uses the hinge plate, which the validator doesn't model
  (e.g. dozy-dolphin, happy-ghost, scaredy-bat).
- **5** — no design passed the checker and the picture check in 6 tries
  (mini-city-airplane, playful-plane, rabbit-half-listening, rocket-shuttle,
  super-sprinter).

**The printed totals as a cross-check.** Of the 4 builds whose page prints a
total, submarine (15) and mini-tugboat (10) agree across both reads and are
verified. Sailing ship and snappy crab disagreed by one line each (a lime
side-stud brick vs a white edge-stud tile; one dark purple 1x2 plate), so
they head the hand-check queue instead of being waved through.

**In the app** (against the confirmed inventory): 41 verified manual builds
(house-and-tree plus these 40), 12 with booklets. Verified-without-booklet
builds get the fit check and the named reason ("No step-by-step booklet:
… Build it from the book"). The printable checklist
(`GET /api/manual/checklist`) now lists only the 60 still waiting, with each
card starting from the lines where its reads differ; `manual_check` lists
the same queue.

## Cost

| Run | Builds | Calls | Cost |
|---|---|---|---|
| Pilot (reads + steps) | 3 | 7 | $1.45 |
| Full second reads | 97 | 97 | $11.43 |
| Steps, pilot redo (Super Sprinter) | 1 | 7 | $2.33 |
| Steps, full run | 38 | 85 | $20.45 |
| **Total** | | | **$35.66** |

Run logs (with Wonder's replies) are in git-ignored
`data/manual-verify/`; the per-draft cost recorded in the draft files totals
$34.75. Keys from `.env` only, never printed or committed.

## Files

| File | |
|---|---|
| `backend/manual_verify.py` | Second read, step generation with validator + picture check, `--report`, CLI (`--reads-only` / `--steps-only`, `--max-usd`, smallest-first) |
| `backend/build_plan.py` | `reads_agree` / `verified`; verified-no-steps builds get the bin check plus the named no-booklet reason; booklet notes state the two-reads provenance |
| `backend/booklet.py`, `backend/manual_check.py`, `app/app.js` | Checklist and queue show only what's still waiting, differences first; the app names the two-reads verification and counts booklets honestly (service worker v11) |
| `backend/manual/drafts/*.json` | Each draft gains `second_read` (and `auto_steps` + `steps` where a design passed) |
| `tests/test_manual_verify.py` | 16 tests, recorded replies only |
| `tests/test_manual_catalog.py` | Two tests fixed to cover the verified-steps-pending state the app already handled ("its steps haven't been worked out yet") instead of assuming steps were attempted |

## Tests

- **venv:** 199 tests in `tests/` plus Path A's 31, all passing.
- **System `python3`** (no Pillow): 199 run, 93 skipped, the rest pass.

## Next blocker

People with the kit. The 60-build hand-check queue is now targeted — each
card starts with the exact lines its two reads disagree on — and any
hand-check overrides the two-reads verdict. Start with sailing ship and
snappy crab: one differing line each, and a printed total to check against.
Nothing here has been hand-built yet; that stays the standard for the demo's
verified claims.
