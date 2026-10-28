# LEGO piece reference

Facts about real LEGO pieces (names, sizes, dimensions, weights) for the
inventory taxonomy, collected from public sources on 2026-10-28. Every number
below cites its source. [lego_piece_dimensions.json](lego_piece_dimensions.json)
holds the same data in machine-readable form: 236 pieces, each with family,
size, `length_mm`, `width_mm`, `height_mm` and, where BrickLink publishes one,
`weight_g`.

Nothing here was copied from anyone's code, design files, training data or
datasets: no LDraw geometry, no Rebrickable data. The part tables were built
from individual BrickLink catalogue pages and LEGO's and LDraw's published
specifications. The sources are listed at the end, and each part row links to
its own BrickLink page.

> Fan project, not affiliated with or endorsed by the LEGO Group. "LEGO" is a
> trademark of the LEGO Group.

## The numbers that matter

| Quantity | Value | LDraw units | Sources |
|---|---|---|---|
| Stud pitch (centre to centre, horizontal grid) | **8.0 mm** | 20 LDU | [1] [7] [12] [13] |
| Brick height, without the stud | **9.6 mm** | 24 LDU | [1] [7] [12] [13] |
| Plate height, without the stud (1/3 brick) | **3.2 mm** | 8 LDU | [2] [7] [9] [13] |
| Tile height (a plate with a smooth top) | **3.2 mm** | 8 LDU | [10] [14] |
| Stud diameter | **4.8 mm** | 12 LDU | [1] [7] [13] |
| Stud height | **≈1.7 mm** (sources give 1.6–1.9) | 4 LDU | [7] [10] [12] [13] |
| Clearance, per side | **0.1 mm** (a 1×1 is 7.8 mm across) | – | [13] |
| Compatibility tolerance | dimensions vary **at most 1%** | – | [1] |
| 1 LDraw unit (LDU) | ≈0.4 mm | 1 | [7] |

## 1. Dimensions

### The grid

- **LEGO's own figures.** A LEGO A/S patent [1] gives the classic 2×4 brick
  as about 3.2 cm long, 1.6 cm wide and 0.96 cm high without its knobs. Each
  knob is about 0.48 cm across.
  - Those figures are 8 mm per stud, a 9.6 mm brick and a 4.8 mm stud.
  - The same patent says dimensions may vary by at most 1% for elements to stay
    connectable.
- **Three plates make one brick.** LEGO's help pages say so [2], and so do
  BrickLink's naming standard [9] and Brick Architect [14].
- **LDraw's units.** The LDraw file format specification [7] uses whole units:
  - stud pitch 20 LDU, brick height 24 LDU, plate height 8 LDU;
  - stud diameter 12 LDU, stud height 4 LDU;
  - 1 LDU ≈ 0.4 mm, which LDraw calls an approximation.
- **Measured values.** LUGNET's FAQ [12] gives a stud pitch of 7.986 mm ± 2 µm
  at 25 °C, measured along a wall of Technic beams. From that and the ratios
  it derives:
  - a brick of 9.582 mm and a plate of 3.194 mm;
  - 1 LDU = 0.3993 mm.
  - 8.0 / 9.6 / 3.2 mm are the rounded values everyone uses.
- **The basic ratios.**
  - Stud pitch to plate height is 2:5, so 5 plates = 2 studs [12].
  - Brick height to stud pitch is 6:5 (24:20 LDU) [7] [12].
- **Moulded size and clearance.** Moulded parts are 0.2 mm smaller than the
  grid across, with 0.1 mm of clearance on each side [13]. A 1×1 is 7.8 mm and
  a 2×4 is 15.8 × 31.8 mm.
  - BrickLink's bounding box for the 4×10 brick, 31.8 × 79.8 mm, shows the
    same 0.2 mm [10].
  - Most smaller parts round to whole millimetres there.
- **Studs.** The nominal diameter is 4.8 mm [1] [13]; measured studs come out
  at 4.87–4.90 mm [13].
  - Stud-height references range from 1.6 to 1.8 mm [13], and LUGNET derives
    1.7 mm [12].
  - BrickLink's bounding boxes put a brick with its stud at 11.5 mm and a plate
    at 5.1 mm, which implies about 1.9 mm, rounded [10].
- **Material and precision.** LEGO switched from cellulose acetate to ABS in
  1963, and its history page says moulding was then done to an accuracy of
  1/200 mm [4]. That is a historical figure, not a current specification.
- **Stud-and-tube coupling.** LEGO filed the patent for the stud-and-tube
  coupling on 28 January 1958 [3]. LEGO's help page describes the tubes inside
  the two classic bricks [2]:
  - the 2×1 brick, made since 1952, has a solid tube;
  - the 2×4 has three hollow tubes.

### How sizes are named

- **Studs, width × length (× height).** BrickLink [9] writes stud dimensions as
  width × length × height. Width and length are counted in studs; height is
  counted in bricks.
  - Brick 2 × 4 × 3 is 2 studs wide, 4 long and 3 bricks tall.
  - LEGO itself names bricks the same way, "2x1" and "2x4" [2].
- **Default heights are left out.**
  - Plates and tiles are one plate high (1/3 brick), and that height is not
    written.
  - A plain brick's height of 1 is not written either.
  - Thinner-than-brick heights are written as fractions: 2/3 is two plates and
    1/3 is one.
- **Slopes put the slope direction first.** Slope 33 3 × 1 is 3 studs down
  the slope and 1 across [9]. The angle in the name (18, 30, 33, 45, 65, 75…)
  is approximate.
- **Technic lengths are in studs.** LEGO's Technic help page says every beam
  and axle comes with a number giving its length in studs [5].
  - BrickLink writes these as "L": Axle 4L is 4 studs (32 mm) long [9].
  - LEGO also publishes a printable 1:1 Technic measurement chart [5].
- **Wheels and tires use millimetres.**
  - BrickLink names wheels and some tires by diameter × width in mm, for
    example "Wheel 18mm D. x 14mm".
  - Numbers without a unit, as in "Tire 30.4 x 14", are nominal labels. They
    are often moulded on the tire and are not necessarily measurements [9].
- **DUPLO is twice the size in every direction.** It mixes with LEGO bricks
  [2].
- **Part numbers differ between catalogues.** The taxonomy should key on one
  catalogue (BrickLink here) and treat the others as aliases.

  | Same part | BrickLink | LDraw |
  |---|---|---|
  | Tile 1 × 1 | 3070 (lists 3070b as an alternate) | `3070b.dat` "Tile 1 x 1 with Groove" |
  | Plate, round 1 × 1 | 4073 (lists 6141 as an alternate) | `4073.dat` moved to `6141.dat` |
  | Thick liftarm, 3 holes | 32523 "Technic, Liftarm Thick 1 x 3" | "Technic Beam 3" |
  | Thin liftarm, 6 holes | 32063 "Technic, Liftarm Thin 1 x 6" | "Technic Beam 6 x 0.5" (half thickness) |
  | Slope 45 2 × 2 | 3039 "Slope 45 2 x 2" | "Slope Brick 45 2 x 2" |
  | Minifig head | 3626 (lists 3626b and 3626c as alternates) | `3626c.dat` "Minifig Head with Hollow Stud" |

  Sources: BrickLink part pages [10] and LDraw part-file title lines [8]. The
  LDraw files were read for their title line only.

### Weights

LEGO does not publish part weights; no LEGO source found gives one. BrickLink's
catalogue lists a weight for every part fetched here [10]. Selected values:

| Part | Name | Weight g | | Part | Name | Weight g |
|---|---|---|---|---|---|---|
| 3005 | Brick 1 × 1 | 0.44 | | 3024 | Plate 1 × 1 | 0.20 |
| 3004 | Brick 1 × 2 | 0.83 | | 3023 | Plate 1 × 2 | 0.36 |
| 3010 | Brick 1 × 4 | 1.64 | | 3022 | Plate 2 × 2 | 0.64 |
| 3009 | Brick 1 × 6 | 2.42 | | 3020 | Plate 2 × 4 | 1.20 |
| 3008 | Brick 1 × 8 | 3.21 | | 3070 | Tile 1 × 1 | 0.16 |
| 3003 | Brick 2 × 2 | 1.35 | | 3069 | Tile 1 × 2 | 0.26 |
| 3001 | Brick 2 × 4 | 2.32 | | 3068 | Tile 2 × 2 | 0.49 |
| 2456 | Brick 2 × 6 | 3.74 | | 3626 | Minifig head | 0.54 |

The left column is exactly BrickGPT's 8 generator bricks.

## 2. Piece families and their standard sizes

The size lists below come from BrickLink's category listings [11], read on
2026-10-28. The count in brackets is how many catalogue entries the category
holds, including variants such as old moulds and special versions. Every size
named here is a size BrickLink lists as a real part.

### Bricks: Brick (66 entries) and Brick, Round (96)

- **1 brick tall:**
  - 1 × 1, 1 × 2, 1 × 3, 1 × 4, 1 × 6, 1 × 8, 1 × 10, 1 × 12, 1 × 16;
  - 2 × 2, 2 × 3, 2 × 4, 2 × 6, 2 × 8, 2 × 10;
  - 4 × 6, 4 × 10, 4 × 12, 4 × 18; 8 × 8, 8 × 16; 12 × 24.
  - There are no 1 × 5, 1 × 7, 2 × 5 or 2 × 7 bricks.
- **Corners:** 2 × 2 and 4 × 4.
- **Taller:**
  - 1 × 1 × 3, 1 × 1 × 5;
  - 1 × 2 × 2, 1 × 2 × 3, 1 × 2 × 5;
  - 1 × 3 × 5, 1 × 4 × 3, 1 × 6 × 5;
  - 2 × 2 × 3, 2 × 4 × 3, 2 × 6 × 3.
