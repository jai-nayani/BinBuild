"""Inventory taxonomy: every kind of piece BinBuild recognises and counts.

The rule: generation uses only the 8 BrickGPT types; everything else is
inventoried, never force-fit.

BrickGPT generates with exactly 8 trained brick types (1x1, 1x2, 1x4, 1x6,
1x8, 2x2, 2x4, 2x6). That does not change. What this module defines is the
INVENTORY: what the app names and counts from a bin. Single source of truth:
TAXONOMY.md is generated from this file (`python3 -m backend.inventory_taxonomy
--write`) and a test fails if the two drift apart.

Layers (each entry belongs to exactly one family; `layer` is derived):
  a  generator-ready bricks: exactly BrickGPT's 8 (family brick)
  b  other bricks: other sizes, round, arch, taller (family brick)
  c  plates            d  tiles             e  slopes
  f  wheels + tires    g  windows/doors     h  Technic
  i  minifigs + accessories                 j  other (plants, animals, ...)
  k  unknown

Every family also has a family-level key equal to its name ("brick", "plate",
..., "unknown") for a piece whose family is clear but whose exact type isn't.

Keys are canonical: lowercase, underscores, footprint smallest side first
(`brick_2x1` -> `brick_1x2`, `window_4x1x3` -> `window_1x4x3`; a third number
is height and stays put). `canonical_key()` normalises; `generator_key("2x1")`
maps BrickGPT's bare size notation to `brick_1x2`.

Colour is recorded per entry as `solid` (the one colour the part is moulded in)
or `primary` (dominant colour; prints, stickers and multi-colour assemblies are
not recorded), always from COLORS or "unknown".

Spark classification spec (prompt rendered by `classification_prompt()`):
  Input: one SAM region, i.e. one segmented piece cropped from a batch photo
  (pixels outside the mask greyed), plus which view it came from.
  Task: return the most specific taxonomy key when confident, else the family
  key, else "unknown". Nothing is ever force-fit into a generator type: brick_WxL
  only for a plain, one-brick-tall brick of exactly that footprint.
  Reply: JSON only, exactly
      {"taxonomy_key": "plate_2x4", "family": "plate",
       "color": "light_bluish_gray", "confidence": 0.82}
  `resolve_classification()` enforces it on our side: an invalid key, a
  family that contradicts the key, or low confidence walks down the ladder
  specific -> family -> unknown (SPECIFIC_MIN_CONFIDENCE, FAMILY_MIN_CONFIDENCE).
  It never walks up, and never turns anything into a generator type.

Inventory data model: inventory_items rows store taxonomy_key, family,
generator_ready, color, count (InventoryItem). SCHEMA_FIELDS lists the columns
this adds to the design doc's tables (batches, detections, inventory_items);
`schema_migration()` emits ALTER TABLE statements for just the missing ones.
`generator_inventory()` turns inventory items into the {"1x2": n} counts the
BrickGPT constraint layer takes, from generator-ready items only.

Stdlib only; no network, no models.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

GENERATOR_TYPES = ("1x1", "1x2", "1x4", "1x6", "1x8", "2x2", "2x4", "2x6")

# family -> (layer letter, description). The family-level key is the family name.
FAMILIES = {
    "brick": ("b", "Bricks: studs on top, one brick tall unless a height is given"),
    "plate": ("c", "Plates: one third of a brick tall, studs on top"),
    "tile": ("d", "Tiles: plate height, smooth top with no studs"),
    "slope": ("e", "Slopes: angled top; also inverted and curved slopes"),
    "wheel": ("f", "Wheels (rims), rubber tires and wheel-holder plates"),
    "window_door": ("g", "Window frames, window glass, doors and door frames"),
    "technic": ("h", "Technic: beams, pins, axles, gears, bushes, bricks with holes"),
    "minifig": ("i", "Minifigure parts, complete minifigures and their accessories"),
    "other": ("j", "Other recognisable parts: plants, flowers, animals, hinges, bars, clips, cones, dishes"),
    "unknown": ("k", "Cannot be identified"),
}
LAYERS = {
    "a": "Generator-ready bricks (BrickGPT's 8 types)",
    "b": "Bricks in other sizes and shapes",
    "c": "Plates", "d": "Tiles", "e": "Slopes", "f": "Wheels and tires",
    "g": "Windows and doors", "h": "Technic", "i": "Minifigs and accessories",
    "j": "Other", "k": "Unknown",
}

COLOR_MODES = {
    "solid": "the single colour the part is moulded in",
    "primary": "the dominant colour; prints, stickers and multi-colour assemblies are not recorded",
}

# BrickLink colour names in snake_case; "unknown" when it can't be judged.
COLORS = (
    "white", "black", "light_bluish_gray", "dark_bluish_gray", "light_gray", "dark_gray",
    "red", "dark_red", "blue", "dark_blue", "medium_blue", "dark_azure", "medium_azure",
    "sand_blue", "yellow", "bright_light_yellow", "orange", "bright_light_orange",
    "dark_orange", "green", "dark_green", "bright_green", "lime", "sand_green",
    "olive_green", "tan", "dark_tan", "reddish_brown", "dark_brown", "medium_nougat",
    "light_nougat", "bright_pink", "dark_pink", "magenta", "medium_lavender",
    "dark_purple", "pearl_gold", "flat_silver", "trans_clear", "trans_black", "trans_red",
    "trans_orange", "trans_yellow", "trans_green", "trans_bright_green",
    "trans_light_blue", "trans_dark_blue", "trans_neon_green", "unknown",
)

SPECIFIC_MIN_CONFIDENCE = 0.6  # below this a specific key drops to its family
FAMILY_MIN_CONFIDENCE = 0.4    # below this a family key drops to unknown


@dataclass(frozen=True)
class Entry:
    """One taxonomy key. part_nums are BrickLink design IDs, for reference."""

    key: str
    family: str
    name: str
    part_nums: tuple = ()
    generator_ready: bool = False
    color_mode: str = "solid"

    @property
    def generator_type(self):
        """BrickGPT's size string ("1x2") for the 8 generator bricks, else None."""
        return self.key.removeprefix("brick_") if self.generator_ready else None

    @property
    def layer(self) -> str:
        return "a" if self.generator_ready else FAMILIES[self.family][0]

    @property
    def level(self) -> str:
        if self.key == "unknown":
            return "unknown"
        return "family" if self.key == self.family else "specific"


