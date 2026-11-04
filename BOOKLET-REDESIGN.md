# Booklet redesign: make the drawings look like the book

Branch `spike/booklet-redesign`, from `main` a927ca1. Trigger: the carousel
covers didn't resemble their names ("the stingray doesn't look like a
stingray; the Lego design completely fails"). Ground truth: the book's
photos (`~/Downloads/lego manual`, viewed directly; no paid API used).
Quality bar taken from brickbybrickfun.com's scroll-to-build: real part
geometry (a wedge is tapered, a tile is flat), one clean isometric camera,
steps in layers. BinBuild's drawings stay schematic, but the silhouettes
now carry the part shapes.

## Function-level bugs found in the drawing code (backend/booklet.py)

All fixed in the function, so they heal every build at once:

1. **Wedge plates drew as full rectangles with studs on every cell.** A
   wedge plate has studs along one long edge only and tapers away from it.
   Now `place()` takes `studs=`; the surface falls away from the studded
   edge and only that edge's cells get studs.
2. **The `studs=` direction never reached the renderer.** The validator's
   design lines carry it, but `manual_verify.layer_steps` dropped it,
   `build_plan.draft_set` didn't pass it, and `booklet.place` had nowhere
   to keep it. Plumbed through all three; every draft's steps were
   regenerated from its validated design (each re-checked with
   `manual_verify.check_design`: the physical validator plus exactly the
   book's list).
3. **Round tiles drew as studded cylinders** — eyes looked like cans. A
   round tile is now a flat disc with no stud; a printed tile gets its
   print as a dark pupil, so eye tiles read as eyes.
4. **Jumper plates drew a stud on every cell.** The real part has one
   centre stud between the two cells; `picture()` now draws exactly that.
5. **Every curved slope drew 2 plates tall.** The azure 1x2 (LDraw 6091)
   is 4 plates with a stud on its flat end (now drawn, on that end), the
   1x3 is 3, the rest 2 (`CURVED_HEIGHTS`).

## Per build (worst first; book page in brackets)

| Build | Verdict | What differed / what changed |
|---|---|---|
| Stingray [20] | **FIXED** | Layout rebuilt from the photo: the two wedges ran along the body with the eyes on the blue plate in front of them, so the plan was a square with a tail. Now the wedges span the wingspan (tips out, studs on the head edge), the eyes sit on the wing roots at the centre, the tail runs from the centre, the blue plate peeks out at the head. Re-validated. Render reads as a stingray at a glance. |
| Paintbrush [23] | **BOOKLET WITHDRAWN** | The book's brush lies on its side (two round bricks end to end, lying down). The validator only connects pieces by studs from above, so this build cannot be expressed — the earlier booklet stacked it into a tower that read as a battery. It keeps its verified piece list and is honestly labelled "No step-by-step booklet: … lies on its side … build it from the book". Drops out of the carousel (11 cards). |
| Guitar [23] | FIXED (renderer) | White rectangle + green bar (a T). The wedge body now tapers with studs on one edge; reads as guitar body + neck. |
| Binoculars [23] | MATCH | Two upright grey tubes on the dark base, as pictured. (Renderer-neutral; unchanged.) |
| House and tree [28] | MATCH | Already read as its name; the hand-checked set is untouched. |
| Hungry llama [29] | FIXED (renderer) | The azure head drew 2 plates tall and flat-topped. With its true 4-plate curve and stud end it reads as the creature's head over the orange body on grey legs. |
| Rabbit face, both ears [48] | FIXED (renderer) | Ears were white rectangles, eyes studded cans, the muzzle studded all over. Now: tapered ears, flat eye discs with pupils, one centre stud on the jumper muzzle. The Nov 1 open question (ear orientation) is answered by the photo: ears extend from the face with studs along the inner edge — as designed. |
| Blueberry cake [51] | FIXED (renderer) | The wedge base now tapers like a cake slice under the purple layer and lime top. |
| Flying bug [64] | FIXED (renderer) | Eyes are now flat discs with pupils on the orange head; the wing wedge tapers. |
| Radar dish station [78] | FIXED (renderer + turn) | The dish wedge sat in front as a slab. The model is turned 180° (same model, re-validated) so the tapered dish reads at the back with the receiver head in front. |
| Mega-2000 Milky Way-shake maker [82] | MATCH | Upright stack — grey cube base, cylinder, two lime caps — exactly as pictured. |
| Birthday cake (message to aliens) [95] | FIXED (renderer) | Layered stack already; black curved slopes now keep their true heights at the base ends. |

Nothing was marked NEEDS-PHOTO: every booklet build's page was legible
enough to judge. No parts list changed — only the stingray's and radar's
layouts (same pieces, same counts, re-validated) and the paintbrush's
booklet status. No invented pieces or positions: every layout above is
the book's, within the owned 50 pieces / 21 kinds.

## Tests

`tests/test_booklet_redesign.py` (8): wedge studs/taper, flat printed
tile + pupil, jumper centre stud, curved heights, edge-stud tile; every
booklet build validates against its book list and renders; the stingray's
wing/eye/tail layout is pinned; the paintbrush stays verified without a
booklet. Full suite: 280 in tests/ + Path A's 31.

## Nov 2: real part shapes from LDraw

Branch `spike/ldraw-renders`, from `main` cb8e861. Trigger: on the live
site the pictures still looked very bad next to the book. The schematic
vector drawings above had reached their limit, so the renderer was
replaced: every booklet picture is now drawn from the parts' real shapes.

- `backend/ldraw_mesh.py` flattens the LDraw files of the kit's parts
  (`~/Downloads/ldraw`, BFC winding honoured, colour 16 inherits, edge and
  conditional lines kept) into `backend/ldraw_kit.json.gz` (160 KB,
  committed; rebuild with `python -m backend.ldraw_mesh`).
- `backend/ldraw_render.py` places those meshes on the booklet grid and
  draws them with a z-buffer (numpy), flat shading and the parts' own edge
  lines, like a printed instruction book. Hidden studs and faces vanish
  because they're behind something, not by rule. Each picture is a PNG
  embedded in the same `<svg>` the pages and carousel already used.
- Each build is drawn at the angle the book shows it (`"view"` in the set,
  or `"drawing"` in a draft: render-only hints — camera, which way a wedge
  tapers — never part of the validated design).
- The validator's directions now reach the drawing for every directional
  part: slope fall, wedge studded edge, clip end, side studs.

Real geometry shows real details: the black 1x2 curved slope (11477) has
its tall half raised one plate, so on the house a brick's studs show under
the middle of the roof. The book's picture shows the same step.

| Build | Verdict | What changed |
|---|---|---|
| Stingray [20] | MATCH | Re-read from a full-resolution crop: wings span the wingspan with all 4 studs of each showing, eyes on the azure plate in front of them, tail back from under the centre. The book centres the tail on the seam between the wings, half a stud off the grid, which studs can't hold; ours sits under the left wing root. |
| Guitar [23] | MATCH | Neck in line with the body's stud column and under its narrow end; round plate on the body's third stud from the neck. |
| Binoculars [23] | MATCH | |
| House and tree [28] | MATCH | Book's low front angle; set untouched. |
| Hungry llama [29] | MATCH | Head one stud forward, its stud end overhanging the front of the body so one orange stud shows behind it, as pictured. |
| Rabbit face, both ears [48] | MATCH | Ears in line with the face's outer columns, narrowing towards the face, seen from above like the book. In the book the ears lie loose next to the face; here each is held under the face's top row by one stud. |
| Blueberry cake [51] | **BOOKLET WITHDRAWN** | The picture shows 2 medium blue 1x1 cheese slopes on top that the list doesn't have (the kit has 2). Recorded as a `picture_check` that disagrees; the list is no longer verified and waits for a hand-check. |
| Flying bug [64] | CLOSE | Book's angle and wing taper. The book's picture is small and partly hidden; the arrangement may differ (the lime clip plate looks on top of the wing there). Noted in the draft. |
| Radar dish station [78] | MATCH | Mast moved so the dish covers its end and 4 lime studs show above the base, as pictured. |
| Milky Way-shake maker [82] | MATCH | |
| Birthday cake [95] | **BOOKLET WITHDRAWN** | The picture shows 3 black curved slopes (list: 2), dark purple either side of the front slope (list: 1) and a middle layer as wide as the 2x2 plate on it (list: one 1x2 brick). `picture_check` disagrees; waits for a hand-check. |

The carousel now has 9 cards. No list was changed or invented: layouts
moved only within each build's verified pieces (re-validated), and the two
lists the pictures contradict were withdrawn rather than patched.
`build_plan.reads_agree` treats a disagreeing `picture_check` like a
disagreeing second read, and the hand-check page lists its differences.

Tests: `tests/test_booklet_redesign.py` (12) checks every kit part has its
LDraw mesh, a wedge covers 3/4 of its plate, the eye tile has its print,
a slope falling the other way is the mirror image, pictures are embedded
PNGs, every booklet build validates and renders at its angle, the stingray
and radar layouts, and the withdrawn cakes. `test_full_loop` checks a stud
under a brick is hidden. Full suite: 285 in tests/ + Path A's 31, run with
all outside network blocked.

Part shapes: the [LDraw](https://www.ldraw.org) parts library, CC BY 4.0.