- **Round:**
  - 1 × 1 and 2 × 2 (with axle hole), 4 × 4 (with hole);
  - domes, and macaroni and corner pieces up to 16 × 16.

### Plates: Plate (44 entries) and Plate, Round (84)

- **1 ×:** 1, 2, 3, 4, 5, 6, 8, 10, 12.
- **2 ×:** 2, 3, 4, 6, 8, 10, 12, 14, 16.
- **3 × 3; 4 ×:** 4, 6, 8, 10, 12.
- **6 ×:** 6, 8, 10, 12, 14, 16, 24.
- **Large:** 8 × 8, 8 × 11, 8 × 16, 16 × 16.
- **Corners:** 2 × 2, 3 × 3, 4 × 4.
- **Round:**
  - 1 × 1, 2 × 2 (with axle hole);
  - 4 × 4, 6 × 6 and 8 × 8 (with hole).
- **Jumper plates** (1 × 2 or 2 × 2 with one centred stud) are in Plate,
  Modified.

### Tiles: Tile (24 entries) and Tile, Round (31)

- **1 ×:** 1, 2, 3, 4, 6, 8.
- **2 ×:** 2, 3, 4, 6.
- **Larger:** 3 × 6, 4 × 4, 4 × 8, 6 × 8.
- **Corner:** 2 × 2.
- **Round:** 1 × 1, 2 × 2, 3 × 3, 6 × 6.
- **Grille tile:** 1 × 2, in Tile, Modified.

### Slopes: Slope (82), Slope, Curved (83), Slope, Inverted (30)

- **Angles in the catalogue:** 10, 14, 15, 18, 25, 30, 33, 45, 53, 65, 75.
- **45°:**
  - 2 × 1, 2 × 2, 2 × 3, 2 × 4, 2 × 6, 2 × 8, 4 × 4;
  - double 2 × 2, 2 × 3, 2 × 4, 6 × 8.
- **33°:** 3 × 1, 3 × 2, 3 × 3, 3 × 4, 3 × 6; double 2 × 2, 2 × 4.
- **30° (2/3 tall):** 1 × 1, 1 × 2, 1 × 3, 1 × 4.
- **Other angles:**
  - 18°: 4 × 1, 4 × 2;
  - 65°: 2 × 1 × 2;
  - 75°: 2 × 1 × 3, 2 × 2 × 3.
- **Curved:** 1 × 1, 2 × 1, 2 × 2, 3 × 1, 4 × 1, 4 × 2, 6 × 1, 8 × 1, 8 × 2, 10 × 1,
  12 × 1, and others.
- **Inverted 45°:** 2 × 1, 2 × 2, and others.

### Wheels and tires: Wheel (274) and Wheel, Tire & Tread (129)

- **Wheel diameters in BrickLink's names (mm):**
  - 8, 11, 14, 15, 18, 21;
  - 30, 30.4, 31, 36.8, 41, 43.2;
  - 55.7, 56, 61.6, 62.3, 75, 107.1.
- **Wheel widths:** 6–46 mm.
- **Tires** are labelled either in mm ("14mm D. x 4mm", "21mm D. x 9mm") or with
  nominal pairs ("30.4 x 14", "43.2 x 22", "56 x 26", "81.6 x 34").

### Windows and doors: Window (135), Door (101), Door, Frame (56), Window, Glass & Shutter (54)

- **Windows:**
  - 1 × 1 × 1, 1 × 1 × 2, 1 × 2 × 1, 1 × 2 × 2, 1 × 2 × 3;
  - 1 × 3 × 2, 1 × 3 × 3;
  - 1 × 4 × 2, 1 × 4 × 3, 1 × 4 × 5, 1 × 4 × 6;
  - 1 × 6 × 2, 1 × 6 × 3, 1 × 6 × 5, 1 × 6 × 6;
  - 2 × 4 × 3, 3 × 3 × 2, 4 × 4 × 3.
- **Doors:**
  - 1 × 2 × 3;
  - 1 × 3 × 1 to 1 × 3 × 6;
  - 1 × 4 × 3 to 1 × 4 × 11;
  - 1 × 5 × 4, 1 × 6 × 6 to 1 × 6 × 10.
- **Frames and fillers:** current windows and doors are a frame plus a separate
  glass pane or door leaf.

### Technic: Liftarm (79), Axle (40), Pin (26), Gear (101), Brick (88), Connector (132)

- **Thick liftarms (straight):** 1 × 1 (spacer), 1 × 2, 1 × 3, 1 × 5, 1 × 7,
  1 × 9, 1 × 11, 1 × 13, 1 × 15. Above 3, only odd lengths appear.
- **Thin liftarms (half thickness):** 1 × 2, 1 × 3, 1 × 4, 1 × 5, 1 × 6, 1 × 7.
- **Axles:**
  - every length from 2L to 12L, plus 16L and 32L;
  - versions with a stop: 3L, 3.5L, 4L, 4.5L, 5L, 5.5L, 8L.
- **Pins:**
  - 1/2, 3/4, 2L and 3L, with or without friction ridges;
  - axle 1L + pin 1L.
- **Gears (teeth):** 8, 12, 14, 16, 18, 20, 22, 24, 28, 36, 40, 64.
  - Bevel, double-bevel, crown and clutch variants.
  - Worm screws, racks and differentials.
- **Technic bricks with holes:**
  - 1 × 1, 1 × 2, 1 × 3, 1 × 4, 1 × 6, 1 × 8, 1 × 10, 1 × 12, 1 × 14, 1 × 16;
  - 2 × 4;
  - open-centre frames 4 × 4, 4 × 6, 6 × 8.
- **Connectors:** bushes (full and half), axle connectors (2L, 3L), and
  axle-and-pin connectors.

### Minifigure parts: Head (4384), Torso (7158), Legs (45), Hair (644), Headgear (1474), Body Part (1673)

- **What a minifig is:** a head, a torso (with arms and hands), and hips with
  two legs.
- **Height:** LEGO says a minifigure is four standard bricks tall without
  headgear [6]. That is 4 × 9.6 = 38.4 mm, our arithmetic.
- **Why the counts are high:** nearly all the entries are printed variants of
  the same few shapes.

### Other common families

- Arch (44): 1 × 3, 1 × 4, 1 × 6, 1 × 4 × 2, 1 × 6 × 2, 1 × 8 × 2, 1 × 12 × 3, and others.
- Cone (32): 1 × 1, 2 × 2 × 2, 4 × 4 × 2, and others.
- Bracket (50): stud-on-side parts such as 1 × 2 – 1 × 2 and 1 × 2 – 2 × 2.
- Hinge (124).
- Plant (60).
- Dish (20): 2 × 2 up to 10 × 10.
- Bar (69).
- Baseplate (84): 16 × 16, 32 × 32, and others.

### Measured parts by family

These are the 236 parts in the JSON. **W × L × H** are nominal grid sizes where
`Basis` is `nominal_grid`: studs × 8 mm across and plates × 3.2 mm tall, with
no stud. For other bases, see `dims_basis_values` in the JSON:

- `name_mm`: the mm in BrickLink's name;
- `name_nominative`: a nominal label;
- `bricklink_bbox`: BrickLink's bounding box, studs included.

The `Grid` column is explained in section 3.

### Bricks (32)

