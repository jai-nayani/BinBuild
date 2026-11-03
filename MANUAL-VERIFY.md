# Manual verification: Wonder checks its own drafts (Nov 1)

On `spike/integration`. Every draft piece list got an independent second
Muse Wonder read: 82 drafts read by Wonder from the pictured model, and 18
transcribed from the book's "Elements you'll need" box. Where the two reads
agree, the draft is verified. A verified draft gets its steps worked out
automatically, but only when they pass two checks: BinBuild's validator, and
a separate comparison with the book's picture.

No hand-check was replaced. A person with the kit can still verify any build,
a hand-check overrides the reads, and hand-checked drafts are never touched.

**Result:**
- **40 of 100 drafts are verified** by two reads that agree on every line.
- **11 of those 40 have a step-by-step booklet.**
- **The other 60 stay unverified** in the hand-check queue. Each card starts
  with the lines where its two reads differ.
- **Wonder spend: $35.77.**

**Update, Nov 2:** two agreed lists were contradicted by their own page's
picture (blueberry cake, birthday cake): both reads missed pieces the
picture shows. Each now carries a `picture_check` that disagrees, which
unverifies it like a disagreeing second read: 38 verified, 9 booklets (with
house and tree), 62 in the queue. Details: [BOOKLET-REDESIGN.md](BOOKLET-REDESIGN.md).

## How it works

```
draft ──▶ second read (new Wonder conversation, same page photo(s), same
          owned-pieces constraint, same checker as the first read, no sight
          of the first list)
            ├─ agrees on every line (kind + count) ─▶ verified:
            │    "What can I build?" bin-checks it like house and tree
            └─ differs on any line, or gives no list ─▶ stays a draft;
                 the differences head its hand-check card
verified ──▶ steps: Wonder writes the pictured model in the validated design
             format, using exactly the verified list
               ├─ the validator passes (on the stud grid, every piece held by
               │   studs, nothing floating, no overlaps, within the kit,
               │   exactly the list) AND a separate Wonder conversation judges
               │   the drawn model the same as the book's picture
               │      ─▶ steps recorded; the booklet comes through the
               │         house-and-tree path
               └─ otherwise, after at most 5 retries ─▶ verified without a
                    booklet, with the reason named on the build's card
```

**The second read is independent of the first:**
- it uses the first read's prompt and checker (`manual_transcribe`);
- it starts a new conversation;
- it never sees the first list.

For the 18 diagram builds, it is also told that the page prints an
"Elements you'll need" box. A test pins this.

**When the steps stop early:**
- **"Cannot":** Wonder may answer `Cannot: <why>` when the pictured model is
  held by clips, bars or side studs, or shows a piece on its side.
- **The hinge plate:** a list containing the black 1x4 hinge plate gets no
  call at all. The validator has no geometry for it (no LDraw match), so its
  steps couldn't be checked.

## Pilot: 2 of 3 agree

Three builds, one from each group:
- a printed-total Wonder draft: Submarine;
- a diagram draft: Mini City car;
- a typical Wonder draft with unsure lines: Super Sprinter.

The rule set beforehand was to go on only if at least 2 of the 3 agreed on
every line.

| Build | Reads | Lines agreeing | Steps |
|---|---|---|---|
| Submarine | agree | 12 of 12 | none: the periscope's round brick is on its side, on a side stud ("Cannot") |
| Super Sprinter | agree | 6 of 6 | passed the validator on try 3, but wasn't the book's model (below) |
| Mini City car | **differ** | 7 of 9 | none (not verified) |

Mini City car's hand list has a white 1x2 jumper plate where the second read
sees a white 2x2 tile with 2 studs on its edge. These two look alike in the
book's drawings, and the same swap shows up again for Tiny Tentacles. A
person has to settle it, and that is what the queue is for.

Pilot cost: $1.45 for 7 calls.

## The Super Sprinter lesson: the validator can't tell what the book shows

Super Sprinter is the pilot's first booklet.
- **Try 1:** the legs were under the body, as on the page, but they didn't
  connect.
- **Try 2:** nothing stood on the table.
- **Try 3:** Wonder moved the legs and feet **on top of the body**. That
  passes every stud rule, but it isn't the model on page 20.

The validator checks physics, not likeness, so it let try 3 through.

**What changed:** a design that passes the validator is now drawn as its
booklet would draw it, from two opposite corners. A separate Wonder
conversation then compares the drawings with the page photo. It only sees
the drawings, not the design text.
- "Not the same" counts as a failed validation. The differences go back to
  the placing conversation and use one of the 5 retries.
- The placing prompt now says what stands on the table in the picture stands
  at z=0. It also says moving a piece to pass the checker is not allowed, and
  that a picture check follows.

**Calibration ($0.11):** shown the stored try-3 design, the check said "not
the same". Its reasons were the right ones:
- the legs and feet are on top of the wing instead of underneath;
- the curved pieces form a hump instead of legs.

