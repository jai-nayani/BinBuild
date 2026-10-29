"""Tests for the BrickGPT inventory constraint layer (spike, Path A).

Stdlib only. Run from the repo root:
    python3 -m unittest backend.test_brickgpt_constraint -v
"""

import unittest
from dataclasses import fields

from backend.brickgpt_constraint import (
    BRICK_TYPES,
    DEFAULT_SAMPLES,
    KIT_DIR,
    MAX_PATCH_ATTEMPTS,
    MAX_SAMPLES,
    MIN_SAMPLES,
    Build,
    Failure,
    canonical,
    count_bricks,
    fit_design,
    generate,
    is_connected,
    load_inventory,
    parse_design,
    plan_build,
    short_studs,
    shortfall,
    tilings,
)

FITS = load_inventory(KIT_DIR / "test-inventory-fits.json")
NEAR_MISS = load_inventory(KIT_DIR / "test-inventory-near-miss.json")
SHORT = load_inventory(KIT_DIR / "test-inventory-short.json")
INVENTORIES = {"fits": FITS, "near-miss": NEAR_MISS, "short": SHORT}
DESIGN_SIZES = {
    "bed": 65, "bench": 58, "bottle": 160, "bus": 74, "car": 115,
    "chair": 86, "sofa": 88, "table": 89, "tower": 68, "train": 37,
}
PLENTY = dict.fromkeys(BRICK_TYPES, 999)


def footprint(design):
    return sorted((x, y, b.z) for b in design for x, y in b.cells())


class KitDataTest(unittest.TestCase):
    """The provided kit matches its stated counts (checked, not adjusted)."""

    def test_design_sizes_match_the_brief(self):
        for category, size in DESIGN_SIZES.items():
            self.assertEqual(len(generate(category)), size, category)

    def test_fits_inventory_is_exactly_the_chair(self):
        chair = count_bricks(generate("chair"))
        self.assertEqual({t: n for t, n in FITS.items() if n}, chair)

    def test_short_inventory_has_27_bricks(self):
        self.assertEqual(sum(SHORT.values()), 27)


class CanonicalizationTest(unittest.TestCase):
    def test_rotated_sizes_are_the_same_brick(self):
        self.assertEqual(canonical("2x1"), "1x2")
        self.assertEqual(canonical("6x2"), "2x6")
        self.assertEqual(canonical("8x1"), "1x8")
        self.assertEqual(canonical("1x2"), "1x2")

    def test_rotated_bricks_count_together(self):
        design = parse_design("1x2 (0,0,0)\n2x1 (0,0,1)\n")
        self.assertEqual(count_bricks(design), {"1x2": 2})

    def test_inventory_keys_are_canonicalized(self):
        inventory = load_inventory({"2x1": 3, "1x2": 1, "6x2": 2})
        self.assertEqual(inventory["1x2"], 4)
        self.assertEqual(inventory["2x6"], 2)

    def test_rotated_brick_is_covered_by_canonical_stock(self):
        design = parse_design("2x1 (0,0,0)\n")
        self.assertEqual(shortfall(design, load_inventory({"1x2": 1})), {})

    def test_sizes_outside_the_universe_are_rejected(self):
        with self.assertRaises(ValueError):
            canonical("3x3")
        with self.assertRaises(ValueError):
            parse_design("2x3 (0,0,0)\n")

    def test_overlapping_or_out_of_grid_bricks_are_rejected(self):
        with self.assertRaises(ValueError):
            parse_design("2x2 (0,0,0)\n1x1 (1,1,0)\n")
        with self.assertRaises(ValueError):
            parse_design("8x1 (15,0,0)\n")  # 8 along x from 15 runs past 19


