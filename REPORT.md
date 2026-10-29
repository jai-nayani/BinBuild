# Spike report: BrickGPT inventory constraint, Path A (generate → filter → patch)

Branch `spike/constraint-path-a`. Module `backend/brickgpt_constraint.py`, tests
`backend/test_brickgpt_constraint.py`, inputs in `spike-constraint-kit/` (copied
unchanged from the kit).

```bash
python3 -m unittest backend.test_brickgpt_constraint -v   # 31 tests, ~0.25 s, stdlib only
python3 -m backend.brickgpt_constraint                     # prints the matrix and sampling tables below (~10 s)
```

## Verdict

**Path A produces a buildable, connected design from two of the three test
inventories, so the 6:00 PM Oct 28 kill trigger is not hit.**

| Test case | Expected | Result |
|---|---|---|
| chair × fits | fits as-is | **fit**, 0 attempts, 0.5 ms |
| chair × near-miss | patch saves it | **patched**, 5 attempts (1 rejected), 7.4 ms, connected, same footprint per layer, 86 → 101 bricks |
| chair × short | explicit failure, shortfall named | **failed**: short 1x1:20 1x2:20 1x6:1 1x8:4 2x2:4 2x4:3 2x6:7 |

Across all 30 inventory × design runs:

| Inventory | fit | patched | failed |
|---|---|---|---|
| fits (86) | chair | train | 8: 6 not patchable (too few spare studs), bottle + tower not connected |
| near-miss (119) | — | chair, train | 8: bench hit the cap 1× 2x6 short of fitting, 5 not patchable, bottle + tower not connected |
| short (27) | — | — | 10, each with its shortfall named |

The test inventories are all built around the chair, so the other designs
failing is expected. It is not evidence against Path A. What it does show:
patching only rescues designs that are already close to the bin's
composition.

## How it works

- **Coordinates:** `HxW (x,y,z)` is H studs along x and W along y, with
  (x,y,z) the minimum corner. I checked this reading on the data: there are 0
  overlaps and 0 out-of-grid bricks in all 10 designs. The swapped reading
  overlaps in every design.
- **Counting:** each brick's size is sorted ascending (`6x2` → `2x6`).
  Inventory keys are canonicalized the same way.
- **Fit:** used ≤ owned for every type.
- **Connected:** all bricks form one group joined by stud contacts, meaning
  overlapping footprints on adjacent layers. Two bricks side by side on the
  same layer are not joined. This is a connectivity result, **not** a
  physical-stability claim.
- **Patch:**
  - Pick a brick of a short type and replace it with a tiling of its exact
    footprint, on the same layer, using only spare owned pieces.
  - Tilings are tried in order of fewest pieces, then most stud contacts.
  - Counts and connectivity are re-checked after every swap. A swap that
    disconnects the build is rejected and the next candidate is tried.
  - Cap: 20 attempts per design. An attempt is one swap applied and
    re-checked.
  - Tilings that leave a piece touching nothing above or below are skipped
    without counting as attempts, because they can never be connected.
- **Up-front checks, before any attempt:**
  - Do the short bricks cover more studs than all the spare pieces? Then no
    patch can work.
  - Is a short type something no spare piece can tile (e.g. a 1x1)? Then no
    patch can work.
- **Failure rule:** `Failure` has no `design` field. Its fields are the reason,
  the shortfall in the generated design, what was still short when patching
  stopped, and the attempt log. The half-patched design is discarded. A
  design that fits on counts but is not connected also fails.

## Near-miss chair: what the patcher did

```
attempt 1: 6x1 (1,11,9)   -> 2x1 + 2x1 + 2x1: ok
attempt 2: 6x2 (0,18,16)  -> 2x2 + 2x2 + 2x1 + 2x1: ok          (uses the 2 spare 2x2s)
attempt 3: 6x2 (1,17,13)  -> 6 × 2x1: ok
attempt 4: 2x6 (8,12,12)  -> 6 × 2x1: disconnects the build    (crosswise pieces break the seat bridge)
attempt 5: 2x6 (8,12,12)  -> 4 × 2x1 + 2 × 1x2: ok             (lengthwise 1x2s keep the bridge)
```

- **Counts before:** 1x1:30 1x2:30 1x6:1 1x8:5 2x2:6 2x4:5 2x6:9
- **Counts after:** 1x1:30 **1x2:47** 1x8:5 **2x2:8** 2x4:5 **2x6:6**
- This used 17 of the 25 spare 1x2s rather than the expected 21, because the
  bin's 2 spare 2x2s covered part of one 2x6.