_E = Entry
ENTRIES = (
    # (a) generator-ready: exactly BrickGPT's 8 trained types
    _E("brick_1x1", "brick", "Brick 1 x 1", ("3005",), generator_ready=True),
    _E("brick_1x2", "brick", "Brick 1 x 2", ("3004",), generator_ready=True),
    _E("brick_1x4", "brick", "Brick 1 x 4", ("3010",), generator_ready=True),
    _E("brick_1x6", "brick", "Brick 1 x 6", ("3009",), generator_ready=True),
    _E("brick_1x8", "brick", "Brick 1 x 8", ("3008",), generator_ready=True),
    _E("brick_2x2", "brick", "Brick 2 x 2", ("3003",), generator_ready=True),
    _E("brick_2x4", "brick", "Brick 2 x 4", ("3001",), generator_ready=True),
    _E("brick_2x6", "brick", "Brick 2 x 6", ("2456",), generator_ready=True),
    # (b) bricks in other sizes and shapes
    _E("brick_1x3", "brick", "Brick 1 x 3", ("3622",)),
    _E("brick_1x10", "brick", "Brick 1 x 10", ("6111",)),
    _E("brick_1x12", "brick", "Brick 1 x 12", ("6112",)),
    _E("brick_1x16", "brick", "Brick 1 x 16", ("2465",)),
    _E("brick_2x3", "brick", "Brick 2 x 3", ("3002",)),
    _E("brick_2x8", "brick", "Brick 2 x 8", ("3007",)),
    _E("brick_2x10", "brick", "Brick 2 x 10", ("3006",)),
    _E("brick_4x6", "brick", "Brick 4 x 6", ("2356",)),
    _E("brick_1x2x2", "brick", "Brick 1 x 2 x 2 (two bricks tall)", ("3245",)),
    _E("brick_1x1x3", "brick", "Brick 1 x 1 x 3 (three bricks tall)", ("14716",)),
    _E("brick_2x2x3", "brick", "Brick 2 x 2 x 3 (three bricks tall)", ("30145",)),
    _E("brick_round_1x1", "brick", "Brick, round 1 x 1", ("3062",)),
    _E("brick_round_2x2", "brick", "Brick, round 2 x 2", ("3941",)),
    _E("brick_arch_1x4", "brick", "Brick, arch 1 x 4", ("3659",)),
    _E("brick", "brick", "Brick whose size or shape can't be determined"),
    # (c) plates
    _E("plate_1x1", "plate", "Plate 1 x 1", ("3024",)),
    _E("plate_1x2", "plate", "Plate 1 x 2", ("3023",)),
    _E("plate_1x3", "plate", "Plate 1 x 3", ("3623",)),
    _E("plate_1x4", "plate", "Plate 1 x 4", ("3710",)),
    _E("plate_1x6", "plate", "Plate 1 x 6", ("3666",)),
    _E("plate_1x8", "plate", "Plate 1 x 8", ("3460",)),
    _E("plate_1x10", "plate", "Plate 1 x 10", ("4477",)),
    _E("plate_1x12", "plate", "Plate 1 x 12", ("60479",)),
    _E("plate_2x2", "plate", "Plate 2 x 2", ("3022",)),
    _E("plate_2x3", "plate", "Plate 2 x 3", ("3021",)),
    _E("plate_2x4", "plate", "Plate 2 x 4", ("3020",)),
    _E("plate_2x6", "plate", "Plate 2 x 6", ("3795",)),
    _E("plate_2x8", "plate", "Plate 2 x 8", ("3034",)),
    _E("plate_2x10", "plate", "Plate 2 x 10", ("3832",)),
    _E("plate_2x12", "plate", "Plate 2 x 12", ("2445",)),
    _E("plate_4x4", "plate", "Plate 4 x 4", ("3031",)),
    _E("plate_4x6", "plate", "Plate 4 x 6", ("3032",)),
    _E("plate_4x8", "plate", "Plate 4 x 8", ("3035",)),
    _E("plate_4x10", "plate", "Plate 4 x 10", ("3030",)),
    _E("plate_4x12", "plate", "Plate 4 x 12", ("3029",)),
    _E("plate_6x6", "plate", "Plate 6 x 6", ("3958",)),
    _E("plate_6x8", "plate", "Plate 6 x 8", ("3036",)),
    _E("plate_6x10", "plate", "Plate 6 x 10", ("3033",)),
    _E("plate_6x12", "plate", "Plate 6 x 12", ("3028",)),
    _E("plate_8x8", "plate", "Plate 8 x 8", ("41539",)),
    _E("plate_round_1x1", "plate", "Plate, round 1 x 1", ("4073", "6141")),
    _E("plate_round_2x2", "plate", "Plate, round 2 x 2 with axle hole", ("4032",)),
    _E("plate_jumper_1x2", "plate", "Plate 1 x 2 with one centre stud (jumper)", ("3794",)),
    _E("plate", "plate", "Plate whose size or shape can't be determined"),
    # (d) tiles
    _E("tile_1x1", "tile", "Tile 1 x 1", ("3070",)),
    _E("tile_1x2", "tile", "Tile 1 x 2", ("3069",)),
    _E("tile_1x3", "tile", "Tile 1 x 3", ("63864",)),
    _E("tile_1x4", "tile", "Tile 1 x 4", ("2431",)),
    _E("tile_1x6", "tile", "Tile 1 x 6", ("6636",)),
    _E("tile_1x8", "tile", "Tile 1 x 8", ("4162",)),
    _E("tile_2x2", "tile", "Tile 2 x 2", ("3068",)),
    _E("tile_2x3", "tile", "Tile 2 x 3", ("26603",)),
    _E("tile_2x4", "tile", "Tile 2 x 4", ("87079",)),
    _E("tile_2x6", "tile", "Tile 2 x 6", ("69729",)),
    _E("tile_round_1x1", "tile", "Tile, round 1 x 1", ("98138",)),
    _E("tile_round_2x2", "tile", "Tile, round 2 x 2", ("14769",)),
    _E("tile_grille_1x2", "tile", "Tile 1 x 2 with grille", ("2412",)),
    _E("tile", "tile", "Tile whose size or shape can't be determined"),
    # (e) slopes
    _E("slope_45_1x2", "slope", "Slope 45 degrees, 2 x 1", ("3040",)),
    _E("slope_45_2x2", "slope", "Slope 45 degrees, 2 x 2", ("3039",)),
    _E("slope_45_2x3", "slope", "Slope 45 degrees, 2 x 3", ("3038",)),
    _E("slope_45_2x4", "slope", "Slope 45 degrees, 2 x 4", ("3037",)),
    _E("slope_33_1x3", "slope", "Slope 33 degrees, 3 x 1", ("4286",)),
    _E("slope_33_2x3", "slope", "Slope 33 degrees, 3 x 2", ("3298",)),
    _E("slope_33_3x4", "slope", "Slope 33 degrees, 3 x 4", ("3297",)),
    _E("slope_30_1x1", "slope", "Slope 30 degrees, 1 x 1 x 2/3 (cheese slope)", ("54200",)),
    _E("slope_18_1x4", "slope", "Slope 18 degrees, 4 x 1", ("60477",)),
    _E("slope_inverted_45_1x2", "slope", "Slope, inverted 45 degrees, 2 x 1", ("3665",)),
    _E("slope_inverted_45_2x2", "slope", "Slope, inverted 45 degrees, 2 x 2", ("3660",)),
    _E("slope_curved_1x2", "slope", "Slope, curved 2 x 1", ("11477",)),
    _E("slope_curved_1x4", "slope", "Slope, curved 4 x 1", ("61678",)),
    _E("slope_curved_2x2", "slope", "Slope, curved 2 x 2", ("15068",)),
    _E("slope", "slope", "Slope whose size or angle can't be determined"),
    # (f) wheels + tires (sizes by outside diameter, in studs: 1 stud = 8 mm)
    _E("wheel_small", "wheel", "Wheel rim, small: under 2 studs across"),
    _E("wheel_medium", "wheel", "Wheel rim, medium: 2 to 4 studs across"),
    _E("wheel_large", "wheel", "Wheel rim, large: over 4 studs across"),
    _E("tire_small", "wheel", "Rubber tire, small: under 2 studs across"),
    _E("tire_medium", "wheel", "Rubber tire, medium: 2 to 4 studs across"),
    _E("tire_large", "wheel", "Rubber tire, large: over 4 studs across"),
    _E("wheel_holder_plate", "wheel", "Plate 2 x 2 with wheel holders", ("4600",)),
    _E("wheel", "wheel", "Wheel, tire or wheel part that can't be told apart"),
    # (g) windows / doors
    _E("window_1x2x2", "window_door", "Window frame 1 x 2 x 2", ("60592",)),
    _E("window_1x2x3", "window_door", "Window frame 1 x 2 x 3", ("60593",)),
    _E("window_1x4x3", "window_door", "Window frame 1 x 4 x 3", ("60594",)),
    _E("window_glass", "window_door", "Glass pane for a window frame", ("60601", "60602", "60603")),
    _E("door_frame_1x4x6", "window_door", "Door frame 1 x 4 x 6", ("60596",)),
    _E("door_1x4x6", "window_door", "Door 1 x 4 x 6 (the door itself)", ("60616",)),
    _E("window_door", "window_door", "Window or door part that can't be told apart"),
    # (h) Technic
    _E("technic_beam_3", "technic", "Technic beam (thick liftarm), 3 holes", ("32523",)),
    _E("technic_beam_5", "technic", "Technic beam (thick liftarm), 5 holes", ("32316",)),
    _E("technic_beam_7", "technic", "Technic beam (thick liftarm), 7 holes", ("32524",)),
    _E("technic_beam_9", "technic", "Technic beam (thick liftarm), 9 holes", ("40490",)),
    _E("technic_beam_11", "technic", "Technic beam (thick liftarm), 11 holes", ("32525",)),
    _E("technic_beam_13", "technic", "Technic beam (thick liftarm), 13 holes", ("41239",)),
    _E("technic_beam_15", "technic", "Technic beam (thick liftarm), 15 holes", ("32278",)),
    _E("technic_beam_bent", "technic", "Technic beam, bent or L-shaped", ("32140", "32526", "32348")),
    _E("technic_pin", "technic", "Technic pin, 2 long (with or without friction)", ("2780", "3673")),
    _E("technic_pin_long", "technic", "Technic pin, 3 long", ("6558",)),
    _E("technic_pin_axle", "technic", "Technic pin with an axle end", ("43093",)),
    _E("technic_axle_2", "technic", "Technic axle, 2 long", ("32062",)),
    _E("technic_axle_3", "technic", "Technic axle, 3 long", ("4519",)),
    _E("technic_axle_4", "technic", "Technic axle, 4 long", ("3705",)),
    _E("technic_axle_5", "technic", "Technic axle, 5 long", ("32073",)),
    _E("technic_axle_6", "technic", "Technic axle, 6 long", ("3706",)),
    _E("technic_axle_7", "technic", "Technic axle, 7 long", ("44294",)),
    _E("technic_axle_8", "technic", "Technic axle, 8 long", ("3707",)),
    _E("technic_gear_8", "technic", "Technic gear, 8 teeth", ("3647", "10928")),
    _E("technic_gear_12_bevel", "technic", "Technic gear, 12 teeth, double bevel", ("32270",)),
    _E("technic_gear_16", "technic", "Technic gear, 16 teeth", ("4019", "94925")),
    _E("technic_gear_20_bevel", "technic", "Technic gear, 20 teeth, double bevel", ("32269",)),
    _E("technic_gear_24", "technic", "Technic gear, 24 teeth", ("3648",)),
    _E("technic_gear_36_bevel", "technic", "Technic gear, 36 teeth, double bevel", ("32498",)),
    _E("technic_gear_40", "technic", "Technic gear, 40 teeth", ("3649",)),
    _E("technic_bush", "technic", "Technic bush (axle stopper)", ("3713",)),
    _E("technic_bush_half", "technic", "Technic half bush", ("32123",)),
    _E("technic_brick_1x2", "technic", "Technic brick 1 x 2 with hole", ("3700",)),
    _E("technic_brick_1x4", "technic", "Technic brick 1 x 4 with holes", ("3701",)),
    _E("technic_brick_1x6", "technic", "Technic brick 1 x 6 with holes", ("3894",)),
    _E("technic_brick_1x8", "technic", "Technic brick 1 x 8 with holes", ("3702",)),
    _E("technic", "technic", "Technic part that can't be told apart"),
    # (i) minifigs + accessories
    _E("minifig_head", "minifig", "Minifigure head", ("3626",), color_mode="primary"),
    _E("minifig_torso", "minifig", "Minifigure torso (with or without arms)", ("973",), color_mode="primary"),
    _E("minifig_legs", "minifig", "Minifigure legs (with hips)", ("970",), color_mode="primary"),
    _E("minifig_hair", "minifig", "Minifigure hair piece", color_mode="primary"),
    _E("minifig_headgear", "minifig", "Minifigure hat, helmet or cap", color_mode="primary"),
    _E("minifig_complete", "minifig", "Assembled minifigure (counts as one piece)", color_mode="primary"),
    _E("minifig_accessory", "minifig", "Minifigure accessory: tool, weapon, cup, etc.", color_mode="primary"),
    _E("minifig", "minifig", "Minifigure part that can't be told apart", color_mode="primary"),
    # (j) other
    _E("flower", "other", "Flower or flower plate", color_mode="primary"),
    _E("plant_leaves", "other", "Plant leaves", ("2417", "2423"), color_mode="primary"),
    _E("plant_stem", "other", "Plant stem", color_mode="primary"),
    _E("animal", "other", "Animal figure or animal part", color_mode="primary"),
    _E("hinge", "other", "Hinge part (brick or plate hinge)", color_mode="primary"),
    _E("bar", "other", "Bar, or a part with a bar", color_mode="primary"),
    _E("clip", "other", "Clip, or a part with a clip", color_mode="primary"),
    _E("cone_1x1", "other", "Cone 1 x 1", ("4589",)),
    _E("dish", "other", "Dish (radar dish)", ("4740", "3960")),
    _E("other", "other", "Recognisable non-brick part not listed above", color_mode="primary"),
    # (k) unknown
    _E("unknown", "unknown", "Cannot be identified", color_mode="primary"),
)

