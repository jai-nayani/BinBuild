"""Tests for the inventory taxonomy.

Stdlib only. Run from the repo root:
    python3 -m unittest backend.test_inventory_taxonomy -v
"""

import json
import re
import sqlite3
import unittest

from backend.inventory_taxonomy import (
    COLORS,
    ENTRIES,
    FAMILIES,
    FAMILY_MIN_CONFIDENCE,
    GENERATOR_TYPES,
    MARKDOWN_PATH,
    SCHEMA_FIELDS,
    SPECIFIC_MIN_CONFIDENCE,
    TAXONOMY,
    Classification,
    InventoryItem,
    canonical_key,
    classification_prompt,
    generator_inventory,
    generator_key,
    lookup,
    render_markdown,
    resolve_classification,
    schema_migration,
    tally,
)

BRICKGPT_8 = {"1x1", "1x2", "1x4", "1x6", "1x8", "2x2", "2x4", "2x6"}


def reply(key, family=None, color="red", confidence=0.9):
    raw = {"taxonomy_key": key, "color": color, "confidence": confidence}
    if family is not None:
        raw["family"] = family
    return resolve_classification(raw)


class CanonicalKeyTest(unittest.TestCase):
    def test_rotated_footprints_are_the_same_key(self):
        self.assertEqual(canonical_key("brick_2x1"), canonical_key("brick_1x2"))
        self.assertEqual(canonical_key("brick_2x1"), "brick_1x2")
        self.assertEqual(canonical_key("plate_4x2"), "plate_2x4")
        self.assertEqual(canonical_key("slope_45_2x1"), "slope_45_1x2")
        self.assertEqual(canonical_key("Brick 2 x 1"), "brick_1x2")
        self.assertEqual(canonical_key("plate_10x1"), "plate_1x10")

    def test_height_is_not_swapped_into_the_footprint(self):
        self.assertEqual(canonical_key("window_4x1x3"), "window_1x4x3")
        self.assertEqual(canonical_key("brick_2x1x2"), "brick_1x2x2")

    def test_every_key_is_already_canonical(self):
        for entry in ENTRIES:
            self.assertEqual(canonical_key(entry.key), entry.key)

    def test_lookup_canonicalizes(self):
        self.assertIs(lookup("brick_2x1"), TAXONOMY["brick_1x2"])
        self.assertIs(lookup("PLATE 6 x 2"), TAXONOMY["plate_2x6"])

    def test_brickgpt_notation_maps_to_the_same_key(self):
        self.assertEqual(generator_key("2x1"), generator_key("1x2"))
        self.assertEqual(generator_key("6x2"), "brick_2x6")
        with self.assertRaises(ValueError):
            generator_key("2x3")  # a real brick, but not one of the 8


class OneFamilyPerKeyTest(unittest.TestCase):
    def test_no_key_is_listed_twice(self):
        keys = [e.key for e in ENTRIES]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(TAXONOMY), len(ENTRIES))

    def test_every_key_has_exactly_one_known_family(self):
        for entry in ENTRIES:
            self.assertIn(entry.family, FAMILIES, entry.key)
            self.assertEqual(lookup(entry.key).family, entry.family)

    def test_each_family_has_its_family_level_key(self):
        for family in FAMILIES:
            self.assertEqual(TAXONOMY[family].family, family)
            self.assertEqual(TAXONOMY[family].level, "unknown" if family == "unknown" else "family")

    def test_family_prefixes_are_unambiguous(self):
        # A key that starts like a family name belongs to that family
        # (no "plate_..." filed under brick, no "technic_..." under other).
        for entry in ENTRIES:
            for family in FAMILIES:
                if entry.key.startswith(family + "_"):
                    self.assertEqual(entry.family, family, entry.key)

    def test_no_part_number_is_claimed_by_two_keys(self):
        seen = {}
        for entry in ENTRIES:
            for part in entry.part_nums:
                self.assertNotIn(part, seen, f"{part} in {entry.key} and {seen.get(part)}")
                seen[part] = entry.key

    def test_colour_modes_and_names_are_set(self):
        for entry in ENTRIES:
            self.assertIn(entry.color_mode, ("solid", "primary"), entry.key)
            self.assertTrue(entry.name, entry.key)


class GeneratorReadyTest(unittest.TestCase):
    def test_exactly_the_8_brickgpt_types(self):
        ready = {e.key for e in ENTRIES if e.generator_ready}
        self.assertEqual(ready, {f"brick_{t}" for t in BRICKGPT_8})
        self.assertEqual(set(GENERATOR_TYPES), BRICKGPT_8)
        self.assertEqual({TAXONOMY[k].generator_type for k in ready}, BRICKGPT_8)

    def test_generator_bricks_are_plain_bricks(self):
        for entry in ENTRIES:
            if entry.generator_ready:
                self.assertEqual(entry.family, "brick")
                self.assertEqual(entry.layer, "a")
                self.assertEqual(entry.color_mode, "solid")

    def test_same_footprint_in_another_family_is_not_generator_ready(self):
        for key in ("plate_1x2", "tile_1x2", "technic_brick_1x2", "brick_1x2x2",
                    "slope_45_1x2", "brick_2x3", "brick"):
            self.assertFalse(TAXONOMY[key].generator_ready, key)
            self.assertIsNone(TAXONOMY[key].generator_type, key)