| Part | Name | Size | W × L × H mm | Basis | Weight g | Grid |
|---|---|---|---|---|---|---|
| [3005](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3005) | Brick 1 x 1 | 1x1 | 8 × 8 × 9.6 | nominal_grid | 0.44 | stud_grid |
| [3004](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3004) | Brick 1 x 2 | 1x2 | 8 × 16 × 9.6 | nominal_grid | 0.83 | stud_grid |
| [3622](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3622) | Brick 1 x 3 | 1x3 | 8 × 24 × 9.6 | nominal_grid | 1.24 | stud_grid |
| [3010](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3010) | Brick 1 x 4 | 1x4 | 8 × 32 × 9.6 | nominal_grid | 1.64 | stud_grid |
| [3009](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3009) | Brick 1 x 6 | 1x6 | 8 × 48 × 9.6 | nominal_grid | 2.42 | stud_grid |
| [3008](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3008) | Brick 1 x 8 | 1x8 | 8 × 64 × 9.6 | nominal_grid | 3.21 | stud_grid |
| [6111](https://www.bricklink.com/v2/catalog/catalogitem.page?P=6111) | Brick 1 x 10 | 1x10 | 8 × 80 × 9.6 | nominal_grid | 3.8 | stud_grid |
| [6112](https://www.bricklink.com/v2/catalog/catalogitem.page?P=6112) | Brick 1 x 12 | 1x12 | 8 × 96 × 9.6 | nominal_grid | 4.8 | stud_grid |
| [2465](https://www.bricklink.com/v2/catalog/catalogitem.page?P=2465) | Brick 1 x 16 | 1x16 | 8 × 128 × 9.6 | nominal_grid | 6.2 | stud_grid |
| [3003](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3003) | Brick 2 x 2 | 2x2 | 16 × 16 × 9.6 | nominal_grid | 1.35 | stud_grid |
| [3002](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3002) | Brick 2 x 3 | 2x3 | 16 × 24 × 9.6 | nominal_grid | 1.92 | stud_grid |
| [3001](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3001) | Brick 2 x 4 | 2x4 | 16 × 32 × 9.6 | nominal_grid | 2.32 | stud_grid |
| [2456](https://www.bricklink.com/v2/catalog/catalogitem.page?P=2456) | Brick 2 x 6 | 2x6 | 16 × 48 × 9.6 | nominal_grid | 3.74 | stud_grid |
| [3007](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3007) | Brick 2 x 8 | 2x8 | 16 × 64 × 9.6 | nominal_grid | 4.75 | stud_grid |
| [3006](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3006) | Brick 2 x 10 | 2x10 | 16 × 80 × 9.6 | nominal_grid | 5.75 | stud_grid |
| [2356](https://www.bricklink.com/v2/catalog/catalogitem.page?P=2356) | Brick 4 x 6 | 4x6 | 32 × 48 × 9.6 | nominal_grid | 6.3 | stud_grid |
| [6212](https://www.bricklink.com/v2/catalog/catalogitem.page?P=6212) | Brick 4 x 10 | 4x10 | 32 × 80 × 9.6 | nominal_grid | 9.5 | stud_grid |
| [4202](https://www.bricklink.com/v2/catalog/catalogitem.page?P=4202) | Brick 4 x 12 | 4x12 | 32 × 96 × 9.6 | nominal_grid | 11.5 | stud_grid |
| [4201](https://www.bricklink.com/v2/catalog/catalogitem.page?P=4201) | Brick 8 x 8 | 8x8 | 64 × 64 × 9.6 | nominal_grid | 16.3 | stud_grid |
| [4204](https://www.bricklink.com/v2/catalog/catalogitem.page?P=4204) | Brick 8 x 16 | 8x16 | 64 × 128 × 9.6 | nominal_grid | 30.66 | stud_grid |
| [2357](https://www.bricklink.com/v2/catalog/catalogitem.page?P=2357) | Brick 2 x 2 Corner | 2x2 | 16 × 16 × 9.6 | nominal_grid | 1.25 | stud_grid |
| [14716](https://www.bricklink.com/v2/catalog/catalogitem.page?P=14716) | Brick 1 x 1 x 3 | 1x1x3 | 8 × 8 × 28.8 | nominal_grid | 1.24 | stud_grid |
| [2453b](https://www.bricklink.com/v2/catalog/catalogitem.page?P=2453b) | Brick 1 x 1 x 5 - Solid Stud | 1x1x5 | 8 × 8 × 48 | nominal_grid | 2.13 | stud_grid |
| [22886](https://www.bricklink.com/v2/catalog/catalogitem.page?P=22886) | Brick 1 x 2 x 3 | 1x2x3 | 8 × 16 × 28.8 | nominal_grid | 2.1 | stud_grid |
| [3245c](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3245c) | Brick 1 x 2 x 2 with Inside Stud Holder | 1x2x2 | 8 × 16 × 19.2 | nominal_grid | 1.5 | stud_grid |
| [2454](https://www.bricklink.com/v2/catalog/catalogitem.page?P=2454) | Brick 1 x 2 x 5 | 1x2x5 | 8 × 16 × 48 | nominal_grid | 3.49 | stud_grid |
| [49311](https://www.bricklink.com/v2/catalog/catalogitem.page?P=49311) | Brick 1 x 4 x 3 | 1x4x3 | 8 × 32 × 28.8 | nominal_grid | 3.97 | stud_grid |
| [30145](https://www.bricklink.com/v2/catalog/catalogitem.page?P=30145) | Brick 2 x 2 x 3 | 2x2x3 | 16 × 16 × 28.8 | nominal_grid | 3.75 | stud_grid |
| [30144](https://www.bricklink.com/v2/catalog/catalogitem.page?P=30144) | Brick 2 x 4 x 3 | 2x4x3 | 16 × 32 × 28.8 | nominal_grid | 6.73 | stud_grid |
| [6213](https://www.bricklink.com/v2/catalog/catalogitem.page?P=6213) | Brick 2 x 6 x 3 | 2x6x3 | 16 × 48 × 28.8 | nominal_grid | 10.18 | stud_grid |
| [3062](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3062) | Brick, Round 1 x 1 | 1x1 | 8 × 8 × 9.6 | nominal_grid | 0.28 | stud_grid |
| [3941](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3941) | Brick, Round 2 x 2 with Axle Hole | 2x2 | 16 × 16 × 9.6 | nominal_grid | 1.2 | stud_grid |

### Plates (37)

| Part | Name | Size | W × L × H mm | Basis | Weight g | Grid |
|---|---|---|---|---|---|---|
| [3024](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3024) | Plate 1 x 1 | 1x1 | 8 × 8 × 3.2 | nominal_grid | 0.2 | stud_grid |
| [3023](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3023) | Plate 1 x 2 | 1x2 | 8 × 16 × 3.2 | nominal_grid | 0.36 | stud_grid |
| [3623](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3623) | Plate 1 x 3 | 1x3 | 8 × 24 × 3.2 | nominal_grid | 0.53 | stud_grid |
| [3710](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3710) | Plate 1 x 4 | 1x4 | 8 × 32 × 3.2 | nominal_grid | 0.71 | stud_grid |
| [78329](https://www.bricklink.com/v2/catalog/catalogitem.page?P=78329) | Plate 1 x 5 | 1x5 | 8 × 40 × 3.2 | nominal_grid | 0.9 | stud_grid |
| [3666](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3666) | Plate 1 x 6 | 1x6 | 8 × 48 × 3.2 | nominal_grid | 1.06 | stud_grid |
| [3460](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3460) | Plate 1 x 8 | 1x8 | 8 × 64 × 3.2 | nominal_grid | 1.36 | stud_grid |
| [4477](https://www.bricklink.com/v2/catalog/catalogitem.page?P=4477) | Plate 1 x 10 | 1x10 | 8 × 80 × 3.2 | nominal_grid | 1.61 | stud_grid |
| [60479](https://www.bricklink.com/v2/catalog/catalogitem.page?P=60479) | Plate 1 x 12 | 1x12 | 8 × 96 × 3.2 | nominal_grid | 1.95 | stud_grid |
| [3022](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3022) | Plate 2 x 2 | 2x2 | 16 × 16 × 3.2 | nominal_grid | 0.64 | stud_grid |
| [3021](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3021) | Plate 2 x 3 | 2x3 | 16 × 24 × 3.2 | nominal_grid | 0.93 | stud_grid |
| [3020](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3020) | Plate 2 x 4 | 2x4 | 16 × 32 × 3.2 | nominal_grid | 1.2 | stud_grid |
| [3795](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3795) | Plate 2 x 6 | 2x6 | 16 × 48 × 3.2 | nominal_grid | 1.74 | stud_grid |
| [3034](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3034) | Plate 2 x 8 | 2x8 | 16 × 64 × 3.2 | nominal_grid | 2.27 | stud_grid |
| [3832](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3832) | Plate 2 x 10 | 2x10 | 16 × 80 × 3.2 | nominal_grid | 2.91 | stud_grid |
| [2445](https://www.bricklink.com/v2/catalog/catalogitem.page?P=2445) | Plate 2 x 12 | 2x12 | 16 × 96 × 3.2 | nominal_grid | 3.5 | stud_grid |
| [4282](https://www.bricklink.com/v2/catalog/catalogitem.page?P=4282) | Plate 2 x 16 | 2x16 | 16 × 128 × 3.2 | nominal_grid | 4.5 | stud_grid |
| [11212](https://www.bricklink.com/v2/catalog/catalogitem.page?P=11212) | Plate 3 x 3 | 3x3 | 24 × 24 × 3.2 | nominal_grid | 1.25 | stud_grid |
| [3031](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3031) | Plate 4 x 4 | 4x4 | 32 × 32 × 3.2 | nominal_grid | 2.22 | stud_grid |
| [3032](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3032) | Plate 4 x 6 | 4x6 | 32 × 48 × 3.2 | nominal_grid | 3.3 | stud_grid |
| [3035](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3035) | Plate 4 x 8 | 4x8 | 32 × 64 × 3.2 | nominal_grid | 4.7 | stud_grid |
| [3030](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3030) | Plate 4 x 10 | 4x10 | 32 × 80 × 3.2 | nominal_grid | 5.55 | stud_grid |
| [3029](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3029) | Plate 4 x 12 | 4x12 | 32 × 96 × 3.2 | nominal_grid | 6.76 | stud_grid |
| [3958](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3958) | Plate 6 x 6 | 6x6 | 48 × 48 × 3.2 | nominal_grid | 4.71 | stud_grid |
| [3036](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3036) | Plate 6 x 8 | 6x8 | 48 × 64 × 3.2 | nominal_grid | 6.4 | stud_grid |
| [3033](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3033) | Plate 6 x 10 | 6x10 | 48 × 80 × 3.2 | nominal_grid | 7.95 | stud_grid |
| [3028](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3028) | Plate 6 x 12 | 6x12 | 48 × 96 × 3.2 | nominal_grid | 9.47 | stud_grid |
| [3027](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3027) | Plate 6 x 16 | 6x16 | 48 × 128 × 3.2 | nominal_grid | 13.27 | stud_grid |
| [3026](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3026) | Plate 6 x 24 | 6x24 | 48 × 192 × 3.2 | nominal_grid | 19.43 | stud_grid |
| [41539](https://www.bricklink.com/v2/catalog/catalogitem.page?P=41539) | Plate 8 x 8 | 8x8 | 64 × 64 × 3.2 | nominal_grid | 9.4 | stud_grid |
| [92438](https://www.bricklink.com/v2/catalog/catalogitem.page?P=92438) | Plate 8 x 16 | 8x16 | 64 × 128 × 3.2 | nominal_grid | 17 | stud_grid |
| [91405](https://www.bricklink.com/v2/catalog/catalogitem.page?P=91405) | Plate 16 x 16 | 16x16 | 128 × 128 × 3.2 | nominal_grid | 35 | stud_grid |
| [2420](https://www.bricklink.com/v2/catalog/catalogitem.page?P=2420) | Plate 2 x 2 Corner | 2x2 | 16 × 16 × 3.2 | nominal_grid | 0.54 | stud_grid |
| [4073](https://www.bricklink.com/v2/catalog/catalogitem.page?P=4073) | Plate, Round 1 x 1 | 1x1 | 8 × 8 × 3.2 | nominal_grid | 0.12 | stud_grid |
| [4032](https://www.bricklink.com/v2/catalog/catalogitem.page?P=4032) | Plate, Round 2 x 2 with Axle Hole | 2x2 | 16 × 16 × 3.2 | nominal_grid | 0.37 | stud_grid |
| [15573](https://www.bricklink.com/v2/catalog/catalogitem.page?P=15573) | Plate, Modified 1 x 2 with 1 Stud with Groove and Bottom Stud Holder (Jumper) | 1x2 | 8 × 16 × 3.2 | nominal_grid | 0.3 | half_stud_offset |
| [87580](https://www.bricklink.com/v2/catalog/catalogitem.page?P=87580) | Plate, Modified 2 x 2 with Groove and 1 Stud in Center (Jumper) | 2x2 | 16 × 16 × 3.2 | nominal_grid | 0.52 | half_stud_offset |

### Tiles (18)

| Part | Name | Size | W × L × H mm | Basis | Weight g | Grid |
|---|---|---|---|---|---|---|
| [3070](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3070) | Tile 1 x 1 | 1x1 | 8 × 8 × 3.2 | nominal_grid | 0.16 | grid_bottom_only |
| [3069](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3069) | Tile 1 x 2 | 1x2 | 8 × 16 × 3.2 | nominal_grid | 0.26 | grid_bottom_only |
| [63864](https://www.bricklink.com/v2/catalog/catalogitem.page?P=63864) | Tile 1 x 3 | 1x3 | 8 × 24 × 3.2 | nominal_grid | 0.4 | grid_bottom_only |
| [2431](https://www.bricklink.com/v2/catalog/catalogitem.page?P=2431) | Tile 1 x 4 | 1x4 | 8 × 32 × 3.2 | nominal_grid | 0.54 | grid_bottom_only |
| [6636](https://www.bricklink.com/v2/catalog/catalogitem.page?P=6636) | Tile 1 x 6 | 1x6 | 8 × 48 × 3.2 | nominal_grid | 0.83 | grid_bottom_only |
| [4162](https://www.bricklink.com/v2/catalog/catalogitem.page?P=4162) | Tile 1 x 8 | 1x8 | 8 × 64 × 3.2 | nominal_grid | 1.06 | grid_bottom_only |
| [3068](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3068) | Tile 2 x 2 | 2x2 | 16 × 16 × 3.2 | nominal_grid | 0.49 | grid_bottom_only |
| [26603](https://www.bricklink.com/v2/catalog/catalogitem.page?P=26603) | Tile 2 x 3 | 2x3 | 16 × 24 × 3.2 | nominal_grid | 0.68 | grid_bottom_only |
| [87079](https://www.bricklink.com/v2/catalog/catalogitem.page?P=87079) | Tile 2 x 4 | 2x4 | 16 × 32 × 3.2 | nominal_grid | 0.9 | grid_bottom_only |
| [69729](https://www.bricklink.com/v2/catalog/catalogitem.page?P=69729) | Tile 2 x 6 | 2x6 | 16 × 48 × 3.2 | nominal_grid | 1.35 | grid_bottom_only |
| [6934a](https://www.bricklink.com/v2/catalog/catalogitem.page?P=6934a) | Tile 3 x 6 | 3x6 | 24 × 48 × 3.2 | nominal_grid | 1.73 | grid_bottom_only |
| [1751](https://www.bricklink.com/v2/catalog/catalogitem.page?P=1751) | Tile 4 x 4 | 4x4 | 32 × 32 × 3.2 | nominal_grid | 1.75 | grid_bottom_only |
| [8165](https://www.bricklink.com/v2/catalog/catalogitem.page?P=8165) | Tile 4 x 8 | 4x8 | 32 × 64 × 3.2 | nominal_grid | 3.45 | grid_bottom_only |
| [6320](https://www.bricklink.com/v2/catalog/catalogitem.page?P=6320) | Tile 6 x 8 | 6x8 | 48 × 64 × 3.2 | nominal_grid | 5 | grid_bottom_only |
| [14719](https://www.bricklink.com/v2/catalog/catalogitem.page?P=14719) | Tile 2 x 2 Corner | 2x2 | 16 × 16 × 3.2 | nominal_grid | 0.43 | grid_bottom_only |
| [98138](https://www.bricklink.com/v2/catalog/catalogitem.page?P=98138) | Tile, Round 1 x 1 | 1x1 | 8 × 8 × 3.2 | nominal_grid | 0.11 | grid_bottom_only |
| [4150](https://www.bricklink.com/v2/catalog/catalogitem.page?P=4150) | Tile, Round 2 x 2 | 2x2 | 16 × 16 × 3.2 | nominal_grid | 0.33 | grid_bottom_only |
| [2412b](https://www.bricklink.com/v2/catalog/catalogitem.page?P=2412b) | Tile, Modified 1 x 2 Grille with Bottom Groove | 1x2 | 8 × 16 × 3.2 | nominal_grid | 0.23 | grid_bottom_only |

### Slopes (22)

| Part | Name | Size | W × L × H mm | Basis | Weight g | Grid |
|---|---|---|---|---|---|---|
| [54200](https://www.bricklink.com/v2/catalog/catalogitem.page?P=54200) | Slope 30 1 x 1 x 2/3 | 1x1x2/3 | 8 × 8 × 6.4 | nominal_grid | 0.21 | sloped_top |
| [85984](https://www.bricklink.com/v2/catalog/catalogitem.page?P=85984) | Slope 30 1 x 2 x 2/3 | 1x2x2/3 | 8 × 16 × 6.4 | nominal_grid | 0.35 | sloped_top |
| [60477](https://www.bricklink.com/v2/catalog/catalogitem.page?P=60477) | Slope 18 4 x 1 | 4x1 | 32 × 8 × 9.6 | nominal_grid | 1.1 | sloped_top |
| [3040](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3040) | Slope 45 2 x 1 | 2x1 | 16 × 8 × 9.6 | nominal_grid | 0.69 | sloped_top |
| [3039](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3039) | Slope 45 2 x 2 | 2x2 | 16 × 16 × 9.6 | nominal_grid | 1.15 | sloped_top |
| [3038](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3038) | Slope 45 2 x 3 | 2x3 | 16 × 24 × 9.6 | nominal_grid | 1.72 | sloped_top |
| [3037](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3037) | Slope 45 2 x 4 | 2x4 | 16 × 32 × 9.6 | nominal_grid | 1.97 | sloped_top |
| [4286](https://www.bricklink.com/v2/catalog/catalogitem.page?P=4286) | Slope 33 3 x 1 | 3x1 | 24 × 8 × 9.6 | nominal_grid | 0.98 | sloped_top |
| [3298](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3298) | Slope 33 3 x 2 | 3x2 | 24 × 16 × 9.6 | nominal_grid | 1.33 | sloped_top |
| [4161](https://www.bricklink.com/v2/catalog/catalogitem.page?P=4161) | Slope 33 3 x 3 | 3x3 | 24 × 24 × 9.6 | nominal_grid | 1.94 | sloped_top |
| [3297](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3297) | Slope 33 3 x 4 | 3x4 | 24 × 32 × 9.6 | nominal_grid | 2.57 | sloped_top |
| [60481](https://www.bricklink.com/v2/catalog/catalogitem.page?P=60481) | Slope 65 2 x 1 x 2 | 2x1x2 | 16 × 8 × 19.2 | nominal_grid | 1.16 | sloped_top |
| [4460b](https://www.bricklink.com/v2/catalog/catalogitem.page?P=4460b) | Slope 75 2 x 1 x 3 - Hollow Stud | 2x1x3 | 16 × 8 × 28.8 | nominal_grid | 1.68 | sloped_top |
| [3300](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3300) | Slope 33 2 x 2 Double | 2x2 | 16 × 16 × 4.8 | nominal_grid | 0.54 | sloped_top |
| [3043](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3043) | Slope 45 2 x 2 Double | 2x2 | 16 × 16 × 9.6 | nominal_grid | 0.91 | sloped_top |
| [11477](https://www.bricklink.com/v2/catalog/catalogitem.page?P=11477) | Slope, Curved 2 x 1 x 2/3 | 2x1x2/3 | 16 × 8 × 6.4 | nominal_grid | 0.31 | sloped_top |
| [15068](https://www.bricklink.com/v2/catalog/catalogitem.page?P=15068) | Slope, Curved 2 x 2 x 2/3 | 2x2x2/3 | 16 × 16 × 6.4 | nominal_grid | 0.57 | sloped_top |
| [50950](https://www.bricklink.com/v2/catalog/catalogitem.page?P=50950) | Slope, Curved 3 x 1 | 3x1 | 24 × 8 × 9.6 | nominal_grid | 0.75 | sloped_top |
| [61678](https://www.bricklink.com/v2/catalog/catalogitem.page?P=61678) | Slope, Curved 4 x 1 | 4x1 | 32 × 8 × 9.6 | nominal_grid | 0.8 | sloped_top |
| [93606](https://www.bricklink.com/v2/catalog/catalogitem.page?P=93606) | Slope, Curved 4 x 2 | 4x2 | 32 × 16 × 9.6 | nominal_grid | 1.4 | sloped_top |
| [3665](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3665) | Slope, Inverted 45 2 x 1 | 2x1 | 16 × 8 × 9.6 | nominal_grid | 0.69 | sloped_bottom |
| [3660](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3660) | Slope, Inverted 45 2 x 2 with Flat Bottom Pin | 2x2 | 16 × 16 × 9.6 | nominal_grid | 1.25 | sloped_bottom |

### Wheels and tires (17)

| Part | Name | Size | W × L × H mm | Basis | Weight g | Grid |
|---|---|---|---|---|---|---|
| [4624](https://www.bricklink.com/v2/catalog/catalogitem.page?P=4624) | Wheel 8mm D. x 6mm | 8x6 | 6 × 8 × 8 | name_mm | 0.22 | off_grid |
| [50944](https://www.bricklink.com/v2/catalog/catalogitem.page?P=50944) | Wheel 11mm D. x 6mm with 5 Spokes | 11x6 | 6 × 11 × 11 | name_mm | 0.32 | off_grid |
| [56902](https://www.bricklink.com/v2/catalog/catalogitem.page?P=56902) | Wheel 18mm D. x 8mm with Fake Bolts and Shallow Spokes | 18x8 | 8 × 18 × 18 | name_mm | 1.02 | off_grid |
| [30285](https://www.bricklink.com/v2/catalog/catalogitem.page?P=30285) | Wheel 18mm D. x 14mm | 18x14 | 14 × 18 × 18 | name_mm | 1.5 | off_grid |
| [55981](https://www.bricklink.com/v2/catalog/catalogitem.page?P=55981) | Wheel 18mm D. x 14mm with Pin Hole, Fake Bolts and Shallow Spokes | 18x14 | 14 × 18 × 18 | name_mm | 1.82 | off_grid |
| [56904](https://www.bricklink.com/v2/catalog/catalogitem.page?P=56904) | Wheel 30mm D. x 14mm | 30x14 | 14 × 30 × 30 | name_mm | 4.1 | off_grid |
| [56145](https://www.bricklink.com/v2/catalog/catalogitem.page?P=56145) | Wheel 30.4mm D. x 20mm with No Pin Holes and Reinforced Rim | 30.4x20 | 20 × 30.4 × 30.4 | name_mm | 4.25 | off_grid |
| [3139](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3139) | Tire 14mm D. x 4mm Smooth Small Single | 14x4 | 4 × 14 × 14 | name_mm | 0.4 | off_grid |
| [50945](https://www.bricklink.com/v2/catalog/catalogitem.page?P=50945) | Tire 14mm D. x 6mm Solid Smooth | 14x6 | 6 × 14 × 14 | name_mm | 0.42 | off_grid |
| [3641](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3641) | Tire 15mm D. x 6mm Offset Tread Small | 15x6 | 6 × 15 × 15 | name_mm | 0.73 | off_grid |
| [92409](https://www.bricklink.com/v2/catalog/catalogitem.page?P=92409) | Tire 17.5mm D. x 6mm with Shallow Staggered Treads - Band Around Center of Tread | 17.5x6 | 6 × 17.5 × 17.5 | name_mm | 0.78 | off_grid |
| [4084](https://www.bricklink.com/v2/catalog/catalogitem.page?P=4084) | Tire 21mm D. x 9mm Offset Tread Medium | 21x9 | 9 × 21 × 21 | name_mm | 2.38 | off_grid |
| [6578](https://www.bricklink.com/v2/catalog/catalogitem.page?P=6578) | Tire 30.4 x 14 VR | 30.4x14 | 14 × 30.4 × 30.4 | name_nominative | 4.75 | off_grid |
| [58090](https://www.bricklink.com/v2/catalog/catalogitem.page?P=58090) | Tire 30.4 x 14 Solid | 30.4x14 | 14 × 30.4 × 30.4 | name_nominative | 7.61 | off_grid |
| [30391](https://www.bricklink.com/v2/catalog/catalogitem.page?P=30391) | Tire 30.4 x 14 Offset Tread | 30.4x14 | 14 × 30.4 × 30.4 | name_nominative | 6.5 | off_grid |
| [44309](https://www.bricklink.com/v2/catalog/catalogitem.page?P=44309) | Tire 43.2 x 22 ZR | 43.2x22 | 22 × 43.2 × 43.2 | name_nominative | 11.15 | off_grid |
| [61481](https://www.bricklink.com/v2/catalog/catalogitem.page?P=61481) | Tire 43.2mm D. x 26mm Balloon Small | 43.2x26 | 26 × 43.2 × 43.2 | name_mm | 8.5 | off_grid |

### Windows and doors (10)

| Part | Name | Size | W × L × H mm | Basis | Weight g | Grid |
|---|---|---|---|---|---|---|
| [60592](https://www.bricklink.com/v2/catalog/catalogitem.page?P=60592) | Window 1 x 2 x 2 Flat Front | 1x2x2 | 8 × 16 × 19.2 | nominal_grid | 1 | stud_grid |
| [60593](https://www.bricklink.com/v2/catalog/catalogitem.page?P=60593) | Window 1 x 2 x 3 Flat Front | 1x2x3 | 8 × 16 × 28.8 | nominal_grid | 1.3 | stud_grid |
| [51239](https://www.bricklink.com/v2/catalog/catalogitem.page?P=51239) | Window 1 x 3 x 3 Flat Front | 1x3x3 | 8 × 24 × 28.8 | nominal_grid | 1.6 | stud_grid |
| [60594](https://www.bricklink.com/v2/catalog/catalogitem.page?P=60594) | Window 1 x 4 x 3 - No Shutter Tabs | 1x4x3 | 8 × 32 × 28.8 | nominal_grid | 1.85 | stud_grid |
| [60601](https://www.bricklink.com/v2/catalog/catalogitem.page?P=60601) | Glass for Window 1 x 2 x 2 Flat Front | 1x2x2 | 13.2 × 15.6 × 1.6 | bricklink_bbox | 0.28 | off_grid |
| [60602](https://www.bricklink.com/v2/catalog/catalogitem.page?P=60602) | Glass for Window 1 x 2 x 3 Flat Front | 1x2x3 | 1.6 × 13.2 × 25.2 | bricklink_bbox | 0.55 | off_grid |
| [60603](https://www.bricklink.com/v2/catalog/catalogitem.page?P=60603) | Glass for Window 1 x 4 x 3 - Opening | 1x4x3 | 29.4 × 23.8 × 3 | bricklink_bbox | 1.2 | off_grid |
| [60596](https://www.bricklink.com/v2/catalog/catalogitem.page?P=60596) | Door, Frame 1 x 4 x 6 with 2 Holes on Top and Bottom | 1x4x6 | 8 × 32 × 57.6 | nominal_grid | 3.2 | stud_grid |
| [60616](https://www.bricklink.com/v2/catalog/catalogitem.page?P=60616) | Door 1 x 4 x 6 with Stud Handle | 1x4x6 | 6.5 × 28.6 × 53.4 | bricklink_bbox | 2.8 | off_grid |
| [60623](https://www.bricklink.com/v2/catalog/catalogitem.page?P=60623) | Door 1 x 4 x 6 with 4 Panes and Stud Handle | 1x4x6 | 6.5 × 28.6 × 53.4 | bricklink_bbox | 1.92 | off_grid |

### Technic (65)

| Part | Name | Size | W × L × H mm | Basis | Weight g | Grid |
|---|---|---|---|---|---|---|
| [6541](https://www.bricklink.com/v2/catalog/catalogitem.page?P=6541) | Technic, Brick 1 x 1 with Hole | 1x1 | 8 × 8 × 9.6 | nominal_grid | 0.38 | stud_grid |
| [3700](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3700) | Technic, Brick 1 x 2 with Hole | 1x2 | 8 × 16 × 9.6 | nominal_grid | 0.82 | stud_grid |
| [32000](https://www.bricklink.com/v2/catalog/catalogitem.page?P=32000) | Technic, Brick 1 x 2 with Holes | 1x2 | 8 × 16 × 9.6 | nominal_grid | 0.73 | stud_grid |
| [3701](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3701) | Technic, Brick 1 x 4 with Holes | 1x4 | 8 × 32 × 9.6 | nominal_grid | 1.46 | stud_grid |
| [3894](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3894) | Technic, Brick 1 x 6 with Holes | 1x6 | 8 × 48 × 9.6 | nominal_grid | 2.2 | stud_grid |
| [3702](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3702) | Technic, Brick 1 x 8 with Holes | 1x8 | 8 × 64 × 9.6 | nominal_grid | 2.85 | stud_grid |
| [2730](https://www.bricklink.com/v2/catalog/catalogitem.page?P=2730) | Technic, Brick 1 x 10 with Holes | 1x10 | 8 × 80 × 9.6 | nominal_grid | 3.67 | stud_grid |
| [3895](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3895) | Technic, Brick 1 x 12 with Holes | 1x12 | 8 × 96 × 9.6 | nominal_grid | 4.2 | stud_grid |
| [32018](https://www.bricklink.com/v2/catalog/catalogitem.page?P=32018) | Technic, Brick 1 x 14 with Holes | 1x14 | 8 × 112 × 9.6 | nominal_grid | 4.92 | stud_grid |
| [3703](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3703) | Technic, Brick 1 x 16 with Holes | 1x16 | 8 × 128 × 9.6 | nominal_grid | 5.87 | stud_grid |
| [18654](https://www.bricklink.com/v2/catalog/catalogitem.page?P=18654) | Technic, Liftarm Thick 1 x 1 (Spacer) | 1L | 8 × 8 × 8 | nominal_grid_length | 0.17 | technic_holes |
| [43857](https://www.bricklink.com/v2/catalog/catalogitem.page?P=43857) | Technic, Liftarm Thick 1 x 2 | 2L | 8 × 16 × 8 | nominal_grid_length | 0.4 | technic_holes |
| [32523](https://www.bricklink.com/v2/catalog/catalogitem.page?P=32523) | Technic, Liftarm Thick 1 x 3 | 3L | 8 × 24 × 8 | nominal_grid_length | 0.7 | technic_holes |
| [32316](https://www.bricklink.com/v2/catalog/catalogitem.page?P=32316) | Technic, Liftarm Thick 1 x 5 | 5L | 8 × 40 × 8 | nominal_grid_length | 1.25 | technic_holes |
| [32524](https://www.bricklink.com/v2/catalog/catalogitem.page?P=32524) | Technic, Liftarm Thick 1 x 7 | 7L | 8 × 56 × 8 | nominal_grid_length | 1.74 | technic_holes |
| [40490](https://www.bricklink.com/v2/catalog/catalogitem.page?P=40490) | Technic, Liftarm Thick 1 x 9 | 9L | 8 × 72 × 8 | nominal_grid_length | 2.59 | technic_holes |
| [32525](https://www.bricklink.com/v2/catalog/catalogitem.page?P=32525) | Technic, Liftarm Thick 1 x 11 | 11L | 8 × 88 × 8 | nominal_grid_length | 2.8 | technic_holes |
| [41239](https://www.bricklink.com/v2/catalog/catalogitem.page?P=41239) | Technic, Liftarm Thick 1 x 13 | 13L | 8 × 104 × 8 | nominal_grid_length | 3.3 | technic_holes |
| [32278](https://www.bricklink.com/v2/catalog/catalogitem.page?P=32278) | Technic, Liftarm Thick 1 x 15 | 15L | 8 × 120 × 8 | nominal_grid_length | 4 | technic_holes |
| [41677](https://www.bricklink.com/v2/catalog/catalogitem.page?P=41677) | Technic, Liftarm Thin 1 x 2 - Axle Holes | 2L | 8 × 16 × 4 | nominal_grid_length | 0.33 | technic_holes |
| [6632](https://www.bricklink.com/v2/catalog/catalogitem.page?P=6632) | Technic, Liftarm Thin 1 x 3 - Axle Holes | 3L | 8 × 24 × 4 | nominal_grid_length | 0.45 | technic_holes |
| [32449](https://www.bricklink.com/v2/catalog/catalogitem.page?P=32449) | Technic, Liftarm Thin 1 x 4 - Axle Holes | 4L | 8 × 32 × 4 | nominal_grid_length | 0.55 | technic_holes |
| [32017](https://www.bricklink.com/v2/catalog/catalogitem.page?P=32017) | Technic, Liftarm Thin 1 x 5 | 5L | 8 × 40 × 4 | nominal_grid_length | 0.58 | technic_holes |
| [32063](https://www.bricklink.com/v2/catalog/catalogitem.page?P=32063) | Technic, Liftarm Thin 1 x 6 | 6L | 8 × 48 × 4 | nominal_grid_length | 0.8 | technic_holes |
| [32065](https://www.bricklink.com/v2/catalog/catalogitem.page?P=32065) | Technic, Liftarm Thin 1 x 7 | 7L | 8 × 56 × 4 | nominal_grid_length | 0.9 | technic_holes |
| [3704](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3704) | Technic, Axle 2L | 2L | 4.8 × 16 × 4.8 | nominal_grid_length | 0.27 | technic_holes |
| [32062](https://www.bricklink.com/v2/catalog/catalogitem.page?P=32062) | Technic, Axle 2L Notched | 2L | 4.4 × 16 × 4.4 | nominal_grid_length | 0.26 | technic_holes |
| [4519](https://www.bricklink.com/v2/catalog/catalogitem.page?P=4519) | Technic, Axle 3L | 3L | 4.4 × 24 × 4.4 | nominal_grid_length | 0.43 | technic_holes |
| [3705](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3705) | Technic, Axle 4L | 4L | 4.4 × 32 × 4.4 | nominal_grid_length | 0.59 | technic_holes |
| [87083](https://www.bricklink.com/v2/catalog/catalogitem.page?P=87083) | Technic, Axle 4L with Stop | 4L | 6 × 32 × 6 | nominal_grid_length | 0.59 | technic_holes |
| [32073](https://www.bricklink.com/v2/catalog/catalogitem.page?P=32073) | Technic, Axle 5L | 5L | 4.4 × 40 × 4.4 | nominal_grid_length | 0.66 | technic_holes |
| [3706](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3706) | Technic, Axle 6L | 6L | 4.4 × 48 × 4.4 | nominal_grid_length | 0.86 | technic_holes |
| [44294](https://www.bricklink.com/v2/catalog/catalogitem.page?P=44294) | Technic, Axle 7L | 7L | 4.4 × 56 × 4.4 | nominal_grid_length | 1.05 | technic_holes |
| [3707](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3707) | Technic, Axle 8L | 8L | 4.4 × 64 × 4.4 | nominal_grid_length | 1.18 | technic_holes |
| [60485](https://www.bricklink.com/v2/catalog/catalogitem.page?P=60485) | Technic, Axle 9L | 9L | 4.4 × 72 × 4.4 | nominal_grid_length | 1.3 | technic_holes |
| [3737](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3737) | Technic, Axle 10L | 10L | – × 80 × – | nominal_grid_length | 1.49 | technic_holes |
| [23948](https://www.bricklink.com/v2/catalog/catalogitem.page?P=23948) | Technic, Axle 11L | 11L | – × 88 × – | nominal_grid_length | 1.65 | technic_holes |
| [3708](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3708) | Technic, Axle 12L | 12L | – × 96 × – | nominal_grid_length | 1.82 | technic_holes |
| [50451](https://www.bricklink.com/v2/catalog/catalogitem.page?P=50451) | Technic, Axle 16L | 16L | – × 128 × – | nominal_grid_length | 2.37 | technic_holes |
| [4274](https://www.bricklink.com/v2/catalog/catalogitem.page?P=4274) | Technic, Pin 1/2 without Friction Ridges | 1/2 | 6 × 9.7 × 6 | bricklink_bbox | 0.1 | technic_holes |
| [32002](https://www.bricklink.com/v2/catalog/catalogitem.page?P=32002) | Technic, Pin 3/4 | 3/4 | 6.8 × 12 × 6.4 | bricklink_bbox | 0.11 | technic_holes |
| [3673](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3673) | Technic, Pin without Friction Ridges | 2L | 6.8 × 16 × 6.4 | bricklink_bbox | 0.16 | technic_holes |
| [2780](https://www.bricklink.com/v2/catalog/catalogitem.page?P=2780) | Technic, Pin with Short Friction Ridges | 2L | 6 × 16 × 6 | bricklink_bbox | 0.2 | technic_holes |
| [6558](https://www.bricklink.com/v2/catalog/catalogitem.page?P=6558) | Technic, Pin 3L with Friction Ridges | 3L | 6 × 24 × 6 | bricklink_bbox | 0.37 | technic_holes |
| [32556](https://www.bricklink.com/v2/catalog/catalogitem.page?P=32556) | Technic, Pin 3L without Friction Ridges | 3L | 6.8 × 24 × 6.4 | bricklink_bbox | 0.25 | technic_holes |
| [43093](https://www.bricklink.com/v2/catalog/catalogitem.page?P=43093) | Technic, Axle 1L with Pin with Friction Ridges | 1L+1L | 6 × 16 × 6 | bricklink_bbox | 0.26 | technic_holes |
| [3749](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3749) | Technic, Axle 1L with Pin without Friction Ridges with Round Hole | 1L+1L | 5.9 × 16 × 5.9 | bricklink_bbox | 0.22 | technic_holes |
| [3713](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3713) | Technic Bush | – | 7.3 × 8 × 7.2 | bricklink_bbox | 0.14 | technic_holes |
| [4265c](https://www.bricklink.com/v2/catalog/catalogitem.page?P=4265c) | Technic Bush 1/2 Smooth | – | 7.2 × 7.2 × 4 | bricklink_bbox | 0.1 | technic_holes |
| [6538c](https://www.bricklink.com/v2/catalog/catalogitem.page?P=6538c) | Technic, Axle Connector 2L (Smooth with x Hole + Orientation) | – | 7.6 × 16 × 7.4 | bricklink_bbox | 0.4 | technic_holes |
| [6536](https://www.bricklink.com/v2/catalog/catalogitem.page?P=6536) | Technic, Axle and Pin Connector Perpendicular | – | 8 × 15.3 × 8 | bricklink_bbox | 0.39 | technic_holes |
| [32039](https://www.bricklink.com/v2/catalog/catalogitem.page?P=32039) | Technic, Axle Connector with Axle Hole | – | 8 × 16 × 7.5 | bricklink_bbox | 0.32 | technic_holes |
| [3647](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3647) | Technic, Gear 8 Tooth | 8T | 9.9 × 9.9 × 8 | bricklink_bbox | 0.16 | technic_holes |
| [6589](https://www.bricklink.com/v2/catalog/catalogitem.page?P=6589) | Technic, Gear 12 Tooth Bevel | 12T | 12.8 × 12.8 × 4 | bricklink_bbox | 0.29 | technic_holes |
| [32270](https://www.bricklink.com/v2/catalog/catalogitem.page?P=32270) | Technic, Gear 12 Tooth Double Bevel | 12T | 13.6 × 13.6 × 8 | bricklink_bbox | 0.58 | technic_holes |
| [4019](https://www.bricklink.com/v2/catalog/catalogitem.page?P=4019) | Technic, Gear 16 Tooth - Axle Hole with Open Sides | 16T | 17.3 × 17.3 × 8 | bricklink_bbox | 0.7 | technic_holes |
| [94925](https://www.bricklink.com/v2/catalog/catalogitem.page?P=94925) | Technic, Gear 16 Tooth - Axle Hole with Closed Sides | 16T | 17.3 × 17.3 × 8 | bricklink_bbox | 0.7 | technic_holes |
| [32198](https://www.bricklink.com/v2/catalog/catalogitem.page?P=32198) | Technic, Gear 20 Tooth Bevel | 20T | 20.8 × 20.8 × 4 | bricklink_bbox | 0.75 | technic_holes |
| [32269](https://www.bricklink.com/v2/catalog/catalogitem.page?P=32269) | Technic, Gear 20 Tooth Double Bevel | 20T | 21.6 × 21.6 × 8 | bricklink_bbox | 1.4 | technic_holes |
| [3648](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3648) | Technic, Gear 24 Tooth with 1 Axle Hole | 24T | 25.7 × 25.7 × 7.7 | bricklink_bbox | 1.17 | technic_holes |
| [3650b](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3650b) | Technic, Gear 24 Tooth Crown - Reinforced | 24T | 26.9 × 26.9 × 8 | bricklink_bbox | 1.1 | technic_holes |
| [46372](https://www.bricklink.com/v2/catalog/catalogitem.page?P=46372) | Technic, Gear 28 Tooth Double Bevel | 28T | 29 × 29 × 8 | bricklink_bbox | 2.7 | technic_holes |
| [32498](https://www.bricklink.com/v2/catalog/catalogitem.page?P=32498) | Technic, Gear 36 Tooth Double Bevel | 36T | 40.2 × 40.2 × 8 | bricklink_bbox | 3.5 | technic_holes |
| [3649](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3649) | Technic, Gear 40 Tooth | 40T | 48.2 × 48.2 × 8 | bricklink_bbox | 3.76 | technic_holes |
| [4716](https://www.bricklink.com/v2/catalog/catalogitem.page?P=4716) | Technic, Gear Worm Screw, Long | worm | 10.2 × 10.2 × 16 | bricklink_bbox | 0.6 | technic_holes |

### Minifigure parts (12)

| Part | Name | Size | W × L × H mm | Basis | Weight g | Grid |
|---|---|---|---|---|---|---|
| [3626](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3626) | Minifigure, Head (Plain) | – | 10.2 × 10.2 × 11.4 | bricklink_bbox | 0.54 | minifig |
| [973](https://www.bricklink.com/v2/catalog/catalogitem.page?P=973) | Torso Plain | – | 15.4 × 7.8 × 18.6 | bricklink_bbox | 0.82 | minifig |
| [970c00](https://www.bricklink.com/v2/catalog/catalogitem.page?P=970c00) | Hips and Legs Plain | – | 15 × 8 × 20.5 | bricklink_bbox | 1.18 | minifig |
| [970](https://www.bricklink.com/v2/catalog/catalogitem.page?P=970) | Hips | – | 14.4 × 13.9 × 9.7 | bricklink_bbox | 0.4 | minifig |
| [971](https://www.bricklink.com/v2/catalog/catalogitem.page?P=971) | Leg, Right | – | 7.2 × 14.8 × 8 | bricklink_bbox | 0.3 | minifig |
| [972](https://www.bricklink.com/v2/catalog/catalogitem.page?P=972) | Leg, Left | – | 7.2 × 14.8 × 8 | bricklink_bbox | 0.3 | minifig |
| [981](https://www.bricklink.com/v2/catalog/catalogitem.page?P=981) | Arm, Left | – | 12.5 × 6.5 × 6 | bricklink_bbox | 0.15 | minifig |
| [982](https://www.bricklink.com/v2/catalog/catalogitem.page?P=982) | Arm, Right | – | 12.5 × 6.5 × 6 | bricklink_bbox | 0.15 | minifig |
| [983](https://www.bricklink.com/v2/catalog/catalogitem.page?P=983) | Hand | – | 13 × 5 × 5 | bricklink_bbox | 0.09 | minifig |
| [3901](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3901) | Minifigure, Hair Male Smooth | – | 12 × 12 × 10 | bricklink_bbox | 0.3 | minifig |
| [3624](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3624) | Minifigure, Headgear Hat, Police | – | 13.1 × 6.4 × 14.3 | bricklink_bbox | 0.41 | minifig |
| [3833](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3833) | Minifigure, Headgear Helmet Construction | – | 17 × 6.8 × 19.4 | bricklink_bbox | 0.3 | minifig |

### Other common families (23)

| Part | Name | Size | W × L × H mm | Basis | Weight g | Grid |
|---|---|---|---|---|---|---|
| [4490](https://www.bricklink.com/v2/catalog/catalogitem.page?P=4490) | Arch 1 x 3 | 1x3 | 8 × 24 × 9.6 | nominal_grid | 1.03 | partial_grid |
| [3659](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3659) | Arch 1 x 4 | 1x4 | 8 × 32 × 9.6 | nominal_grid | 1.25 | partial_grid |
| [3455](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3455) | Arch 1 x 6 | 1x6 | 8 × 48 × 9.6 | nominal_grid | 1.71 | partial_grid |
| [6182](https://www.bricklink.com/v2/catalog/catalogitem.page?P=6182) | Arch 1 x 4 x 2 | 1x4x2 | 8 × 32 × 19.2 | nominal_grid | 2.07 | partial_grid |
| [3308](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3308) | Arch 1 x 8 x 2 | 1x8x2 | 8 × 64 × 19.2 | nominal_grid | 3.83 | partial_grid |
| [4589](https://www.bricklink.com/v2/catalog/catalogitem.page?P=4589) | Cone 1 x 1 | 1x1 | 8 × 8 × 9.6 | nominal_grid | 0.26 | stud_grid |
| [3942c](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3942c) | Cone 2 x 2 x 2 - Open Stud | 2x2x2 | 16 × 16 × 19.2 | nominal_grid | 1.32 | stud_grid |
| [99781](https://www.bricklink.com/v2/catalog/catalogitem.page?P=99781) | Bracket 1 x 2 - 1 x 2 | 1x2 | 16 × 9.6 × 11.2 | bricklink_bbox | 0.55 | rotated_grid |
| [99780](https://www.bricklink.com/v2/catalog/catalogitem.page?P=99780) | Bracket 1 x 2 - 1 x 2 Inverted | 1x2 | 16 × 8 × 11.2 | bricklink_bbox | 0.55 | rotated_grid |
| [44728](https://www.bricklink.com/v2/catalog/catalogitem.page?P=44728) | Bracket 1 x 2 - 2 x 2 | 1x2 | 16 × 17.6 × 11.2 | bricklink_bbox | 0.8 | rotated_grid |
| [3937](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3937) | Hinge Brick 1 x 2 Base | 1x2 | 8 × 16 × 9.6 | nominal_grid | 0.48 | partial_grid |
| [3938](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3938) | Hinge Brick 1 x 2 Top Plate | 1x2 | 8 × 16 × 3.2 | nominal_grid | 0.34 | partial_grid |
| [4081b](https://www.bricklink.com/v2/catalog/catalogitem.page?P=4081b) | Plate, Modified 1 x 1 with Light Attachment - Thick Ring | 1x1 | 8 × 6.4 × 15.2 | bricklink_bbox | 0.35 | stud_grid |
| [61252](https://www.bricklink.com/v2/catalog/catalogitem.page?P=61252) | Plate, Modified 1 x 1 with Open O Clip (Horizontal Grip) | 1x1 | 8 × 8.3 × 13.7 | bricklink_bbox | 0.27 | stud_grid |
| [2423](https://www.bricklink.com/v2/catalog/catalogitem.page?P=2423) | Plant Leaves 4 x 3 | 4x3 | 32 × 24 × 3.2 | nominal_grid | 0.44 | partial_grid |
| [2417](https://www.bricklink.com/v2/catalog/catalogitem.page?P=2417) | Plant Leaves 6 x 5 | 6x5 | 48 × 40 × 3.2 | nominal_grid | 1.07 | partial_grid |
| [3741](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3741) | Plant Flower Stem with Stud and 3 Stems | – | 14 × 14 × 18 | bricklink_bbox | 0.2 | off_grid |
| [3742](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3742) | Plant Flower Small | – | 9 × 9.7 × 2.4 | bricklink_bbox | 0.07 | off_grid |
| [4740](https://www.bricklink.com/v2/catalog/catalogitem.page?P=4740) | Dish 2 x 2 Inverted (Radar) | 2x2 | 16 × 16 × 3.2 | nominal_grid | 0.28 | partial_grid |
| [3960](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3960) | Dish 4 x 4 Inverted (Radar) with Solid Stud | 4x4 | 32 × 32 × 6.4 | nominal_grid | 1.33 | partial_grid |
| [87994](https://www.bricklink.com/v2/catalog/catalogitem.page?P=87994) | Bar 3L (Bar Arrow) | – | 24 × 3.2 × 3.2 | bricklink_bbox | 0.2 | off_grid |
| [3811](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3811) | Baseplate 32 x 32 | 32x32 | 256 × 256 × – | nominal_grid | 107 | grid_top_only |
| [3867](https://www.bricklink.com/v2/catalog/catalogitem.page?P=3867) | Baseplate 16 x 16 | 16x16 | 128 × 128 × – | nominal_grid | 26.25 | grid_top_only |


## 3. How the sizes relate

### One grid: 8 mm across, 3.2 mm up

- **Across, the grid is the stud pitch, 8 mm** [1] [7]. Everything with studs
  or stud receptacles sits on it.
- **Up, the step is one plate, 3.2 mm.** A brick is 3 plates [2], so any stack
  of bricks and plates is a whole number of plates tall.
- **5 plates = 2 studs = 16 mm.** The ratio is 2:5 [12], and in LDraw units
  5 × 8 = 2 × 20 [7].
  - So **1 brick + 2 plates = 2 studs**.
  - This is why a Technic brick, two plates and another Technic brick put two
    holes 16 mm apart vertically, the same as two hole pitches horizontally.
    That is our arithmetic from the figures above.
- **1 stud = 2.5 plates.** An odd number of studs can never equal a whole
  number of plates, again our arithmetic. Turning a part on its side therefore
  works cleanly only across even stud counts.
- **Technic holes sit about 0.2 mm above the centre** of a brick's height [13],
  so stud-on-side and Technic geometry don't line up perfectly.

### Which families stack on the grid

| Family | Footprint on the 8 mm grid | Height in whole plates | Takes pieces on top | Attaches underneath | Stack-compatible |
|---|---|---|---|---|---|
| Bricks (standard, tall, round, corner) | yes | yes: 3 per brick | yes | yes | **yes** |
| Plates | yes | yes: 1 | yes | yes | **yes** |
| Tiles | yes | yes: 1 | **no**, smooth top | yes | bottom only, as a top layer |
| Jumper plates | yes underneath | yes: 1 | offset by half a stud | yes | yes, shifted 4 mm |
| Slopes | yes underneath | mostly (2/3, 1, 2, 3 bricks)\* | only a flat top row | yes | bottom only |
| Inverted slopes | yes on top | yes | yes | only the flat part | top only |
| Technic bricks | yes | yes: 3 | yes | yes | **yes**, with holes sideways |
| Windows, door frames | yes | yes (n bricks) | yes | yes | **yes** |
| Arches | yes | yes | yes | ends only | yes, with an open span |
| Brackets | yes, plus a face turned 90° | – | yes | yes | yes, and sideways |
| Baseplates | yes | thinner than a plate | yes | **no** | base only |
| Technic liftarms | holes at 8 mm, **no studs** | **no**: 8 mm thick, or 4 mm thin\*\* | no | no | **no**: pins and axles |
| Axles, pins, bushes, gears | lengths in 8 mm steps | no | no | no | **no** |
| Wheels and tires | **no**: diameters in mm\*\*\* | no | no | no | **no**: on axles or pins |
| Glass panes, door leaves | no: fit inside frames | – | no | no | no |
| Minifigure parts | partly | no | head stud | leg holes | partly |

\* Most slopes are whole plate heights. Some are not: BrickLink lists the 33°
2 × 2 double slope (3300) as 1/2 brick tall, which is 1.5 plates [10].

\*\* BrickLink's bounding boxes give 8.0 mm for thick liftarms and 4.0 mm for
thin ones [10], and LDraw names the thin ones "× 0.5" [8]. 8 mm is
2.5 plates, so a liftarm lying flat never matches a brick stack.

\*\*\* For example, 18 mm is 2.25 studs, 30.4 mm is 3.8 studs and 43.2 mm is
5.4 studs.

### What this means for the inventory

- **Generation can count on exact geometry only for parts that obey both
  grids.** BrickGPT's 8 bricks do, at 1 × n or 2 × n by 1 brick tall.
- **Plates and tiles share the grid but use the 3.2 mm step.** Three plates
  stand in for one brick of height, but they are not the same part.
- **Slopes, Technic parts, wheels and minifigs don't stack on the grid as
  bricks.** That matches the taxonomy's rule that only the 8 are
  generator-ready.

## 4. Cross-check: the taxonomy's part numbers

The taxonomy on branch `spike/inventory-taxonomy` holds 131 part numbers, and
TAXONOMY.md says they were not checked against a catalogue. This research
checked every one against BrickLink. Nothing on that branch was changed; these
notes are for whoever updates it.

- **126 of 131 are BrickLink item numbers**, and BrickLink's name matches the
  intended part. That includes all 8 generator bricks: 3005, 3004, 3010, 3009,
  3008, 3003, 3001, 2456.
- **5 are not BrickLink numbers:**

  | Taxonomy key | Taxonomy number | BrickLink |
  |---|---|---|
  | `brick_1x2x2` | 3245 | 3245b (with inside axle holder) or 3245c (with inside stud holder) |
  | `plate_round_1x1` | 6141 | listed as an alternate of 4073, which the taxonomy also has |
  | `plate_jumper_1x2` | 3794 | 3794a, 3794b, or the current 15573 |
  | `tile_grille_1x2` | 2412 | 2412a (without bottom groove) or 2412b (with) |
  | `technic_bush_half` | 32123 | listed as an alternate of 4265c "Technic Bush 1/2 Smooth" |

- **3 resolve to a slightly different part than the key intends:**

  | Taxonomy key | Number | BrickLink name | Closer match |
  |---|---|---|---|
  | `tile_round_2x2` | 14769 | Tile, Round 2 x 2 with Bottom Stud Holder | 4150 "Tile, Round 2 x 2" |
  | `technic_axle_2` | 32062 | Technic, Axle 2L Notched | 3704 "Technic, Axle 2L" |
  | `minifig_legs` | 970 | Hips | 970c00 "Hips and Legs Plain" |

## Sources

LEGO's own publications:

1. LEGO A/S, patent WO2019106129A1 (published 2019-06-06): 2 × 4 brick size,
   knob diameter, and the 1% compatibility tolerance.
   https://patents.google.com/patent/WO2019106129A1/en
2. LEGO Help: Comparing LEGO bricks, plates, and DUPLO bricks. Covers: three
   plates equal one brick; 2 × 1 and 2 × 4 naming and their tubes; DUPLO at
   twice the size.
   https://www.lego.com/en-us/service/help-topics/article/comparing-lego-bricks-plates-and-duplo-bricks
3. LEGO History: The stud-and-tube principle (patent filed 28 January 1958).
   https://www.lego.com/en-gb/history/articles/d-the-stud-and-tube-principle
4. LEGO History: Quality in every detail. Covers: ABS from 1963, and moulding
   to 1/200 mm.
   https://www.lego.com/en-gb/history/articles/d-quality-in-every-detail
5. LEGO Help: Tips for building with LEGO Technic elements. Covers: Technic
   lengths are in studs, and the 1:1 measurement chart.
   https://www.lego.com/en-us/service/help-topics/article/tips-for-building-with-lego-technic-elements
6. LEGO: The history of LEGO minifigures (four standard bricks tall; 1978).
   https://www.lego.com/uk-ua/categories/adults-welcome/article/history-of-lego-minifigures

LDraw (open parts library):

7. LDraw File Format Specification 1.0.2 (LDraw.org Standards Board,
   29 April 2012): LDU values and the 0.4 mm approximation.
   https://ldraw.org/article/218
8. LDraw parts library: title lines of individual part files, for example
   https://library.ldraw.org/library/official/parts/3001.dat ("Brick 2 x 4").
   - The library's legal page gives the licence as CC BY 2.0:
     https://www.ldraw.org/legal-info. Current part headers state CC BY 4.0.
   - Library conventions (orientation, file naming):
     https://ldraw.org/article/512.html

BrickLink (public catalogue):

9. BrickLink Help: Item Dimensions, Stud Dimensions and Other Standards.
   https://www.bricklink.com/help.asp?helpID=261
10. BrickLink catalogue part pages: weight, stud dimensions and package
    dimensions, one page per part, for example
    https://www.bricklink.com/v2/catalog/catalogitem.page?P=3001.
    Every part row above and in the JSON links to its own page.
11. BrickLink catalogue category listings, for example
    https://www.bricklink.com/catalogList.asp?catType=P&catString=5 (Brick).
    - Categories used: 5 Brick, 8 Brick Round, 26 Plate, 28 Plate Round,
      37 Tile, 117 Tile Round, 31 Slope, 438 Slope Curved, 43 Wheel,
      111 Tire, 113 Window, 12 Door, 6 Arch, 21 Cone, 116 Dish;
    - and the Technic categories: 133 Connector, 134 Axle, 135 Brick,
      136 Gear, 137 Liftarm, 139 Pin.
    - The category tree, with every count quoted above, is at
      https://www.bricklink.com/catalogTree.asp?itemType=P.

Fan references:

12. LUGNET FAQ: Dimensions (measured stud pitch, derived heights, 2:5 ratio).
    http://www.lugnet.com/~330/FAQ/Build/dimensions
13. brickfact.com: LEGO brick dimensions. Covers: the 0.1 mm clearance, moulded
    sizes, measured studs, and Technic hole height.
    https://brickfact.com/blog/guidebooks/lego-brick-dimensions
14. Brick Architect: Basic parts. Covers: a plate is 1/3 of a brick, and a tile
    is plate-thick with a smooth side.
    https://brickarchitect.com/parts/category-1

## Method and limits

- **How BrickLink was read.** BrickLink pages were fetched one at a time, 1.5 s
  apart. Its robots.txt allows catalogue item and list pages.
  - Values were read from each part page's weight, stud dimension and package
    dimension fields.
  - The fetched pages themselves are not in the repo.
- **Weights.** These are BrickLink catalogue values, not LEGO's. They can
  differ slightly between moulds.
- **Bounding boxes.** These are published to 0.1 mm, and many round to whole
  millimetres. Treat them as approximate.
- **Gaps.** No current LEGO-published production tolerance or dimension sheet
  was found. LEGO's figures here come from its patent text, help pages and
  history pages.
- **Scope.** The part list is representative, not exhaustive. It has 236 common
  parts across all families; BrickLink's catalogue has tens of thousands of
  entries.