class ConnectivityTest(unittest.TestCase):
    def test_stacked_bricks_are_connected(self):
        self.assertTrue(is_connected(parse_design("2x4 (0,0,0)\n2x2 (1,2,1)\n")))

    def test_side_by_side_on_one_layer_is_not_connected(self):
        self.assertFalse(is_connected(parse_design("1x2 (0,0,0)\n1x2 (1,0,0)\n")))

    def test_floating_brick_is_not_connected(self):
        self.assertFalse(is_connected(parse_design("2x2 (0,0,0)\n2x2 (5,5,3)\n")))

    def test_bottle_and_tower_have_separate_parts(self):
        # Data finding: a lone 1x1 beside the bottle, a 5-brick stack beside the tower.
        self.assertFalse(is_connected(generate("bottle")))
        self.assertFalse(is_connected(generate("tower")))
        for category in ("bed", "bench", "bus", "car", "chair", "sofa", "table", "train"):
            self.assertTrue(is_connected(generate(category)), category)


class TilingsTest(unittest.TestCase):
    def test_2x6_with_only_1x2s_takes_six_pieces(self):
        found = tilings(2, 6, {"1x2": 10})
        self.assertTrue(found)
        for tiling in found:
            self.assertEqual(len(tiling), 6)
            cells = [(ox + i, oy + j) for dh, dw, ox, oy in tiling
                     for i in range(dh) for j in range(dw)]
            self.assertEqual(sorted(cells), [(i, j) for i in range(2) for j in range(6)])

    def test_fewest_pieces_first(self):
        # 2x6 = 12 studs: 2x4 + 2x2, or 2x4 + two 1x2s (2x4 + one 1x2 is only 10).
        self.assertEqual(len(tilings(2, 6, {"2x4": 1, "2x2": 1, "1x2": 6})[0]), 2)
        self.assertEqual(len(tilings(2, 6, {"2x4": 1, "1x2": 6})[0]), 3)

    def test_only_uses_what_is_available(self):
        self.assertEqual(tilings(2, 6, {"1x2": 5}), [])
        self.assertEqual(tilings(1, 1, PLENTY), [])  # nothing smaller than a 1x1


class PipelineTest(unittest.TestCase):
    def test_fits_case(self):
        result = plan_build("chair", FITS)
        self.assertIsInstance(result, Build)
        self.assertEqual(result.status, "fit")
        self.assertEqual(result.design, generate("chair"))
        self.assertEqual(result.attempts, 0)

    def test_near_miss_patch_case(self):
        result = plan_build("chair", NEAR_MISS)
        self.assertIsInstance(result, Build, getattr(result, "reason", ""))
        self.assertEqual(result.status, "patched")
        self.assertEqual(shortfall(result.design, NEAR_MISS), {})
        self.assertTrue(is_connected(result.design))
        self.assertEqual(footprint(result.design), footprint(generate("chair")))
        self.assertLessEqual(result.attempts, MAX_PATCH_ATTEMPTS)
        self.assertNotIn("1x6", result.counts_after)
        self.assertLessEqual(result.counts_after["2x6"], 6)

    def test_short_failure_case_names_the_shortfall(self):
        result = plan_build("chair", SHORT)
        self.assertIsInstance(result, Failure)
        self.assertEqual(result.shortfall, {
            "1x1": 20, "1x2": 20, "1x6": 1, "1x8": 4, "2x2": 4, "2x4": 3, "2x6": 7,
        })

    def test_short_inventory_fails_every_design(self):
        for category in DESIGN_SIZES:
            result = plan_build(category, SHORT)
            self.assertIsInstance(result, Failure, category)
            self.assertTrue(result.shortfall, category)

    def test_generate_seam_accepts_another_generator(self):
        result = plan_build("chair", PLENTY, generate=lambda c: parse_design("2x2 (0,0,0)\n"))
        self.assertIsInstance(result, Build)


class Draws:
    """A stand-in generate(): hands out kit designs in order, counting calls.

    Once the list runs out it keeps returning the last design.
    """

    def __init__(self, *categories):
        self.designs = [generate(c) for c in categories]
        self.calls = 0

    def __call__(self, category):
        design = self.designs[min(self.calls, len(self.designs) - 1)]
        self.calls += 1
        return design


