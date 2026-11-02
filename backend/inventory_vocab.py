"""Inventory vocabulary: the words the inventory stores for a piece.

The names line up with the taxonomy on branch spike/inventory-taxonomy (the
8 generator types, the broad families, BrickLink colour names in snake_case),
so the two can be joined later. That branch is a reference only; nothing here
imports it.

Two entry points:
- normalize_* are lenient. They map what a model writes ("Lime green",
  "2 x 1", "plates") onto the vocabulary and fall back to "unknown".
- check_* are strict. They reject anything outside the vocabulary, for
  corrections a person sends from the review screen.
"""

import re

# BrickGPT's brick library: the only types that feed generation.
GENERATOR_TYPES = ("1x1", "1x2", "1x4", "1x6", "1x8", "2x2", "2x4", "2x6")

FAMILIES = (
    "brick", "plate", "tile", "slope", "wheel", "window_door", "technic",
    "minifig", "other", "unknown",
)

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

_FAMILY_SYNONYMS = {
    "bricks": "brick", "plates": "plate", "tiles": "tile", "slopes": "slope",
    "curved_slope": "slope", "wedge": "slope", "wheels": "wheel", "tire": "wheel",
    "tyre": "wheel", "window": "window_door", "door": "window_door",
    "minifigure": "minifig", "minifig_part": "minifig",
}
# Everyday names a model may use instead of the BrickLink one. Only
# unambiguous ones: plain "grey" or "blue-green" stays unknown.
_COLOR_SYNONYMS = {
    "lime_green": "lime", "light_grey": "light_bluish_gray", "light_gray_bluish": "light_bluish_gray",
    "dark_grey": "dark_bluish_gray", "purple": "dark_purple", "violet": "dark_purple",
    "lavender": "medium_lavender", "pink": "bright_pink", "hot_pink": "magenta",
    "azure": "medium_azure", "light_blue": "medium_azure", "clear": "trans_clear",
    "transparent": "trans_clear", "transparent_clear": "trans_clear",
    "trans_clear_white": "trans_clear", "bright_orange": "orange",
}
_DIMS = re.compile(r"(\d+)\s*[x×]\s*(\d+)")


def _snake(raw) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(raw or "").strip().lower()).strip("_")


def normalize_family(raw) -> str:
    key = _snake(raw)
    key = _FAMILY_SYNONYMS.get(key, key)
    return key if key in FAMILIES else "unknown"


def normalize_color(raw) -> str:
    key = _snake(raw)
    key = _COLOR_SYNONYMS.get(key, key)
    if key not in COLORS:
        key = key.replace("grey", "gray")
        key = _COLOR_SYNONYMS.get(key, key)
    return key if key in COLORS else "unknown"


def normalize_size(raw):
    """'2 x 1', '1×2', '1x2x1' -> '1x2' (smaller side first); None if no WxL."""
    match = _DIMS.search(str(raw or ""))
    if not match:
        return None
    a, b = sorted((int(match.group(1)), int(match.group(2))))
    return f"{a}x{b}" if a > 0 else None


def generator_type(family: str, size, plain: bool):
    """The BrickGPT type for a plain, standard-height brick of one of the 8
    sizes; None for everything else (plates, modified or round bricks, ...)."""
    if family == "brick" and plain and size in GENERATOR_TYPES:
        return size
    return None


def check_family(value: str) -> str:
    if value not in FAMILIES:
        raise ValueError(f"family must be one of {', '.join(FAMILIES)}; got {value!r}")
    return value


def check_color(value: str) -> str:
    if value not in COLORS:
        raise ValueError(f"color must be a BrickLink colour name in snake_case or 'unknown'; got {value!r}")
    return value


def check_size(value):
    if value in (None, ""):
        return None
    size = normalize_size(value)
    if size is None or not re.fullmatch(r"\s*\d+\s*[x×]\s*\d+\s*", str(value)):
        raise ValueError(f"size must look like '1x2' (studs); got {value!r}")
    return size