_DIMS = re.compile(r"(\d+)\s*[x×]\s*(\d+)")


def canonical_key(raw: str) -> str:
    """'Brick 2 x 1' -> 'brick_1x2'. Footprint smallest side first; height stays."""
    text = raw.strip().lower()
    text = _DIMS.sub(lambda m: "x".join(sorted(m.groups(), key=int)), text, count=1)
    return re.sub(r"[\s\-]+", "_", text)


def _index(entries) -> dict:
    """Key -> Entry, refusing anything ambiguous."""
    index = {}
    for entry in entries:
        if entry.key in index:
            raise ValueError(f"duplicate taxonomy key {entry.key!r}")
        if entry.key != canonical_key(entry.key):
            raise ValueError(f"{entry.key!r} is not canonical ({canonical_key(entry.key)!r})")
        if entry.family not in FAMILIES or entry.color_mode not in COLOR_MODES:
            raise ValueError(f"{entry.key!r}: bad family or colour mode")
        index[entry.key] = entry
    missing = [f for f in FAMILIES if index.get(f, Entry("", "", "")).family != f]
    generator = sorted(e.generator_type for e in index.values() if e.generator_ready)
    if missing or generator != sorted(GENERATOR_TYPES):
        raise ValueError(f"family keys missing {missing} or generator set {generator} is not the 8")
    return index


