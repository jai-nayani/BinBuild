# Manual catalog spike

Branch `spike/manual-catalog`, built on `spike/sam-3-1` (aba3bbf). The manual
that came with the 50-piece kit (LEGO 5-Minute Builds) is now the build list.
Every build in it is shown in "What can I build?", manual first and BrickGPT
designs second, with no invented parts lists anywhere.

## Where the catalog came from

The Oct 28 report (`~/workspace/hackathon/manual-2026-10-28/REPORT.md`) is
**not on this Mac**: there is no `~/workspace`, no copy anywhere in the home
folder, and no other session mentions it. The 48 photos are here (Downloads,
`lego manual`, taken Oct 28). So the catalog was rebuilt from the photos, read
page by page on Oct 29, and checked against the facts given for the Oct 28
reading:

| Fact | Oct 28 | Rebuilt from the photos |
|---|---|---|
| Photos | 48 | 48 (IMG_3583–3631; there is no IMG_3595) |
| Chapters | 4 | 4: Watery Worlds (p8–27), Go Wild in the City (p28–51), Up, Up and Away (p52–73), Adventures in Space (p74–96) |
| Pages | 8 to 96; 1–7 not photographed, 34–35 missing | same |
| Printed element totals | submarine 15, sailing ship 8, mini-tugboat 10, snappy crab 9, house and tree 7 | the same 5, and no others |
| Distinct builds | **80** | **106**, by the rule below |

**The count differs.** The rule used here:
- **One entry per model the manual names,** by a page title, a label, a caption
  or the page text.
- **One entry per activity whose example models are unnamed.**
- **Unnamed extra models** are mentioned in the note of the build they appear
  with, not counted.

The Oct 28 rule isn't recorded anywhere I can see, so the two lists can't be
matched entry by entry. Every entry here is a model pictured in the book; none
is made up.

With the Oct 28 list, reconciling is a data edit in
`backend/manual/catalog.json` (merge or drop entries); the app and tests follow
the file.

## The catalog: `backend/manual/catalog.json`

**Each build** has an id, name, chapter, page(s), kind and piece-list status,
plus a note quoting the caption where useful.
- **Kind:** 15 instructions, 15 showcase, 52 activity examples, 13 Build Boost
  extras, 6 puzzles, 5 activities.
- **Printed total:** given only where the page prints one.
- **Parts lists:** none, for any build. The verified build links to its known
  set instead.

| Status | Builds | Meaning |
|---|---|---|
| verified | **1**: house and tree | Piece list checked against the kit's confirmed inventory; booklet exists. |
| diagram-readable | **18** | The page shows exactly which elements the build needs, legible in the full-size photo. Nothing transcribed or checked yet. |
| not-yet-piece-verified | **87** | The page pictures the model but lists no elements. 4 of these have a printed total (submarine 15, sailing ship 8, mini-tugboat 10, snappy crab 9), but which elements isn't given. |

**The 18 diagram-readable builds:**
- 15 have an "Elements you'll need" box: Dozy Dolphin, Yoga Goose, Viking
  longboat, Tiny Tentacles, Inspector Duck, Mini City car, Happy Ghost, Hungry
  Elephant, La-La Llama, Bake-a-cake-ephant, Hot-air Balloon, Playful Plane,
  Space Rocket, Supergalactic Hero, Puppy Power.
- 3 have their pieces drawn on the page: the two town square puzzles, and the
  rocket shuttle (pile C, confirmed on p96).
- I checked the densest box, La-La Llama's, at full resolution; every element
  is distinguishable.

## What "What can I build?" shows now

1. **📕 From your manual (106 builds).** One line explains that 1 build has a
   verified piece list (BinBuild checks your bin and makes a booklet), and the
   other 105 are builds from the same book, meant for this kit, whose parts
   aren't verified yet: build them from the book.
2. **House and tree, highlighted:** "Manual · chapter 2 · Go Wild in the City ·
   page 28", "✓ Verified piece list", "✓ You can build this" (or what's
   missing), and **Make the booklet**.