class UnknownFallbackTest(unittest.TestCase):
    def test_lookup_of_anything_unlisted_is_unknown(self):
        for key in ("brick_3x3", "2x4", "3001", "", "dragon", None, 42):
            self.assertEqual(lookup(key).key, "unknown", key)

    def test_confident_specific_key_is_kept(self):
        result = reply("brick_2x1", "brick", confidence=SPECIFIC_MIN_CONFIDENCE)
        self.assertEqual(result, Classification("brick_1x2", "brick", True, "red",
                                                 SPECIFIC_MIN_CONFIDENCE, "specific"))

    def test_low_confidence_specific_key_drops_to_its_family(self):
        result = reply("plate_2x4", "plate", confidence=0.5)
        self.assertEqual((result.taxonomy_key, result.level), ("plate", "family"))

    def test_low_confidence_family_drops_to_unknown(self):
        self.assertEqual(reply("plate", "plate", confidence=0.3).taxonomy_key, "unknown")
        self.assertEqual(reply("plate_2x4", "plate", confidence=0.1).taxonomy_key, "unknown")
        self.assertEqual(reply("plate", confidence=FAMILY_MIN_CONFIDENCE).taxonomy_key, "plate")

    def test_invented_key_falls_back_to_the_stated_family_then_unknown(self):
        self.assertEqual(reply("brick_3x3", "brick").taxonomy_key, "brick")
        self.assertEqual(reply("brick_3x3").taxonomy_key, "unknown")
        self.assertEqual(reply("3001", "brick").taxonomy_key, "brick")
        self.assertEqual(reply("brick_3x3", "not_a_family").taxonomy_key, "unknown")

    def test_contradictory_family_is_unknown(self):
        self.assertEqual(reply("brick_1x2", "plate").taxonomy_key, "unknown")

    def test_malformed_replies_are_unknown_never_an_error(self):
        for raw in (None, "not json", "[1, 2]", 7, {}, {"taxonomy_key": 5},
                    {"taxonomy_key": "brick_1x2", "confidence": "high"}):
            result = resolve_classification(raw)
            self.assertIsInstance(result, Classification)
            self.assertIn(result.taxonomy_key, ("unknown", "brick"), raw)
        self.assertEqual(resolve_classification('{"taxonomy_key": "tile_2x2", "family": "tile", '
                                                '"color": "white", "confidence": 0.9}').taxonomy_key,
                         "tile_2x2")

    def test_unlisted_colour_is_unknown(self):
        self.assertEqual(reply("brick_1x2", color="fuchsia").color, "unknown")


class NeverForceFitTest(unittest.TestCase):
    def test_nothing_is_turned_into_a_generator_type(self):
        # Bare sizes and near misses never become a generator brick.
        for key, family in (("2x4", None), ("2x4", "brick"), ("brick_2x3", "brick"),
                            ("plate_2x4", "plate"), ("technic_brick_1x2", "technic"),
                            ("brick_2x4x2", "brick"), ("brick_2x4", "plate")):
            self.assertFalse(reply(key, family).generator_ready, (key, family))

    def test_only_generator_items_reach_the_generator(self):
        items = [
            InventoryItem.of("brick_2x1", "red", 3),
            InventoryItem.of("brick_1x2", "blue", 2),
            InventoryItem.of("plate_1x2", "red", 10),
            InventoryItem.of("technic_brick_1x2", "black", 4),
            InventoryItem.of("brick_2x3", "white", 5),
            InventoryItem.of("brick", "yellow", 6),
            InventoryItem.of("unknown", "unknown", 7),
        ]
        counts = generator_inventory(items)
        self.assertEqual(set(counts), BRICKGPT_8)
        self.assertEqual(counts["1x2"], 5)
        self.assertEqual(sum(counts.values()), 5)


