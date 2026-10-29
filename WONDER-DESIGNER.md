# Wonder designer track

Branch `spike/wonder-designer`, built on `spike/sam-3-1` (aba3bbf). This is a
parallel track: the manual catalog, BrickGPT and the trials are unchanged,
and nothing in the app calls this. Muse Wonder (`muse-wonder-1.0`, Meta Model
API) designs a new model from the pieces actually in the bin, every kind of
them, and every proposal goes through a validator.

**Result: a Wonder design passed on the first attempt.** "Simple House":
- 20 pieces, all owned;
- 10 kinds, only 2 of them plain bricks (the kit's two orange 1x2s);
- connected by studs, nothing floating;
- one call, 88 s, $0.20.

It is in `backend/designs/wonder-simple-house.txt` and **has not been
hand-built yet**.

## How it works

```
owned inventory (binbuild.db, confirmed) ──▶ prompt: every usable piece, exact count, LDraw geometry
        ▶ Wonder (reasoning effort high) ──▶ design ──▶ validator ──ok──▶ parts list, placements, booklet
                     ▲                                     │ errors
                     └──── errors fed back, same conversation, max 5 attempts ──▶ else: named shortfall
```

| File | |
|---|---|
| `backend/wonder_design.py` | The design format, the piece table (from LDraw), the validator, booklet placements. Standard library only. |
| `backend/wonder_client.py` | Muse Wonder over the Responses API, in background mode (no connection held open while it reasons). A retry continues the same conversation with `previous_response_id`. Key from `META_MODEL_API_KEY` in `.env`: never printed, logged or in an error; a clear error without it. |
| `backend/wonder_designer.py` | The prompt, the retry loop, the CLI, the booklet. |
| `backend/designs/wonder-simple-house.txt` | The candidate design. |
| `tests/fixtures/wonder-house*-recorded.json` | Both live runs, so tests replay them with no calls. |
| `tests/test_wonder.py` | 21 tests (below). |

```bash
python -m backend.wonder_designer --target "a simple house"          # live: calls Wonder
python -m backend.wonder_designer --booklet backend/designs/wonder-simple-house.txt --turn   # just the booklet
```

### The format: BrickGPT's line, extended

```
SIZE (x,y,z) code colour [down=±x|±y | studs=±x|±y | clip=±x|±y]
2x1 (2,1,5) curved_slope black down=+x
```

- **Same line as BrickGPT:** `HxW (x,y,z)`, with H studs along x and W along
  y. The inventory key sorts the size, so `2x1` and `1x2` are the same piece.
- **What's added:**
  - a piece code and colour, because pieces are no longer only plain bricks;
  - a direction for pieces that need one (which way a slope runs down, which
    edge carries studs, which end a clip is on);
  - **z counts plates**, not bricks, because plates and tiles exist.
- **The booklet path is unchanged:** `booklet.py` takes the placements as
  before, with heights from LDraw.

### Geometry from LDraw

Every kit piece was matched to an LDraw part (`~/Downloads/ldraw`). Its .dat
file was expanded (subparts and primitives) to read the footprint, the height
and the positions of its upright top studs. `verify_against_ldraw()` re-reads
all of them, and a test runs it whenever the library is present: **no
differences**.

| Kit piece | LDraw | What LDraw settled |
|---|---|---|
| orange 1x2 brick | 3004 | 3 plates, 2 studs |
| blue 1x4 brick with studs on side | 30414 | 3 plates; side studs don't count as connections |
| grey 1x1 headlight brick | 4070 | 3 plates, 1 top stud |
| grey 1x1 round brick | 3062b | 3 plates, hollow stud |
| lime tall 1x1 brick, 2 side studs | 32952 | **5 plates** (1 2/3 bricks) |
| plates 1x2, 1x6, 2x2, 2x4 | 3023b, 3666, 3022, 3020 | 1 plate, a stud per cell |
| lime 1x1 round plate | 6141 | 1 plate, 1 stud |
| lime 1x2 plate with clip | 63868 | 1 plate; the clip reaches 0.7 stud past one end |
| white 1x2 jumper plate | 3794b | **one centred stud, off the grid**: nothing may go on it here |
| white 2x4 wedge plate | 41769a / 41770a | **4 studs along one long edge only** |
| black 1x2 curved slope | 11477 | 2 plates, no studs, rises along its length |
| azure 1x2 "curved slope" | **6091** | a different mould: 4 plates at the curve, which peaks next to a flat 3-plate step with **one stud** |
| grey 1x3 curved slope | 50950 | 3 plates, no studs |
| blue 1x1 cheese slope | 54200 | 2 plates, no studs |
| white 1x1 round tile | 98138 | 1 plate, no studs |
| white 2x2 "tile with studs on edge" | 33909 | **a plate with 2 studs on one edge** |
| black 1x4 "hinge plate" | **none found** | No LDraw part matches the book's drawing (studs in the middle, bars at the ends), so its studs aren't known. **It's left out**: 20 of the kit's 21 kinds (49 of 50 pieces) are usable. |

### The validator

`wonder_design.validate(text, owned)` checks:
- **Owned:** every line is a piece the user owns, with counts within the
  inventory. Too many of a kind is reported as a shortfall, like Path A
  ("orange 1x2 brick: uses 3, owns 2").
- **Format:** sizes and directions fit the piece.
- **Grid:** every piece on the stud grid, inside 20×20.
- **No overlaps:** each piece fills its footprint for its height (the 6091's
  two cells have different heights; a clip fills the next cell).
- **Held by studs:** a piece is joined to the one below only where its bottom
  sits on a top stud of that piece. One connected model, standing on the
  table at z=0.
  - Smooth tops (tiles, slopes, the smooth half of the edge-stud plate, the
    tapered half of a wedge) hold nothing.
  - Nothing may sit on a jumper plate.
  - Side studs, clips and bars are not counted.

On failure the errors go back to Wonder, numbered by line ("line 9: not held
by any stud to the rest of the model…"), up to 5 attempts. If none passes,
the result names the shortfall and the last errors, with no design.

## The two live runs

Reasoning effort `high`, target "a simple house", the confirmed kit
inventory.

| | Run 1 | Run 2 (the candidate) |
|---|---|---|
| Result | passed, attempt 1 | passed, attempt 1 |
| Design | "Small House with Pitched Roof", 19 pieces | "Simple House", 20 pieces |
| Time, cost | 144.9 s, $0.29 (1.2k in, 14.4k out, 14.0k of it reasoning) | 88.0 s, $0.20 (1.3k in, 9.9k out, 9.5k reasoning) |
| Prompt | older: no grey 1x3 slopes; misleading 6091 wording | fixed |

**Both runs passed on the first try, so the retry loop has not run live.** Its
feedback path is tested with written replies (a broken design, then the fix).

**Run 1's look was spoiled by my prompt.** It described the azure 6091's
`down=` as "the low (stud) end", but LDraw shows the curve peaking *next to*
the stud. Wonder's two azure back pieces therefore dip in the middle instead
of forming a peak. The model is still valid and connected; only the look is
off. Run 2's prompt describes the piece correctly. Run 1 also lacked the
grey 1x3 slopes, which I had left out of the piece table.

### The candidate: Simple House (`backend/designs/wonder-simple-house.txt`)

| Qty | Piece | LDraw |
|---|---|---|
| 2 | medium azure 2x4 plate | 3020 |
| 1 | blue 1x4 brick with 4 studs on side | 30414 |
| 2 | orange 1x2 brick | 3004 |
| 2 | light bluish gray 1x1 headlight brick | 4070 |
| 1 | white 1x2 jumper plate | 3794b |
| 4 | dark purple 1x2 plate | 3023b |
| 2 | magenta 2x2 plate | 3022 |
| 4 | black 1x2 curved slope | 11477 |
| 1 | light bluish gray 1x1 round brick | 3062b |
| 1 | white 1x1 round printed tile | 98138 |

```
2x4 (0,0,0) plate medium_azure          # base, two plates side by side
2x4 (2,0,0) plate medium_azure
4x1 (0,3,1) side_stud_brick blue        # back wall, ties the two base plates together
1x2 (0,1,1) brick orange                # side walls
1x2 (3,1,1) brick orange
1x1 (0,0,1) headlight_brick light_bluish_gray   # front corners
1x1 (3,0,1) headlight_brick light_bluish_gray
2x1 (1,0,1) jumper_plate white          # doorstep; ties the base plates at the front
2x2 (0,2,4) plate magenta               # ceiling
2x2 (2,2,4) plate magenta
2x1 (0,0,4) plate dark_purple           # over the door (lintel) and the front rooms
2x1 (2,0,4) plate dark_purple
2x1 (0,1,4) plate dark_purple
2x1 (2,1,4) plate dark_purple
2x1 (0,1,5) curved_slope black down=-x  # roof, ridge in the middle
2x1 (0,2,5) curved_slope black down=-x
2x1 (2,1,5) curved_slope black down=+x
2x1 (2,2,5) curved_slope black down=+x
1x1 (3,3,5) round_brick light_bluish_gray       # chimney
1x1 (3,3,8) round_tile white                    # chimney cap
```

(The comments are mine; Wonder gave the lines only.) It's a 4×4-stud house,
one brick tall, with a doorway at the front, a ridged roof and a chimney: 5
booklet steps.

**What to check in the hand-build:**
1. **After step 2,** the two base plates are held together only by the jumper
   plate (front) and the blue brick (back). Check the base lifts as one piece.
2. **The two purple plates over the doorway** each sit on one headlight
   stud, with the other end over the door. Check they don't swivel.
3. **The jumper plate:** its one centred stud has nothing on it; the
   booklet draws two studs (a drawing limit).
4. **Overall:** check it stands, and that a child sees a house.

## One line each

- **Model API cost/time:** 2 Wonder calls in total, $0.49 and 233 s (2.4k
  input + 24.2k output tokens, almost all reasoning); the candidate took one
  call: 88 s, $0.20.
- **What Wonder got right:**
  - only owned pieces, within the exact counts;
  - connected and on the grid on the first try, both times;
  - used the non-brick pieces sensibly: jumper plate as doorstep, headlight
    bricks as corners, a side-stud brick as the back wall, a round tile as
    the chimney cap;
  - a real doorway with a lintel, a ridged roof;
  - left out the pieces it can't stack on.
- **What the validator caught:**
  - **live:** nothing, since both designs were valid;
  - **in tests:** floating pieces, pieces resting on smooth tops, overlaps
    (including inside the 6091's curve and a clip's overhang), over-counts as
    named shortfalls, unowned pieces, off-grid pieces, wrong directions,
    things on a jumper plate, and models off the table;
  - **what it can't see:** how something looks (run 1's back pieces) and how
    firm a one-stud bridge is.
- **Next blocker:** a person has to hand-build Simple House from the kit with
  its booklet, by the Oct 31 evening kill trigger. Nothing else blocks the
  decision.

## Limits

- **Vertical connections only.** Side studs, clips and bars aren't modelled,
  so designs that need them are rejected or never offered.
- **Overlaps are conservative.** Slopes fill their whole box, and wedge plates
  their whole 2×4 rectangle, so a few legal builds are refused.
- **Wedge plates aren't told apart.** The kit has one left and one right, and
  the inventory doesn't distinguish them.
- **The booklet's drawings are approximate** for modified pieces (jumper plate,
  edge-stud plate, wedge plate, 6091). Its pictures look from one corner;
  `--turn` shows the other side.
- **One target, one bin, two runs:** a promising start, not a hit rate.

## Tests

`tests/test_wonder.py`, 21 tests:
- **Geometry:**
  - the parts agree with LDraw (when the library is there);
  - 20 usable kinds and 49 pieces, with no hinge plate;
  - heights match LDraw.
- **Validator:**
  - the page-28 house passes;
  - each failure above gives its message, with shortfalls named;
  - the 6091's stud, wedge plates, the edge-stud plate and the clip overhang
    behave as LDraw says.
- **Loop:**
  - errors go back in the same conversation, and a fix passes;
  - five failures name the shortfall;
  - a reply without a fence still parses;
  - the prompt lists only owned pieces;
  - both recorded live runs replay to their designs;
  - the candidate file passes, with only 2 plain bricks among its 20 pieces.
- **Client:**
  - the documented request (model, reasoning effort, background,
    `previous_response_id`), with polling until done;
  - a clear error without a key, and the key never in an error.
- **Booklet:** one step per layer, heights from LDraw.

Totals: 125 tests in `tests/` plus Path A's 31, all passing in the venv. With
the system `python3`, 56 are skipped and the rest pass.