## Full matrix

Single run on an Apple M2 with Python 3.14.6. The "ms" column covers generate
(file load and parse), filter, connectivity and patch together.

#### test-inventory-fits.json (86 bricks: 1x1:30 1x2:30 1x6:1 1x8:5 2x2:6 2x4:5 2x6:9)

| design | bricks | result | attempts | ms | counts before | counts after / shortfall |
|---|---|---|---|---|---|---|
| bed | 65 | FAILED: not patchable: short bricks cover 272 studs but spare pieces only 103 | 0 | 0.9 | 1x1:9 1x2:5 1x4:6 1x6:5 1x8:9 2x2:4 2x4:2 2x6:25 | short 1x4:6 1x6:4 1x8:4 2x6:16 |
| bench | 58 | FAILED: not patchable: short bricks cover 72 studs but spare pieces only 62 | 0 | 0.7 | 1x1:10 1x2:14 1x4:5 1x8:7 2x2:5 2x4:5 2x6:12 | short 1x4:5 1x8:2 2x6:3 |
| bottle | 160 | FAILED: not connected: 2 separate parts (159+1 bricks) | 0 | 0.9 | 1x1:46 1x2:92 1x4:5 1x6:1 2x2:11 2x4:3 2x6:2 | short 1x1:16 1x2:62 1x4:5 2x2:5 |
| bus | 74 | FAILED: not patchable: short bricks cover 366 studs but spare pieces only 106 | 0 | 0.9 | 1x1:10 1x2:3 1x4:8 1x6:10 1x8:7 2x2:2 2x4:3 2x6:31 | short 1x4:8 1x6:9 1x8:2 2x6:22 |
| car | 115 | FAILED: not patchable: short bricks cover 274 studs but spare pieces only 35 | 0 | 1.2 | 1x1:27 1x2:32 1x4:3 1x6:8 1x8:2 2x2:15 2x4:4 2x6:24 | short 1x2:2 1x4:3 1x6:7 2x2:9 2x6:15 |
| chair | 86 | fit | 0 | 0.5 | 1x1:30 1x2:30 1x6:1 1x8:5 2x2:6 2x4:5 2x6:9 | 1x1:30 1x2:30 1x6:1 1x8:5 2x2:6 2x4:5 2x6:9 |
| sofa | 88 | FAILED: not patchable: short bricks cover 440 studs but spare pieces only 70 | 0 | 1.0 | 1x1:8 1x2:12 1x4:3 1x6:5 1x8:17 2x2:3 2x4:6 2x6:34 | short 1x4:3 1x6:4 1x8:12 2x4:1 2x6:25 |
| table | 89 | FAILED: not patchable: short bricks cover 334 studs but spare pieces only 68 | 0 | 0.9 | 1x1:12 1x2:17 1x4:1 1x6:4 1x8:14 2x2:12 2x4:2 2x6:27 | short 1x4:1 1x6:3 1x8:9 2x2:6 2x6:18 |
| tower | 68 | FAILED: not connected: 2 separate parts (63+5 bricks) | 0 | 0.4 | 1x1:14 1x2:38 2x2:15 2x6:1 | short 1x2:8 2x2:9 |
| train | 37 | patched | 4 | 2.7 | 1x1:11 1x2:10 1x6:5 1x8:1 2x2:1 2x4:3 2x6:6 | 1x1:11 1x2:22 1x6:1 1x8:1 2x2:1 2x4:3 2x6:6 |

#### test-inventory-near-miss.json (119 bricks: 1x1:40 1x2:55 1x8:5 2x2:8 2x4:5 2x6:6)