**Super Sprinter's redo with the check ($2.33):** 6 tries, no booklet.
- Two tries came back empty: Wonder used its whole 32,000-token reply limit
  thinking.
- One try passed the validator and failed the picture check ("model upside
  down", "legs on top").

Since then, feedback restates the line format after an empty or garbled
reply. Super Sprinter stays verified without a booklet. That's honest: the
book stands it on legs that aren't held by studs.

## Full run: 40 verified, 60 queued

**What was compared:** 100 of 100 drafts got a second read.
- 96 second reads gave a list.
- Cookie-jar robot's gave none: "pictured only as a very small corner
  thumbnail". That counts as a disagreement.
- Across both reads, 570 of 728 lines agree (78%).

**Verified, two reads agree (40).** That's 29 of the 82 Wonder drafts and 11
of the 18 diagram drafts († below). They're listed by how their steps went,
in book order, with the element count:
- **With a booklet (11):** stingray (6), guitar (3), paintbrush (3), binoculars
  (3), apple-visitor (4), rabbit-both-ears (8), blueberry-cake (4), flying-bug
  (7), radar-dish-station (6), milky-way-shake-maker (4),
  birthday-cake-message (10).
- **No booklet, the picture isn't stud-held ("Cannot", 15):**
  - submarine (15), mini-tugboat (10), yoga-goose† (16), viking-longboat†
    (14), golf-club (3), mini-ghoul (3), town-square-puzzle-2† (9),
    hungry-elephant† (20), dog-face (6), bake-a-cake-ephant† (15), wise-owl
    (6), unknown-bird (10), baby-bird (4), puppy-power† (15),
    smoothie-robot (10).
  - Most are eyes or faces mounted on side studs. Others are flat lays
    butted edge to edge (dog face, the town-square puzzle), a piece on a
    jumper plate's off-grid stud (mini-tugboat), or a loose golf ball.
- **No booklet, the list uses the hinge plate (9):** dozy-dolphin† (18),
  happy-ghost† (12), frog-face (6), happy-bird (9), scaredy-bat (8),
  high-wire-home (21), planet-base-radio-tower (8), supergalactic-hero†
  (21), friendly-face-message (9).
- **No booklet, nothing passed both checks in 6 tries (5):** super-sprinter
  (10), mini-city-airplane (4), rabbit-half-listening (8), playful-plane†
  (14), rocket-shuttle† (20).

**Waiting for a hand-check (60)**, in queue order, with the number of lines
the reads differ on:
- **Start here, the printed totals:** sailing-ship (2), snappy-crab (1).
- **Then the no-unsure-line diagram drafts:** tiny-tentacles† (2),
  mini-city-car† (2).
- **Then book order:**
  - yo-yo-fish (2), zigzagger (2), deep-sea-flatfish (2), shark (5), mr-croc
    (1), hungry-t-rex (2), baby-fish (1), colorful-chameleon (1),
    magical-mermaid (5), sleepy-sea-monster (3), sleepy-mermaid (5),
    magical-sea-monster (1), inspector-duck† (3), dream-mansion (6),
    entrance-gates (4), apple-tree (1), traffic-light (1);
  - tallest-building (2), wider-building (4), potions-table (3), ghost-bat
    (2), eerie-eyeballs (2), town-square-puzzle-1† (4), elephant-cake (1),
    la-la-llama† (3), giraffe-face (1), lazy-bug (1), hot-air-balloon† (2),
    unknown-helicopter (1), unknown-airplane (1), grand-throne (3),
    fancy-bird-table (1), moo-airlines (1);
  - flying-sofa (4), flying-snail (4), super-pug (5), robot-space-pincers
    (4), mini-robot-spy-eye (4), clean-up-robot (2), space-rocket† (2),
    mobile-base (1), four-legged-space-station (2), walking-sink (2),
    intergalactic-phone (1), laser-umbrella (4), pancake-maker (6), jetpack
    (1), cookie-jar-robot (1), dj-space-elements (4), eyebot (3);
  - kitchen-cupboard (4), green-party-alien (4), blue-bored-alien (1),
    dance-party-alien (5), alien-commander (4), race-car-message (4).
- 19 of the 60 differ on a single line.

**The printed totals as a cross-check:**
- Submarine (15) and mini-tugboat (10) agree across both reads and are
  verified.
- Sailing ship and snappy crab are at the head of the queue:
  - sailing ship: a lime tall side-stud brick against a white edge-stud tile;
  - snappy crab: one dark purple 1x2 plate.

### What "verified by two reads" means, and its limit

Two conversations with the same model, the same photos and the same checker
agreeing on every kind and count is evidence, not proof: both reads can
share a blind spot. They often did doubt the same lines:
- Of the 256 lines the 40 verified lists agree on, **both reads marked 103
  unsure**: hidden pieces, colours the book prints differently.
- One read marked another 56 unsure.
- **Only Guitar was sure on every line in both reads.**

So this is the verification rule as asked for (agreement on every line). It
is weaker than house and tree's hand-check, and the app labels it
differently:
- the chip reads "✓ Verified piece list (two reads of the page agree)";
- the booklet notes say nobody has built it from these steps yet;
- a hand-check overrides it.

## Booklet coverage

- **11 of the 40 verified builds have a booklet (28%).** The app's 41 verified
  builds include house and tree, so 12 of the 41 have one.
- The 11 passed in 1–3 tries ($0.15–0.95 each).
- **Every booklet passed both checks:** the validator, and the picture
  comparison with the page. A test runs the validator again on every
  committed design and rebuilds its steps.
- **I compared two of them with the page by eye:**
  - Stingray: wedge wings across, lime tail out the back, eyes at the front.
  - Rabbit with both ears: azure face, eyes, white nose, purple mouth, and the
    wedge ears below the face plates.

  Both match the book's layout.
- **The drawings are simplified, as in every BinBuild booklet:**
  - wedge plates are drawn as rectangles;
  - round tiles are drawn as round plates;
  - the azure curved slope is drawn 2 plates tall, not 4. That piece is
    Hungry bird's top piece, and nothing sits on it.
- **The 29 without a booklet** say why on their card: "No step-by-step
  booklet: … Build it from the book, page N." None was forced.

## In the app

- "What can I build?" lists 41 verified manual builds first, in book order:
  house and tree plus these 40.
- Each gets the bin check against the confirmed inventory. The 12 with a
  booklet get **Make the booklet**.
- The section note counts honestly: "41 with a verified piece list … 12 of
  them have a step-by-step booklet."
- The printable checklist (`GET /api/manual/checklist`) and
  `python -m backend.manual_check` list only the 60 still waiting.
  - The header says how many two reads verified.
  - Each card starts with a red box: the lines where the reads differ.
- `python -m backend.manual_verify --report` prints where every draft stands
  without making a call.

## Cost

| Run | Builds | Calls | Cost |
|---|---|---|---|
| Pilot (reads + steps) | 3 | 7 | $1.45 |
| Picture-check calibration (Super Sprinter's try 3) | 1 | 1 | $0.11 |
| Steps redo with the picture check (Super Sprinter) | 1 | 7 | $2.33 |
| Second reads, the other 97 | 97 | 97 | $11.43 |
| Steps for the other 38 verified (9 hinge-plate builds: no call) | 38 | 85 | $20.45 |
| **Total** | | **197** | **$35.77** |

- The steps runs cost the most, $23.81 of the $35.77. The 5 builds that used
  all 6 tries cost $11.53 of it.
- Each draft file records what its own calls cost: $34.75 in all.
  - The difference is the pilot's first Super Sprinter steps ($0.91),
    replaced by the redo, plus the calibration call.
- The run logs, with Wonder's replies, are in git-ignored
  `data/manual-verify/`.
- The key comes from `.env` only. It is never printed or committed.
- Only the manual's page photos were sent.

## Files

| File | |
|---|---|
| `backend/manual_verify.py` | Second read, steps with the validator and the picture check, `--report`. CLI options: `--reads-only` / `--steps-only`, `--max-usd`, smallest builds first. |
| `backend/build_plan.py` | `reads_agree` and `verified`. A verified draft without steps gets the bin check and its named no-booklet reason. Booklet notes say how the build was verified. |
| `backend/booklet.py`, `backend/manual_check.py`, `backend/main.py` | The checklist, the CLI and the API show only what's still waiting, differences first. The summary counts two-read builds and booklets. |
| `app/app.js`, `app/sw.js` | "(two reads of the page agree)" chip; the booklet count in the section note; service worker v11. |
| `backend/manual_transcribe.py` | The "Elements you'll need" hint for diagram pages. |
| `backend/manual/drafts/*.json` | Every draft gains `second_read`. Verified ones gain `auto_steps`, and `steps` where a design passed. |
| `tests/test_manual_verify.py` | 16 tests on written replies, no calls. |
| `tests/test_manual_catalog.py` and others | Data-driven expectations: the 40, the queue, every booklet design validated again. |

## Tests

- **venv:** 199 tests in `tests/` plus Path A's 31
  (`backend.test_brickgpt_constraint`), all passing.
- **System `python3` (no Pillow):** 199 run, 93 skipped, the rest pass.
- **The 16 new tests** cover:
  - the read's independence;
  - line-by-line comparison;
  - verified vs queued;
  - the queue order;
  - the differences on the card and in the CLI;
  - "Cannot" and the hinge plate;
  - at most 5 retries for the validator and for the picture check;
  - exactly the list;
  - a booklet through the set path;
  - hanging pieces in the layer steps;
  - hand-checked drafts left alone.

## Next blocker

People with the kit. The 60-build queue is targeted: each card starts with
the lines the reads disagree on, and 19 of the 60 differ on one line only.
Start with sailing ship and snappy crab, which have printed totals to check
against.

None of the 11 auto-built booklets has been built by hand yet. Building one
or two before the demo would test the "two reads + validator + picture check"
chain end to end.