class SamplingTest(unittest.TestCase):
    def test_first_sample_that_fits_returns_immediately(self):
        draws = Draws("chair", "bed", "bus")
        result = plan_build("chair", FITS, generate=draws)
        self.assertIsInstance(result, Build)
        self.assertEqual(result.status, "fit")
        self.assertEqual(result.design, generate("chair"))
        self.assertEqual(draws.calls, 1)

    def test_later_sample_that_patches_is_returned(self):
        draws = Draws("bed", "bus", "chair", "train")
        result = plan_build("chair", NEAR_MISS, generate=draws)
        self.assertIsInstance(result, Build, getattr(result, "reason", ""))
        self.assertEqual(result.status, "patched")
        self.assertEqual(draws.calls, 3)  # bed and bus fail, the chair patches
        self.assertEqual(shortfall(result.design, NEAR_MISS), {})
        self.assertTrue(is_connected(result.design))
        self.assertEqual(footprint(result.design), footprint(generate("chair")))

    def test_all_samples_fail_returns_smallest_shortfall(self):
        order = ("bed", "bench", "car", "bus")
        singles = {c: fit_design(generate(c), NEAR_MISS, "chair") for c in order}
        for single in singles.values():
            self.assertIsInstance(single, Failure)
        # bench is short 108 studs; bed, car and bus are short 300+.
        best = min(singles, key=lambda c: short_studs(singles[c].shortfall))
        self.assertEqual(best, "bench")

        result = plan_build("chair", NEAR_MISS, generate=Draws(*order), samples=4)
        self.assertIsInstance(result, Failure)
        self.assertEqual(result.shortfall, singles["bench"].shortfall)
        self.assertEqual(result.still_short, singles["bench"].still_short)
        self.assertEqual(result.attempts, singles["bench"].attempts)
        self.assertEqual(result.tried, singles["bench"].tried)  # its own attempt log
        self.assertEqual(result.attempts, MAX_PATCH_ATTEMPTS)
        self.assertFalse(hasattr(result, "design"))

    def test_sample_count_is_respected(self):
        for n in range(MIN_SAMPLES, MAX_SAMPLES + 1):
            draws = Draws("bed")  # fails under SHORT every time
            self.assertIsInstance(plan_build("bed", SHORT, generate=draws, samples=n), Failure)
            self.assertEqual(draws.calls, n)
        draws = Draws("bed")
        plan_build("bed", SHORT, generate=draws)
        self.assertEqual(draws.calls, DEFAULT_SAMPLES)

    def test_sample_count_outside_the_range_is_rejected(self):
        for n in (MIN_SAMPLES - 1, MAX_SAMPLES + 1):
            draws = Draws("chair")
            with self.assertRaises(ValueError):
                plan_build("chair", FITS, generate=draws, samples=n)
            self.assertEqual(draws.calls, 0)


class NeverReturnRejectedDesignTest(unittest.TestCase):
    def test_failure_cannot_carry_a_design(self):
        self.assertNotIn("design", {f.name for f in fields(Failure)})

    def test_every_matrix_result_is_buildable_or_a_failure(self):
        for name, inventory in INVENTORIES.items():
            for category in DESIGN_SIZES:
                result = plan_build(category, inventory)
                label = f"{name}/{category}"
                if isinstance(result, Build):
                    self.assertEqual(shortfall(result.design, inventory), {}, label)
                    self.assertTrue(is_connected(result.design), label)
                else:
                    self.assertIsInstance(result, Failure, label)
                    self.assertTrue(result.reason, label)
                    self.assertFalse(hasattr(result, "design"), label)

    def test_capped_patch_fails_instead_of_returning_half_a_patch(self):
        result = plan_build("chair", NEAR_MISS, max_attempts=2)
        self.assertIsInstance(result, Failure)
        self.assertEqual(result.attempts, 2)
        self.assertTrue(result.still_short)
        self.assertIn("cap", result.reason)

    def test_disconnected_design_fails_even_when_counts_fit(self):
        result = plan_build("tower", PLENTY)
        self.assertIsInstance(result, Failure)
        self.assertIn("not connected", result.reason)

    def test_floating_brick_from_generator_fails(self):
        floating = parse_design("2x2 (0,0,0)\n2x2 (5,5,3)\n")
        self.assertIsInstance(fit_design(floating, PLENTY), Failure)


if __name__ == "__main__":
    unittest.main()
