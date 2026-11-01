# Trial fixes (Nov 1)

On `spike/integration`, after the Oct 31 kid trial. Two changes: the retake
pop-up named the wrong view, and a hand-checked manual build now gets a
booklet, like house and tree.

## 1. The retake pop-up named the wrong view

**What happened in the trial:** the backend flagged the front and right
photos as blurry (batch 20261101-040820-6d962d). Each pop-up showed the right
title and photo, but its big yellow button always said **"📷 Retake top
photo"**. So the front was retaken as a top-down shot, which is the photo now
stored as that batch's front view.

**Cause:** two elements had `id="retake-btn"`.
- The photo-review screen's "↺ Retake" button had it since the first PWA
  spike.
- The retake pop-up's button got the same id in the guardrails spike.
- `$('retake-btn')` returns the first one. So the pop-up wrote "Retake front
  photo" into the hidden review button. Its own button kept the page's
  default text, "Retake top photo", for every view.
- The backend named the right views throughout. The retake uploads went to
  the right views too.

**Fix:** the review screen's button is now `review-retake-btn` (in
`app/index.html`). The service worker cache moves to v10 (`app/sw.js`).

**Test:** `tests/test_retake_popup.py`, 5 tests.
- Every id on the page must be unique.
- The real `app/app.js` runs in Node against a fake page built from
  `app/index.html` (`tests/retake_popup_harness.js`). The harness plays a
  batch for each view failing alone, front and right together (as in the
  trial), and all five.
- For each pop-up, these must all name the same view:
  - its title;
  - its own Retake button (found inside the pop-up, not by id);
  - the photo it shows;
  - its "How:" hint;
  - the view the retake uploads to.
- On the old page these tests fail: "Retake top photo" for every view. With
  the fix they pass.
- Also checked in the browser on the trial's own photos:
  - before the fix, "The right photo is unclear" came with a "Retake top
    photo" button;
  - after it, title, photo and button say front, then right.

## 2. Hand-checked manual builds get the full treatment

Before, a hand-checked draft became verified with a bin check but **no
booklet**. Now verifying a draft means recording its steps while building
it, and the build gets everything house and tree has:
- a verified parts list;
- a fit check against the confirmed inventory;
- a step-by-step booklet with a drawing for each step.

**The hand-check tool** (`python -m backend.manual_check`):
- **Listing:** `manual_check` alone lists every draft, closest to verified
  first, with `*` on the 11 to start with.
- **Showing one:** `<id>` prints its checklist with numbered lines (`#n`),
  its steps so far, and what is still to place.
- **Recording steps:** `--record` asks what each step does, then where each
  piece goes, one step per layer.
  - Positions are `#n @x,y,z`: x and y in studs along the table, z in plates
    up (a brick is 3).
  - Add `along y` for a piece turned that way, and `down -x` for the way a
    slope falls.
  - It saves after every step and says what's left.
- **Steps without prompts:** `--step "TEXT :: #n @x,y,z; ..."` adds one;
  `--undo-step` and `--clear-steps` take them back.
- **Preview:** `--preview FILE.html` writes the booklet the steps make so far,
  to compare with the model.
- **Rules:**
  - a step may not place more of a piece than the list holds;
  - positions must be whole numbers, and z can't be below the table;
  - pieces whose boxes overlap get a warning only, since clips and side
    studs can't sit exactly on the grid.
- **`--done --by NAME`** is refused while a line is unsure, and until the
  steps place every piece on the list exactly once.
- **`--set` and `--sure`** also take `#n`. **`--undo`** keeps the steps.

**What happens after `--done`:** the draft's list and steps become a set,
the same shape as `backend/sets/house-and-tree.json` (`draft_set` in
`backend/build_plan.py`).
- "What can I build?" lists it among the verified builds, in book order,
  with a fit check.
- "Make the booklet" (`POST /api/builds {"set": id}`) draws the booklet from
  the recorded steps.
- A draft marked done without complete steps (only by editing the file)
  stays unverified: "draft list hand-checked, waiting for its steps".
- Nothing is invented. Until someone builds it and records it, a build keeps
  "Parts not verified yet", with no fit claim and no booklet.

**Order:** the printable checklist (`GET /api/manual/checklist`) and the
tool's list put the 11 closest first, each marked "start here":
1. **The 4 whose list matches the total the page prints:** submarine,
   sailing ship, mini-tugboat, snappy crab.
2. **The 7 hand drafts with no unsure lines:** Tiny Tentacles, Mini City car,
   Happy Ghost, Bake-a-cake-ephant, Playful Plane, Puppy Power, Rocket
   shuttle.
3. **Then the rest in book order, and hand-checked ones last.**

Checklist lines are numbered to match the tool.

**Now:** 1 verified build (house and tree) out of 106. 100 drafts are each
one hand-check away, steps included, from the same treatment. No draft has
been hand-checked yet: the hand-checks are done with the kit, and this
change is the tooling.

## Tests

- **venv:** 180 tests in `tests/` plus Path A's 31
  (`backend.test_brickgpt_constraint`), all passing.
- **System `python3` (no Pillow):** 180 run, 79 skipped, the rest pass.
- **New since the merges (166):** 14 tests.
  - 5 for the retake pop-up.
  - 9 for the hand-check:
    - steps needed for `--done`;
    - no steps means not verified;
    - bad steps;
    - `--record`;
    - `--preview`;
    - the closest-first listing;
    - the checklist order;
    - the checklist page;
    - a hand-checked draft's booklet through the API.
- The two old "hand-checked, no booklet" tests now check the full treatment
  instead: list, fit check, booklet.