3. **The other 105, by chapter,** each with its name, page(s), activity, and a
   chip: "Parts not verified yet", or "… · elements shown in the book" for the
   18, or "15 elements · …" where a total is printed. They have no button, no
   fit claim and no booklet.
4. **🤖 BrickGPT designs (10)**, as before: buildable first, the rest under
   "Not enough pieces yet".

`GET /api/builds/options` returns the same list with a `manual` summary (106 /
1 / 18 / 87), and `GET /api/manual` returns the catalog. Checked on the phone
layout (375 px) against the real inventory: 105 rows, 1 booklet button,
chapters in order, BrickGPT last.

**House and tree, corrected.** Page 28 pictures the set, and the earlier
booklet (my own arrangement, flagged as such in FULL-LOOP.md) didn't match it.
The booklet now follows the picture:
- the two orange bricks are stacked;
- the two curved slopes sit on top, tall ends together, overhanging both sides;
- the tree is on the second stud.

Same 7 pieces, same 5 steps; the steps and drawings are BinBuild's own.

## Draft piece lists for the 18 (added Oct 29)

Each diagram-readable build now has a **draft**: its elements box (or drawn
pieces) transcribed from the full-size photo, in
`backend/manual/drafts/<id>.json`.
- **Status:** every draft says `"status": "draft"` and carries a warning that
  it isn't a verified piece list.
- **Doubts:** each element line records what was read; lines that were hard to
  read are marked unsure, with the reason.
- **Catalog unchanged:** the 18 stay "diagram-readable". The app shows them as
  "Parts not verified yet · draft list waiting for a hand-check", with no fit
  claim.

**Consistency check.** Every element in every draft maps to a piece kind the
50-piece kit has, and no draft needs more of a kind than the kit holds.
That's evidence the reading is right, not proof.

| Build | Pages | Elements | Kinds | Unsure lines (why) |
|---|---|---|---|---|
| Dozy Dolphin | 10, 11 | 18 | 11 | 2× medium azure curved slope (side view); 1× medium blue cheese slope (small square from above) |
| Yoga Goose | 14, 15 | 16 | 10 | 2× medium azure curved slope (drawn side-on) |
| Viking longboat | 18, 19 | 14 | 9 | 1× medium blue cheese slope (side-on); 1× dark purple plate (looks blue-purple) |
| Tiny Tentacles | 22, 23 | 18 | 9 | none |
| Inspector Duck | 26, 27 | 17 | 10 | 2× dark purple plate (drawn blue-violet) |
| Mini City car | 30, 31 | 20 | 8 | none |
| Happy Ghost | 38, 39 | 12 | 9 | none |
| Town square puzzle | 40, 96 | 19 | 8 | 4× lime round plate, 1× lime 1x6 plate (drawn yellow) |
| Town square puzzle (Build Boost) | 41, 96 | 9 | 5 | 2× dark purple plate (each half hidden) |
| Hungry Elephant | 42, 43 | 20 | 10 | 2× lime round plate (drawn yellow); 2× grey 1x3 curved slope (drawn almost white) |
| La-La Llama | 46, 47 | 31 | 14 | 3× dark purple plate, 2× magenta plate, 1× medium azure 2x4 plate (drawn small or edge-on) |
| Bake-a-cake-ephant | 50, 51 | 15 | 9 | none |
| Hot-air Balloon | 54, 55 | 14 | 7 | 2× lime round plate (drawn yellow-green) |
| Playful Plane | 58, 59 | 14 | 9 | none |
| Space Rocket | 76, 77 | 18 | 11 | 2× medium blue cheese slope (seen from above) |
| Supergalactic Hero | 80, 81 | 21 | 13 | 2× lime clip plate, 2× lime tall side-stud brick (drawn yellow); 2× grey 1x3 curved slope (drawn almost white) |
| Puppy Power | 84, 85 | 15 | 10 | none |
| Rocket shuttle | 88, 89, 96 | 20 | 10 | none (pile C, from the answer on p96) |