| design | bricks | result | attempts | ms | counts before | counts after / shortfall |
|---|---|---|---|---|---|---|
| bed | 65 | FAILED: not patchable: short bricks cover 314 studs but spare pieces only 171 | 0 | 0.7 | 1x1:9 1x2:5 1x4:6 1x6:5 1x8:9 2x2:4 2x4:2 2x6:25 | short 1x4:6 1x6:5 1x8:4 2x6:19 |
| bench | 58 | FAILED: patch failed: hit the 20-attempt cap | 20 | 30.8 | 1x1:10 1x2:14 1x4:5 1x8:7 2x2:5 2x4:5 2x6:12 | short 1x4:5 1x8:2 2x6:6; still short 2x6:1 after patching |
| bottle | 160 | FAILED: not connected: 2 separate parts (159+1 bricks) | 0 | 0.8 | 1x1:46 1x2:92 1x4:5 1x6:1 2x2:11 2x4:3 2x6:2 | short 1x1:6 1x2:37 1x4:5 1x6:1 2x2:3 |
| bus | 74 | FAILED: not patchable: short bricks cover 408 studs but spare pieces only 174 | 0 | 0.8 | 1x1:10 1x2:3 1x4:8 1x6:10 1x8:7 2x2:2 2x4:3 2x6:31 | short 1x4:8 1x6:10 1x8:2 2x6:25 |
| car | 115 | FAILED: not patchable: short bricks cover 304 studs but spare pieces only 91 | 0 | 1.0 | 1x1:27 1x2:32 1x4:3 1x6:8 1x8:2 2x2:15 2x4:4 2x6:24 | short 1x4:3 1x6:8 2x2:7 2x6:18 |
| chair | 86 | patched | 5 | 7.4 | 1x1:30 1x2:30 1x6:1 1x8:5 2x2:6 2x4:5 2x6:9 | 1x1:30 1x2:47 1x8:5 2x2:8 2x4:5 2x6:6 |
| sofa | 88 | FAILED: not patchable: short bricks cover 482 studs but spare pieces only 138 | 0 | 0.9 | 1x1:8 1x2:12 1x4:3 1x6:5 1x8:17 2x2:3 2x4:6 2x6:34 | short 1x4:3 1x6:5 1x8:12 2x4:1 2x6:28 |
| table | 89 | FAILED: not patchable: short bricks cover 368 studs but spare pieces only 128 | 0 | 0.9 | 1x1:12 1x2:17 1x4:1 1x6:4 1x8:14 2x2:12 2x4:2 2x6:27 | short 1x4:1 1x6:4 1x8:9 2x2:4 2x6:21 |
| tower | 68 | FAILED: not connected: 2 separate parts (63+5 bricks) | 0 | 0.4 | 1x1:14 1x2:38 2x2:15 2x6:1 | short 2x2:7 |
| train | 37 | patched | 5 | 3.1 | 1x1:11 1x2:10 1x6:5 1x8:1 2x2:1 2x4:3 2x6:6 | 1x1:11 1x2:25 1x8:1 2x2:1 2x4:3 2x6:6 |

#### test-inventory-short.json (27 bricks: 1x1:10 1x2:10 1x8:1 2x2:2 2x4:2 2x6:2)

| design | bricks | result | attempts | ms | counts before | counts after / shortfall |
|---|---|---|---|---|---|---|
| bed | 65 | FAILED: not patchable: short bricks cover 402 studs but spare pieces only 11 | 0 | 0.7 | 1x1:9 1x2:5 1x4:6 1x6:5 1x8:9 2x2:4 2x4:2 2x6:25 | short 1x4:6 1x6:5 1x8:8 2x2:2 2x6:23 |
| bench | 58 | FAILED: not patchable: short bricks cover 232 studs but spare pieces only 0 | 0 | 0.6 | 1x1:10 1x2:14 1x4:5 1x8:7 2x2:5 2x4:5 2x6:12 | short 1x2:4 1x4:5 1x8:6 2x2:3 2x4:3 2x6:10 |
| bottle | 160 | FAILED: not connected: 2 separate parts (159+1 bricks) | 0 | 0.8 | 1x1:46 1x2:92 1x4:5 1x6:1 2x2:11 2x4:3 2x6:2 | short 1x1:36 1x2:82 1x4:5 1x6:1 2x2:9 2x4:1 |
| bus | 74 | FAILED: not patchable: short bricks cover 496 studs but spare pieces only 14 | 0 | 0.8 | 1x1:10 1x2:3 1x4:8 1x6:10 1x8:7 2x2:2 2x4:3 2x6:31 | short 1x4:8 1x6:10 1x8:6 2x4:1 2x6:29 |
| car | 115 | FAILED: not patchable: short bricks cover 461 studs but spare pieces only 0 | 0 | 1.0 | 1x1:27 1x2:32 1x4:3 1x6:8 1x8:2 2x2:15 2x4:4 2x6:24 | short 1x1:17 1x2:22 1x4:3 1x6:8 1x8:1 2x2:13 2x4:2 2x6:22 |
| chair | 86 | FAILED: not patchable: short bricks cover 222 studs but spare pieces only 0 | 0 | 0.7 | 1x1:30 1x2:30 1x6:1 1x8:5 2x2:6 2x4:5 2x6:9 | short 1x1:20 1x2:20 1x6:1 1x8:4 2x2:4 2x4:3 2x6:7 |
| sofa | 88 | FAILED: not patchable: short bricks cover 594 studs but spare pieces only 2 | 0 | 0.9 | 1x1:8 1x2:12 1x4:3 1x6:5 1x8:17 2x2:3 2x4:6 2x6:34 | short 1x2:2 1x4:3 1x6:5 1x8:16 2x2:1 2x4:4 2x6:32 |
| table | 89 | FAILED: not patchable: short bricks cover 488 studs but spare pieces only 0 | 0 | 0.9 | 1x1:12 1x2:17 1x4:1 1x6:4 1x8:14 2x2:12 2x4:2 2x6:27 | short 1x1:2 1x2:7 1x4:1 1x6:4 1x8:13 2x2:10 2x6:25 |
| tower | 68 | FAILED: not connected: 2 separate parts (63+5 bricks) | 0 | 0.3 | 1x1:14 1x2:38 2x2:15 2x6:1 | short 1x1:4 1x2:28 2x2:13 |
| train | 37 | FAILED: not patchable: short bricks cover 87 studs but spare pieces only 4 | 0 | 0.3 | 1x1:11 1x2:10 1x6:5 1x8:1 2x2:1 2x4:3 2x6:6 | short 1x1:1 1x6:5 2x4:1 2x6:4 |

