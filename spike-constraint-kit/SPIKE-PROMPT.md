# SPIKE: BrickGPT inventory-constrained generation — Path A (generate → filter → patch)

Paste this whole prompt to Claude Code. It is self-contained: everything the spike needs is in this folder.

## Project

BinBuild — Meta Global AI Developer Hackathon, indie track. Submission due **Wed Nov 4, 9:00 PM ET**. Repo: `jai-nayani/BinBuild` (public). Before you touch anything: `git pull` — the scaffold is on main (commit `791b0a1`, FastAPI skeleton + PWA shell). Work on a branch called `spike/constraint-path-a` and push it when done.

The app scans a bin of loose LEGO, inventories the pieces, and generates a NEW build guide using only the pieces owned. Generation is BrickGPT (Llama 3.2 1B, fine-tuned): it outputs a design brick by brick on a 20×20×20 grid. Your job is the constraint layer that makes generation respect the inventory.

## The one decision already made

Path A: **generate → filter → patch**. Generate a design freely, keep it if it fits the bin, patch it if it is a near-miss. Do NOT build the in-loop constraint (checking stock inside the generation loop) — that is the fallback if path A fails.

## Brick universe (fixed, do not expand)

Exactly 8 brick types, all 1 unit tall: `1x1, 1x2, 1x4, 1x6, 1x8, 2x2, 2x4, 2x6`.

- Orientation is encoded in the size string: `1x2` and `2x1` are the SAME brick rotated. The canonical inventory key is the dimensions sorted ascending (`1x2`).
- Constraint semantics: **used ≤ owned per type. Leftovers are fine.** A design does NOT have to use every piece.
- Colors are out of scope for this spike (they get assigned from the inventory after generation).

## What to build

A new module, `backend/brickgpt_constraint.py` (plus tests), that implements:

1. **Parse** a BrickGPT design. Format (see `designs/`): one brick per line, `SIZE (x,y,z)`, e.g. `1x2 (9,18,0)`. 10 pre-generated designs are provided: bed (65 bricks), bench (58), bottle (160), bus (74), car (115), chair (86), sofa (88), table (89), tower (68), train (37). Categories BrickGPT knows (21): basket, bed, bench, birdhouse, bookshelf, bottle, bowl, bus, camera, car, chair, guitar, jar, mug, piano, pot, sofa, table, tower, train, vessel.
2. **Filter**: count bricks per canonical type; a design fits if used ≤ owned for every type.
3. **Patch** near-misses: when a design is short on some type, substitute with owned pieces covering the same footprint at the same height. Legal swaps are footprint tilings, e.g. one `2x6` footprint can be tiled by six `1x2`s, or by `2x4 + 1x2`; one `1x6` by three `1x2`s. Only use pieces the inventory actually has. Re-check counts after every swap. Bound the attempts (a small fixed retry cap, e.g. 20 patch attempts per design, then stop).
4. **Generate step (stubbed for this spike)**: do NOT live-generate and do NOT download any model. Use the provided `designs/` files as the generate step's output. But define a clean seam for it: a function like `generate(category) -> design` that currently loads the matching file from `designs/`, so live BrickGPT can plug in later. Note in your report what the live hook needs.

## The failure rule (critical, do not get this wrong)

If no design fits and patching fails within the attempt cap, return an **explicit failure** naming the shortfall (which types, how many short). NEVER return the last rejected or unstable design with only a warning. A failed generation is a failed generation.

## Stability

No Gurobi on this machine. Do a **connectivity check** instead: every brick must be connected (directly or via other bricks) to the rest of the structure — no floating bricks. Report the result as "connected", NEVER as "physically stable" — that claim needs a hand-built test.

## Test cases (run all of them)

Three inventories are provided. Run the filter + patcher over **all 10 designs** for each inventory:

- `test-inventory-fits.json` — exactly the chair's 86 bricks (30× 1x1, 30× 1x2, 1× 1x6, 5× 1x8, 6× 2x2, 5× 2x4, 9× 2x6). Expected: the chair fits as-is.
- `test-inventory-near-miss.json` — same idea but short 3× 2x6 and the 1× 1x6, with spare small bricks (55× 1x2, 40× 1x1). Expected: a patcher that tiles footprints with 1x2s can save the chair (3 missing 2x6 = 18× 1x2, 1 missing 1x6 = 3× 1x2; 25 spare 1x2s cover it). If your patcher can't find that, say so honestly and report what it tried.
- `test-inventory-short.json` — only 27 bricks total. Expected: explicit failure for the chair (and most designs), with the shortfall named.

## Deliverables

1. `backend/brickgpt_constraint.py` — the module (parse, canonical counting, filter, patch, connectivity check, explicit failure).
2. Tests — runnable in one command (`pytest` or a plain script), covering: fits case, near-miss patch case, short failure case, orientation canonicalization (`2x1` counts as `1x2`), and the never-return-a-rejected-design rule.
3. `REPORT.md` (short) — per test case: fit / patched / failed, brick counts before and after patching, timings, and one paragraph on what changes when live BrickGPT generation plugs into `generate()`.

## Deadline and kill trigger

This spike must be runnable and reported by **tomorrow (Wed Oct 28) afternoon**. There is a hard kill trigger at **6:00 PM ET Oct 28**: if path A cannot produce a buildable design from a test inventory by then, we abandon it and fall back to a pre-generated catalog. So be honest in the report — a clean "path A fails because X" is a useful result; a fudged pass is not.

## Guardrails

- Original work only: write the constraint module from scratch. Do not paste code from any other repo. BrickGPT itself is a dependency, not code to copy.
- Do not touch the PWA (`app/`) or the inventory database code. This spike is the constraint module only.
- Keep it small and readable. No new dependencies.