**7 drafts have no unsure lines.** Most doubts are colour: the book draws
lime as yellow and light grey as near-white. The kit has only one colour of
each of those pieces, so the doubt is the drawing, not the piece.

**Hand-checking a draft:**
1. Open the printable checklist: `GET /api/manual/checklist` (on the Mac:
   http://localhost:8000/api/manual/checklist). It shows all 18, with unsure
   lines first and highlighted.
2. For a build, lay its pieces out from the kit next to its page, tick each
   line, and build the model once.
3. Record it:
   ```
   python -m backend.manual_check dozy-dolphin                       # the checklist in the terminal
   python -m backend.manual_check dozy-dolphin --sure "medium_azure 1x2 curved slope" --set "white 1x2 jumper plate=2"
   python -m backend.manual_check dozy-dolphin --done --by NAME --notes "built it"
   ```
   `--done` is refused while any line is still unsure. `--undo` puts it back
   to a draft. Commit the changed draft file to keep the check.
4. From then on, "What can I build?" counts the build as verified
   ("(hand-checked)") and checks the bin against it: "You have all 18 pieces.
   Build it from the book: pages 10, 11.", or what's missing.
   - **Still no booklet:** BinBuild has no steps for it, so it is built from
     the book.
   - **Turning one into a booklet** means writing its steps as a set file,
     like house-and-tree.

## What would verify the rest

- **The 18 diagram-readable builds:** transcribed (above). What's left is the
  hand-check, about 5–10 minutes per build with the kit.
  - Done: the build turns verified and gets a bin check.
  - Its steps as a set file would add a booklet.
- **The 87 with no list on the page:** build the model from the picture with
  the kit, take it apart, and scan that handful as a batch. Review and confirm
  give its exact piece list, which becomes its set file. The 4 printed totals
  are a check on the count.
- **Activities** (Chance Creatures, Mirror People and the like) have no fixed
  list by design. They stay unverified, which is right for them.
- **Pages 1–7 and 34–35** need photographing; any builds on them aren't in the
  catalog.

## Unchanged

Camera batch, photo gate, inventory review/confirm/undo, the full loop,
the review screen, and SAM opt-in (default still the stub). Live generation is
off; designs are pre-generated only. No model or Model API calls were made for
this spike. The photos, data, `.env` and database are not committed; the
catalog holds names and page numbers only.

## Tests

`tests/test_manual_catalog.py`, 10 tests:
- **Catalog:**
  - every build has a name, a chapter and a photographed page (8–96, not
    34–35);
  - the counts are 106 / 1 / 18 / 87;
  - only house-and-tree is verified, and its set has the 7 pieces page 28
    prints;
  - only the 5 printed totals appear;
  - no parts list anywhere.
- **What can I build?:**
  - all 106 are listed before BrickGPT, verified first, then book order;
  - unverified builds carry no fit claim, missing list, set or booklet;
  - the verified build is checked against the bin and named as short when
    pieces are missing.
- **Booklet:** follows page 28.
- **API:** the manual summary, the booklet for the verified build, and the
  catalog.

Drafts and hand-check, 9 more tests in the same file:
- **Drafts:** one per diagram-readable build, all unverified and saying so;
  totals, vocabulary, and within the kit; no fit claim while waiting.
- **Hand-check tool:** refuses `--done` while unsure lines remain; a
  hand-checked draft gets a fit check and a "short" with what's missing, but
  no booklet; `--set` and `--undo`; bad input. Runs on copies, so the repo's
  drafts are untouched.
- **API:** the checklist page and the summary counts (18 waiting, 0
  hand-checked).

Totals: 123 tests in `tests/` plus Path A's 31, all passing in the venv. With
the system `python3`, 57 are skipped and the rest pass.

## Next blocker for the Oct 30 – Nov 1 kid trials

The 18 draft piece lists need a person with the kit to hand-check them (about
5–10 minutes each; start with the 7 that have no unsure lines). Until then,
house and tree is still the only build the app can check a kid's bin for.