TAXONOMY = _index(ENTRIES)


def lookup(key) -> Entry:
    """The entry for a key; anything not in the taxonomy is 'unknown'."""
    if not isinstance(key, str):
        return TAXONOMY["unknown"]
    return TAXONOMY.get(canonical_key(key), TAXONOMY["unknown"])


def generator_key(size: str) -> str:
    """BrickGPT size notation ('2x1') -> taxonomy key ('brick_1x2'); only the 8."""
    key = canonical_key(f"brick_{size}")
    if key not in TAXONOMY or not TAXONOMY[key].generator_ready:
        raise ValueError(f"{size!r} is not one of BrickGPT's 8 brick types")
    return key


# --- classification ---------------------------------------------------------

@dataclass(frozen=True)
class Classification:
    """A classifier reply after validation: always a real taxonomy key."""

    taxonomy_key: str
    family: str
    generator_ready: bool
    color: str
    confidence: float
    level: str  # specific | family | unknown


def _result(entry: Entry, color: str, confidence: float) -> Classification:
    return Classification(entry.key, entry.family, entry.generator_ready, color, confidence, entry.level)


def resolve_classification(raw) -> Classification:
    """Validate one classifier reply (dict or JSON text) and apply the fallback ladder.

    specific key -> its family key -> unknown, by confidence; an invalid key falls
    back to a valid `family`, and a key whose family contradicts `family` goes to
    unknown. Never raises, never moves up the ladder, never invents a generator type.
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = None
    if not isinstance(raw, dict):
        return _result(TAXONOMY["unknown"], "unknown", 0.0)
    color = raw.get("color") if raw.get("color") in COLORS else "unknown"
    try:
        confidence = min(max(float(raw.get("confidence")), 0.0), 1.0)
    except (TypeError, ValueError):
        confidence = 0.0
    key = raw.get("taxonomy_key")
    key = canonical_key(key) if isinstance(key, str) else None
    family = raw.get("family") if raw.get("family") in FAMILIES else None

    entry = TAXONOMY.get(key)
    if entry is None:
        entry = TAXONOMY[family] if family else TAXONOMY["unknown"]
    elif family and family != entry.family:
        entry = TAXONOMY["unknown"]  # contradictory answer: trust neither half
    if entry.level == "specific" and confidence < SPECIFIC_MIN_CONFIDENCE:
        entry = TAXONOMY[entry.family]
    if entry.level == "family" and confidence < FAMILY_MIN_CONFIDENCE:
        entry = TAXONOMY["unknown"]
    return _result(entry, color, confidence)


def classification_prompt() -> str:
    """The prompt sent to Spark with each SAM region. Lists every taxonomy key."""
    families = "\n".join(f"  {name} | {desc}" for name, (_, desc) in FAMILIES.items())
    vocabulary = "\n".join(f"  {e.key} | {e.family} | {e.name}" for e in ENTRIES)
    example = json.dumps({"taxonomy_key": "plate_2x4", "family": "plate",
                          "color": "light_bluish_gray", "confidence": 0.82})
    return f"""\