class PromptTest(unittest.TestCase):
    def vocabulary(self):
        prompt = classification_prompt()
        return dict(re.findall(r"^  (\S+) \| (\S+) \| .+$",
                               prompt.split("Vocabulary")[1].split("Colours:")[0], re.M))

    def test_prompt_lists_every_taxonomy_key_with_its_family(self):
        self.assertEqual(self.vocabulary(), {e.key: e.family for e in ENTRIES})

    def test_prompt_lists_every_family_and_colour(self):
        prompt = classification_prompt()
        for family in FAMILIES:
            self.assertRegex(prompt, rf"(?m)^  {family} \| ")
        for color in COLORS:
            self.assertRegex(prompt, rf"\b{color}\b")

    def test_prompt_example_reply_is_the_exact_shape_and_resolves(self):
        example = re.search(r"^   (\{.*\})$", classification_prompt(), re.M).group(1)
        raw = json.loads(example)
        self.assertEqual(set(raw), {"taxonomy_key", "family", "color", "confidence"})
        self.assertEqual(resolve_classification(raw).taxonomy_key, raw["taxonomy_key"])

    def test_prompt_names_all_8_generator_keys_in_the_force_fit_rule(self):
        rule = classification_prompt().split("2. Never force-fit")[1].split("3. ")[0]
        for size in BRICKGPT_8:
            self.assertIn(f"brick_{size}", rule)


class InventoryModelTest(unittest.TestCase):
    def test_item_takes_family_and_generator_flag_from_the_taxonomy(self):
        item = InventoryItem.of("Brick 2 x 1", "red", 4)
        self.assertEqual(item, InventoryItem("brick_1x2", "brick", True, "red", 4))
        with self.assertRaises(ValueError):
            InventoryItem.of("brick_3x3", "red", 1)
        with self.assertRaises(ValueError):
            InventoryItem.of("brick_1x2", "fuchsia", 1)
        with self.assertRaises(ValueError):
            InventoryItem.of("brick_1x2", "red", -1)

    def test_tally_groups_by_key_and_colour(self):
        results = [reply("brick_1x2", "brick", "red"), reply("brick_2x1", "brick", "red"),
                   reply("brick_1x2", "brick", "blue"), reply("plate_3x3", "plate", "red")]
        self.assertEqual(tally(results), [
            InventoryItem("brick_1x2", "brick", True, "blue", 1),
            InventoryItem("brick_1x2", "brick", True, "red", 2),
            InventoryItem("plate", "plate", False, "red", 1),
        ])

    def test_migration_adds_only_missing_columns_to_the_design_tables(self):
        db = sqlite3.connect(":memory:")
        # Stand-ins for the design doc's tables, already holding color and count.
        db.executescript("""
            CREATE TABLE batches (batch_id TEXT PRIMARY KEY);
            CREATE TABLE detections (detection_id INTEGER PRIMARY KEY, batch_id TEXT);
            CREATE TABLE inventory_items (item_id INTEGER PRIMARY KEY, color TEXT, count INTEGER);
        """)

        def columns(table):
            return {row[1] for row in db.execute(f"PRAGMA table_info({table})")}

        existing = {t: columns(t) for t in ("batches", "detections", "inventory_items")}
        statements = schema_migration(existing)
        self.assertFalse(any('"color"' in s and "inventory_items" in s for s in statements))
        for statement in statements:
            db.execute(statement)
        self.assertEqual(columns("batches"), {"batch_id"})
        self.assertEqual(columns("inventory_items"),
                         {"item_id", "taxonomy_key", "family", "generator_ready", "color", "count"})
        self.assertTrue({"taxonomy_key", "color", "confidence"} <= columns("detections"))

        again = schema_migration({t: columns(t) for t in existing})
        self.assertFalse([s for s in again if s.startswith("ALTER")])  # idempotent

        item = InventoryItem.of("brick_2x4", "red", 3)
        db.execute("INSERT INTO inventory_items (taxonomy_key, family, generator_ready, color, count) "
                   "VALUES (?, ?, ?, ?, ?)", (item.taxonomy_key, item.family, int(item.generator_ready),
                                              item.color, item.count))
        with self.assertRaises(sqlite3.IntegrityError):  # one row per key and colour
            db.execute("INSERT INTO inventory_items (taxonomy_key, color, count) VALUES ('brick_2x4', 'red', 1)")

    def test_fresh_tables_get_every_field(self):
        statements = schema_migration({})
        for table, fields in SCHEMA_FIELDS.items():
            for name, _ in fields:
                self.assertTrue(any(f'ALTER TABLE {table} ADD COLUMN "{name}"' in s for s in statements))


class MarkdownTest(unittest.TestCase):
    def test_taxonomy_md_is_generated_from_this_module(self):
        self.assertTrue(MARKDOWN_PATH.exists(), "run: python3 -m backend.inventory_taxonomy --write")
        self.assertEqual(MARKDOWN_PATH.read_text(), render_markdown(),
                         "TAXONOMY.md is stale: python3 -m backend.inventory_taxonomy --write")

    def test_markdown_has_the_rule_and_a_row_per_key(self):
        text = render_markdown()
        self.assertIn("Generation uses only the 8; everything else is inventoried, never force-fit.", text)
        for entry in ENTRIES:
            self.assertIn(f"| `{entry.key}` | {entry.family} |", text)


if __name__ == "__main__":
    unittest.main()