## Sampling: N designs per `plan_build`

**How it works:**
- `plan_build(category, inventory, samples=6)` draws up to N designs from
  `generate()`. N defaults to 6 and must be 4–8, or it raises `ValueError`.
- It returns the first design that fits or patches. Later samples are never
  generated.
- If all N fail, it returns the `Failure` with the fewest short studs in its
  generated design, with that sample's own attempt log. Ties go to fewest
  still short after patching, then to the earlier sample.
- The `Failure` shape is unchanged.
- A repeated design still counts as a draw, but its result is reused rather
  than patched again.

**With the stub, sampling one category changes nothing.**
- The stub has one design per category, so all N draws of a category are the
  same design.
- I re-ran the 30 inventory × category cells through `plan_build` with N=6:
  all 30 give the same outcome as the single-shot matrix above.

**A proxy for N different live samples.** `sampling_report()` shuffles the 10
kit designs and hands them out in that order, ignoring the category. That
measures "build anything from this bin", not N samples of one category. Each
row below is 100 seeded shuffles of real `plan_build` calls. The "exact" rate
is 1 − C(10−k, N) / C(10, N), where k is the number of kit designs that fit or
patch for that bin: k = 2 (chair, train) for fits and near-miss, 0 for short.

| inventory | N=4 | N=5 | N=6 | N=7 | N=8 | mean draws at N=6 | mean ms at N=6 |
|---|---|---|---|---|---|---|---|
| fits | 69% (exact 66.7%) | 76% (77.8%) | 88% (86.7%) | 95% (93.3%) | 96% (97.8%) | 3.13 | 2.7 |
| near-miss | 69% (66.7%) | 76% (77.8%) | 88% (86.7%) | 95% (93.3%) | 96% (97.8%) | 3.13 | 13.7 |
| short | 0% | 0% | 0% | 0% | 0% | 6.00 (always N) | 2.7 |

- The measured rates track the exact ones within sampling noise.
- "mean ms" is the constraint layer only, with designs pre-parsed. Generation
  is stubbed, so it isn't timed.
- Live samples are independent draws rather than a shuffle without
  replacement. At the same 2-in-10 hit rate, 1 − 0.8^N gives 59.0%, 67.2%,
  73.8%, 79.0% and 83.2% for N = 4 to 8.

**Which failure gets returned.** Under the fits and near-miss bins, the
"closest" failure is usually the **tower** whenever it is drawn: only 52 and
28 short studs. But the tower fails because it is *not connected*, which
buying bricks can't fix. Under the short bin, the closest is the train (87
studs), else the tower (112). This follows the rule as specified. If the UI
will show the shortfall as "you're short X", consider ranking disconnected
failures after count failures.