You identify ONE LEGO piece. The image is one SAM region: a single segmented
piece cropped from a photo of loose pieces on a table, with everything outside
the piece's mask greyed out. You are also told which view the photo was taken
from (top, front, right, back or left).

Answer with the most specific taxonomy key you are confident about. If you can
tell what kind of piece it is but not its exact type or size, answer with the
family key. If you can't tell what it is, answer "unknown".

Rules:
1. taxonomy_key must be copied exactly from the vocabulary below. Never invent
   a key, never answer with a part number or a bare size like "2x4".
2. Never force-fit a piece into brick_1x1, brick_1x2, brick_1x4, brick_1x6,
   brick_1x8, brick_2x2, brick_2x4 or brick_2x6. Use one of those only for a
   plain brick exactly one brick tall with exactly that footprint: studs on top,
   no slope, no holes, no studs on the sides. A plate (one third of a brick tall)
   is plate_*, a smooth-topped piece is tile_*, a brick with holes is technic_*,
   a taller brick is its own key, and a brick of a size not listed is "brick".
3. Sizes are counted in studs and written smallest side first: a 2 x 1 plate
   is plate_1x2. If studs are hidden or cut off and you can't count them, use
   the family key.
4. family must be the family listed for your taxonomy_key.
5. color must be one value from the colour list. For printed or multi-colour
   parts give the dominant colour. Use "unknown" if the lighting makes it
   impossible to tell.
6. confidence is your probability, from 0 to 1, that taxonomy_key is right.
7. Reply with JSON only, exactly this shape and nothing else:
   {example}

Families (family | what belongs in it):
{families}

Vocabulary (taxonomy_key | family | what it is):
{vocabulary}

Colours:
  {", ".join(COLORS)}
"""


# --- inventory data model ---------------------------------------------------

# Columns this taxonomy adds to the backend design's tables (batches, detections,
# inventory_items). The rest of each table is the design doc's; nothing is redesigned.
SCHEMA_FIELDS = {
    "detections": (  # what the classifier said about one SAM region
        ("taxonomy_key", "TEXT NOT NULL DEFAULT 'unknown'"),
        ("color", "TEXT NOT NULL DEFAULT 'unknown'"),
        ("confidence", "REAL"),
    ),
    "inventory_items": (  # confirmed pieces, one row per taxonomy key and colour
        ("taxonomy_key", "TEXT NOT NULL DEFAULT 'unknown'"),
        ("family", "TEXT NOT NULL DEFAULT 'unknown'"),
        ("generator_ready", "INTEGER NOT NULL DEFAULT 0 CHECK (generator_ready IN (0, 1))"),
        ("color", "TEXT NOT NULL DEFAULT 'unknown'"),
        ("count", "INTEGER NOT NULL DEFAULT 0 CHECK (count >= 0)"),
    ),
}
SCHEMA_INDEXES = (
    "CREATE UNIQUE INDEX IF NOT EXISTS inventory_items_key_color "
    "ON inventory_items (taxonomy_key, color)",
)


def schema_migration(existing_columns: dict) -> list:
    """ALTER TABLE statements adding only the taxonomy columns a table lacks.

    existing_columns: {table: set of column names already there}. Columns the
    design doc already defines (e.g. a `color` or `count`) are left alone.
    """
    statements = []
    for table, fields in SCHEMA_FIELDS.items():
        have = existing_columns.get(table, set())
        statements += [f'ALTER TABLE {table} ADD COLUMN "{name}" {decl}'
                       for name, decl in fields if name not in have]
    return statements + list(SCHEMA_INDEXES)


@dataclass(frozen=True)
class InventoryItem:
    """One inventory_items row. family and generator_ready come from the taxonomy."""

    taxonomy_key: str
    family: str
    generator_ready: bool
    color: str
    count: int

    @classmethod
    def of(cls, key: str, color: str, count: int) -> "InventoryItem":
        entry = TAXONOMY.get(canonical_key(key))
        if entry is None:
            raise ValueError(f"{key!r} is not a taxonomy key (use 'unknown')")
        if color not in COLORS:
            raise ValueError(f"{color!r} is not a known colour (use 'unknown')")
        if not isinstance(count, int) or count < 0:
            raise ValueError(f"bad count {count!r}")
        return cls(entry.key, entry.family, entry.generator_ready, color, count)


def tally(classifications) -> list:
    """Confirmed classifications -> inventory items, one per (key, colour)."""
    counts = Counter((c.taxonomy_key, c.color) for c in classifications)
    return [InventoryItem.of(key, color, n) for (key, color), n in sorted(counts.items())]


def generator_inventory(items) -> dict:
    """{"1x2": n, ...} for the BrickGPT constraint layer, from generator-ready items only."""
    counts = dict.fromkeys(GENERATOR_TYPES, 0)
    for item in items:
        entry = TAXONOMY[item.taxonomy_key]
        if entry.generator_ready:
            counts[entry.generator_type] += item.count
    return counts


# --- TAXONOMY.md --------------------------------------------------------------

def render_markdown() -> str:
    """TAXONOMY.md, generated from the data above."""
    by_layer = {}
    for e in ENTRIES:
        by_layer.setdefault(e.layer, []).append(e)
    lines = [
        "# BinBuild inventory taxonomy",
        "",
        "<!-- Generated by `python3 -m backend.inventory_taxonomy --write` from",
        "     backend/inventory_taxonomy.py. Do not edit by hand. -->",
        "",
        "**Generation uses only the 8; everything else is inventoried, never force-fit.**",
        "",
        f"- {len(ENTRIES)} taxonomy keys in {len(FAMILIES)} families; exactly "
        f"{sum(e.generator_ready for e in ENTRIES)} are generator-ready "
        f"(BrickGPT's {', '.join(GENERATOR_TYPES)}).",
        "- Each key belongs to exactly one family. Every family also has a "
        "family-level key equal to its name, for a piece whose family is clear "
        "but whose exact type isn't.",
        "- Keys are canonical: footprint smallest side first (`brick_2x1` is "
        "`brick_1x2`); a third number is height.",
        "- Colour is recorded from the colour list below, as `solid` (the one "
        "colour the part is moulded in) or `primary` (dominant colour; prints and "
        "multi-colour assemblies are not recorded).",
        "- Part numbers are BrickLink design IDs, given as a reference for "
        "identification. They were written from knowledge and have not been "
        "checked against a parts catalogue.",
        "",
        "## Families",
        "",
        "| Family (= family key) | Layer | What belongs in it |",
        "|---|---|---|",
    ]
    lines += [f"| `{name}` | {layer} | {desc} |" for name, (layer, desc) in FAMILIES.items()]
    lines += ["", "## Taxonomy", ""]
    for layer, title in LAYERS.items():
        lines += [f"### ({layer}) {title}", "",
                  "| Key | Family | Generator-ready | Colour | Name | Part numbers |",
                  "|---|---|---|---|---|---|"]
        lines += [f"| `{e.key}` | {e.family} | {'yes (' + e.generator_type + ')' if e.generator_ready else 'no'} "
                  f"| {e.color_mode} | {e.name} | {', '.join(e.part_nums) or '-'} |"
                  for e in by_layer[layer]]
        lines.append("")
    lines += [
        "## Colours",
        "",
        ", ".join(f"`{c}`" for c in COLORS),
        "",
        "## Spark classification spec",
        "",
        "One call per SAM region. Spark gets the region's crop and the prompt "
        "below, and must reply with JSON only:",
        "",
        "```json",
        '{"taxonomy_key": "plate_2x4", "family": "plate", "color": "light_bluish_gray", "confidence": 0.82}',
        "```",
        "",
        "`resolve_classification()` validates every reply and walks down the "
        "fallback ladder, never up:",
        "",
        "| Reply | Recorded as |",
        "|---|---|",
        f"| valid specific key, confidence >= {SPECIFIC_MIN_CONFIDENCE} | that key |",
        f"| valid specific key, confidence < {SPECIFIC_MIN_CONFIDENCE} | its family key |",
        f"| family key, confidence >= {FAMILY_MIN_CONFIDENCE} | the family key |",
        f"| family key, confidence < {FAMILY_MIN_CONFIDENCE} | `unknown` |",
        "| key not in the taxonomy (e.g. `brick_3x3`, `2x4`, a part number) | the reply's `family` if valid, else `unknown` |",
        "| key whose family contradicts the reply's `family` | `unknown` |",
        "| not JSON, or not an object | `unknown` |",
        "| colour not in the list | colour `unknown` |",
        "",
        "Nothing is ever force-fit into a generator type: only a reply naming one "
        "of the 8 generator keys, with enough confidence, counts toward generation.",
        "",
        "### Prompt",
        "",
        "```text",
        classification_prompt().rstrip("\n"),
        "```",
        "",
        "## Inventory data model",
        "",
        "`inventory_items` rows store `taxonomy_key`, `family`, `generator_ready`, "
        "`color` and `count` (`InventoryItem`); `family` and `generator_ready` "
        "always come from the taxonomy, never from the caller. The columns are "
        "added to the design doc's tables (`batches`, `detections`, "
        "`inventory_items`) without changing anything else; "
        "`schema_migration()` adds only the columns a table doesn't already have.",
        "",
        "| Table | Added column | SQL |",
        "|---|---|---|",
    ]
    lines += [f"| `{table}` | `{name}` | `{decl}` |"
              for table, fields in SCHEMA_FIELDS.items() for name, decl in fields]
    lines += [f"| `inventory_items` | (index) | `{SCHEMA_INDEXES[0]}` |", "",
              "`generator_inventory()` sums generator-ready items into the "
              '`{"1x2": n, ...}` counts the BrickGPT constraint layer takes. '
              "Every other item stays in the inventory and is never counted toward "
              "generation.", ""]
    return "\n".join(lines)


MARKDOWN_PATH = Path(__file__).resolve().parent.parent / "TAXONOMY.md"

if __name__ == "__main__":
    if sys.argv[1:] == ["--write"]:
        MARKDOWN_PATH.write_text(render_markdown())
        print(f"wrote {MARKDOWN_PATH}")
    else:
        print(render_markdown(), end="")