**Recommended N: keep 6 as the default.**
- The constraint layer averages under 17 ms per `plan_build` here, and the
  slowest single sample is bench's 31 ms patch. So the real cost is N × live
  generation time. A bin that can't build anything always pays
  for all N.
- Going from 4 to 6 adds about 15–20 points of hit rate under both estimates.
  Going from 6 to 8 adds about 10, for a third more worst-case latency.
- Revisit once live generation time per design is measured. If it is a few
  seconds or less, use 8. If it is slow, add an up-front "this bin can't build
  anything" check rather than lowering N.
- These rates come from chair-centred test bins and a cross-category pool.
  They show the shape of the curve, not the live per-category hit rate.
- The bigger lever is the per-sample hit rate, not N. Prompting BrickGPT
  towards designs that suit the bin, or Path B, would raise it.

## Why designs fail, and the patcher's limits

1. **Not enough spare studs (most failures).** The generated designs use far
   more of the big bricks than these bins hold. The bed, bus, sofa and table
   use 25–34 2x6s each; the bins have 6–9. Splitting can't create studs that
   aren't there.
2. **Bridges.** Splitting a brick that is the only thing joining two parts of
   the build disconnects it, whatever the tiling. Bench (near-miss) re-tiled
   13 of the 14 bricks it needed, then every candidate for the last 2x6
   disconnected the build. Raising the cap does not help: at 30, 40 or 60 it
   stops after 23 attempts with "every candidate swap disconnects the build".
3. **Greedy order.** Early swaps can spend scarce pieces. Bench used up its
   spare 1x2s on 1x4s and 1x8s first and had to fall back on 1x1s.
4. **Split only.** The patcher never merges bricks or moves them between
   layers. So a short 1x1 can never be patched, and a short 1x2 only with
   two 1x1s.
5. **More pieces.** Each patch adds steps to the build: the near-miss chair
   goes from 86 to 101 bricks.

## Data findings (reported, not adjusted)

- **bottle** has a lone 1x1 at (5,14,0) touching nothing. **tower** has a
  separate 5-brick stack at x=1, y=16–18 beside the main tower.
  - Both stand on the ground, but neither is joined to the rest, so both fail
    "connected" under every inventory.
  - A looser "every brick reaches the ground" rule would pass them. I kept the
    brief's rule: connected to the rest of the structure.
- **The near-miss inventory has 8× 2x2**, where the fits inventory has 6. The
  inventory's description doesn't mention this; it's harmless spare.
- **The brief's tiling example doesn't add up:** "2x6 = 2x4 + 1x2" is 10
  studs, not 12. The valid tilings are 2x4 + 2x2 or 2x4 + two 1x2s, and the
  module uses those.
- **Everything else matches the stated counts:**
  - all 10 designs have the stated brick counts;
  - the fits inventory equals the chair's canonical counts exactly;
  - the short inventory totals 27.

## What changes when live BrickGPT plugs into `generate()`

- **The seam:** `generate(category) -> Design` stays the same, and
  `plan_build(category, inventory, generate=...)` already accepts a different
  generator.
- **What the live hook needs:**
  - BrickGPT's fine-tuned Llama 3.2 1B weights, plus torch and transformers,
    on a GPU or behind a hosted endpoint.
  - A text prompt per category. BrickGPT is prompted with text, not a
    category id.
  - A seed or temperature, so repeated calls give different designs.
  - BrickGPT's text output fed through `parse_design`. The format is
    identical, and anything outside the 8 types, off the grid or overlapping
    raises, which should count as a failed sample.
  - A decision on BrickGPT's physics-based rollback, which needs a Gurobi
    stability solver: it must be disabled or replaced without a Gurobi
    licence. Our connectivity check remains the final gate either way.
- **The sampling loop is in place** (see "Sampling" above):
  - `plan_build` draws up to N designs and returns the first that fits or
    patches, else the smallest-shortfall `Failure`.
  - Live, each `generate()` call must return a *new* sample, e.g. a fresh seed
    per call.
  - That puts generation time × N on the request path. The filter is under
    1 ms and patching at most ~31 ms, so generation dominates.
  - Hopeless designs are rejected by the up-front checks before any patching.
  - A sample that `parse_design` rejects currently raises out of
    `plan_build`. Live, it should count as one failed draw.
- **The Path B signal:** if, on real scanned bins, N free samples rarely land
  close enough for the patcher, that is the evidence for the in-loop
  constraint (Path B).
