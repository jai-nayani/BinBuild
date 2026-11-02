"""Validator diagnostics, and validation that writes nothing.

- format: every validator failure leads with the count, then names the part
  and its exact grid position ("1 floating: Brick 2x4 @ Position(2,1,3)"):
  floating pieces, collisions, off-grid pieces, over-counts and bad stacking,
  in the Wonder validator, in Path A (its parser and its fit check), in the
  check against the book's list and in a known set's shortfall. The exact
  strings are pinned here;
- no side effects: validating and planning take a build and return a verdict
  with details. A populated database is byte-for-byte the same after every
  validator and after the read-only API calls (the build list and POST
  /api/builds/check), which never open a writable connection; with no
  database file, none is created. Only POST /api/builds, the explicit save,
  adds a row.

No Model API call. Every database is a temporary one. Standard-library
unittest. Run from the repo root:
    python3 -m unittest discover -s tests -v
"""

import hashlib
import re
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from backend import brickgpt_constraint as path_a
from backend import build_plan as bp
from backend import inventory_db as db
from backend import manual_verify as mv
from backend import wonder_design as wd
from test_full_loop import KIT_ITEMS, seed
from test_wonder import HOUSE

try:
    import uvicorn  # noqa: F401
    from backend import full_loop
    HAVE_SERVER = True
except ImportError:
    HAVE_SERVER = False

OWNED = wd.owned_from_items(KIT_ITEMS)
PLENTY = dict.fromkeys(path_a.BRICK_TYPES, 999)
NOT_HELD = ("not held by any stud to the rest of the model (floating, or only resting on a smooth top, a slope "
            "or a jumper plate)")
# count, check, then at least one part at Position(x,y,z)
PINPOINTED = re.compile(r"^\d+ (floating|collision|off-grid|over-count|under-count|bad stacking|unknown part|"
                        r"bad direction|unusable part): .+ @ Position\(-?\d+,-?\d+,-?\d+\)")


def wonder_errors(text):
    return wd.validate(text, OWNED).errors


def path_a_parse_error(text) -> str:
    try:
        path_a.parse_design(text)
    except ValueError as err:
        return str(err)
    raise AssertionError(f"parse_design accepted {text!r}")


class TestPathAFormat(unittest.TestCase):
    def test_floating_brick(self):
        result = path_a.fit_design(path_a.parse_design("2x4 (0,0,0)\n2x4 (2,1,3)\n"), PLENTY)
        self.assertIsInstance(result, path_a.Failure)
        self.assertEqual(result.details, ["1 floating: Brick 2x4 @ Position(2,1,3)"])
        self.assertEqual(result.reason, "not connected: 1 floating: Brick 2x4 @ Position(2,1,3)")
        self.assertEqual(result.problem, "floating")

    def test_floating_group_names_every_brick(self):
        result = path_a.plan_build("tower", PLENTY)
        self.assertEqual(result.details, [
            "5 floating: Brick 1x1 @ Position(1,18,0), Brick 1x2 @ Position(1,16,0), Brick 1x2 @ Position(1,17,1), "
            "Brick 1x1 @ Position(1,16,1), Brick 1x2 @ Position(1,17,2)"])

    def test_over_count_names_where_every_brick_of_the_type_is(self):
        design = path_a.parse_design("2x6 (0,0,0)\n2x6 (0,0,1)\n1x2 (0,0,2)\n")
        result = path_a.fit_design(design, path_a.load_inventory({"2x6": 1, "1x2": 5}))
        self.assertIsInstance(result, path_a.Failure)
        self.assertEqual(result.details,
                         ["1 over-count: Brick 2x6 @ Position(0,0,0), Position(0,0,1) — uses 2, owns 1"])

    def test_parser_names_every_bad_brick(self):
        self.assertEqual(path_a_parse_error("8x1 (15,0,0)\n"),
                         "1 off-grid: Brick 8x1 @ Position(15,0,0) — covers x 15-22, y 0-0, layer 0; "
                         "the grid is 0-19 each way")
        self.assertEqual(path_a_parse_error("2x2 (0,0,0)\n2x2 (1,0,0)\n"),
                         "1 collision: Brick 2x2 @ Position(1,0,0) overlaps Brick 2x2 @ Position(0,0,0) "
                         "at Position(1,0,0) — 2 cells shared")
        self.assertEqual(path_a_parse_error("2x3 (4,5,6)\n"),
                         "1 unknown part: Brick 2x3 @ Position(4,5,6) — not one of the 8 brick types "
                         "(1x1, 1x2, 1x4, 1x6, 1x8, 2x2, 2x4, 2x6)")
        # all of them at once, not just the first
        lines = path_a_parse_error("8x1 (15,0,0)\n2x2 (0,0,0)\n1x1 (1,1,0)\n").splitlines()
        self.assertEqual(lines, ["1 off-grid: Brick 8x1 @ Position(15,0,0) — covers x 15-22, y 0-0, layer 0; "
                                 "the grid is 0-19 each way",
                                 "1 collision: Brick 1x1 @ Position(1,1,0) overlaps Brick 2x2 @ Position(0,0,0) "
                                 "at Position(1,1,0)"])

    def test_the_build_list_says_where_the_loose_part_is(self):
        plan = bp.plan_design("bottle", KIT_ITEMS, with_booklet=False)
        self.assertEqual(plan["status"], "not_connected")
        self.assertIn("1 floating: Brick 1x1 @ Position(5,14,0)", plan["details"])
        self.assertIn("(1 floating: Brick 1x1 @ Position(5,14,0))", plan["message"])


class TestWonderFormat(unittest.TestCase):
    def test_floating(self):
        self.assertEqual(wonder_errors(HOUSE + "1x1 (3,0,9) round_plate lime\n"),
                         [f"1 floating: Round Plate 1x1 @ Position(3,0,9) — {NOT_HELD}"])

    def test_collision(self):
        self.assertIn("1 collision: Plate 2x1 @ Position(3,0,2) overlaps Brick 2x1 @ Position(3,0,1) "
                      "at Position(3,0,2) — 2 cells shared", wonder_errors(HOUSE + "2x1 (3,0,2) plate dark_purple\n"))

    def test_off_grid(self):
        self.assertIn("1 off-grid: Plate 1x2 @ Position(19,19,0) — covers x 19-19, y 19-20; "
                      "the base is 0-19 each way", wonder_errors(HOUSE + "1x2 (19,19,0) plate dark_purple\n"))
        self.assertIn("1 off-grid: Plate 1x2 @ Position(0,1,-1) — below the table (z starts at 0)",
                      wonder_errors(HOUSE + "1x2 (0,1,-1) plate dark_purple\n"))
        self.assertIn("1 off-grid: Brick 2x1 @ Position(0,1,58) — its top is at plate 61, "
                      "above the 60-plate limit", wonder_errors(HOUSE + "2x1 (0,1,58) brick orange\n"))

    def test_over_count(self):
        self.assertIn("1 over-count: Brick 1x2 (orange) @ Position(3,0,1), Position(3,0,4), Position(0,1,0) "
                      "— uses 3, owns 2", wonder_errors(HOUSE + "2x1 (0,1,0) brick orange\n"))
        self.assertIn("1 over-count: Plate 1x2 (red) @ Position(0,1,0) — uses 1, owns 0 "
                      "(not in the inventory at all)", wonder_errors(HOUSE + "1x2 (0,1,0) plate red\n"))

    def test_bad_stacking(self):
        self.assertEqual(wonder_errors("2x1 (0,0,1) brick orange\n"),
                         ["1 bad stacking: Brick 2x1 @ Position(0,0,1) — no piece stands on the table: "
                          "the lowest z must be 0"])
        on_jumper = "6x1 (0,0,0) plate lime\n2x1 (0,0,1) jumper_plate white\n1x1 (0,0,2) round_plate lime\n"
        self.assertIn("1 bad stacking: Round Plate 1x1 @ Position(0,0,2) — sits on Jumper Plate 2x1 "
                      "@ Position(0,0,1), whose single stud is half a stud off the grid; nothing may go on a "
                      "jumper plate",
                      wonder_errors(on_jumper))

    def test_parts_that_can_not_be_placed(self):
        self.assertEqual(wonder_errors(HOUSE + "2x4 (0,1,0) brick orange\n"),
                         ["1 unknown part: Brick 2x4 @ Position(0,1,0) — you own no brick of size 2x4; "
                          "a brick comes in 1x2"])
        self.assertEqual(wonder_errors(HOUSE.replace("down=-x", "down=+y")),
                         ["1 bad direction: Curved Slope 2x1 @ Position(2,0,7) — curved_slope 2x1 runs along x, "
                          "so its down= must be ±x"])


class TestEveryFailurePinpoints(unittest.TestCase):
    """A battery of broken designs: every error line names a count, a part
    and a Position. Only a line that can't be read at all (nothing to place)
    and an empty design have no position to give."""

    WONDER = [HOUSE + "1x1 (9,9,0) round_tile white\n1x1 (9,9,5) round_plate lime\n",
              HOUSE + "2x1 (3,0,2) plate dark_purple\n", HOUSE + "2x1 (0,1,0) brick orange\n",
              HOUSE + "1x2 (19,19,0) plate dark_purple\n", HOUSE + "1x2 (0,1,-1) plate red\n",
              "2x1 (0,0,1) brick orange\n", HOUSE + "4x1 (0,1,0) hinge_plate black\n",
              HOUSE.replace(" down=-x", ""), "1x2 (0,0,0) plate dark_purple down=+y\n",
              "6x1 (0,0,0) plate lime\n2x1 (0,0,1) jumper_plate white\n1x1 (0,0,2) round_plate lime\n",
              "4x1 (0,0,0) side_stud_brick blue\n2x1 (0,0,3) clip_plate lime clip=+x\n1x1 (2,0,3) round_plate lime\n"]
    PATH_A = ["8x1 (15,0,0)\n2x2 (0,0,0)\n1x1 (1,1,0)\n2x3 (5,5,5)\n"]

    def test_wonder_validator(self):
        for text in self.WONDER:
            errors = wonder_errors(text)
            self.assertTrue(errors, text)
            for e in errors:
                self.assertRegex(e, PINPOINTED)

    def test_path_a(self):
        for text in self.PATH_A:
            for e in path_a_parse_error(text).splitlines():
                self.assertRegex(e, PINPOINTED)
        short = path_a.load_inventory({"1x1": 10, "1x2": 10, "1x8": 1, "2x2": 2, "2x4": 2, "2x6": 2})
        for category in bp.designs():
            result = path_a.plan_build(category, short)
            self.assertIsInstance(result, path_a.Failure, category)
            self.assertTrue(result.details, category)
            for e in result.details:
                self.assertRegex(e, PINPOINTED)

    def test_unreadable_lines_give_their_line_number(self):
        self.assertEqual(wonder_errors("this is not a design\n"),
                         ["1 unreadable: line 1 'this is not a design' — can't read it; expected "
                          "'HxW (x,y,z) code color [down|studs|clip=±x|±y]'"])
        self.assertEqual(wonder_errors("# only a comment\n"), ["the design has no pieces"])


class TestListsAndSets(unittest.TestCase):
    def test_book_list(self):
        pieces = wd.parse("2x1 (0,0,0) brick orange\n2x1 (0,0,3) brick orange\n")[0]
        orange = ("brick", "brick", "1x2", "orange")
        lime = ("plate", "plate", "1x6", "lime")
        self.assertEqual(mv.list_errors(pieces, {orange: 1, lime: 1}), [
            "1 over-count: Brick 1x2 (orange) @ Position(0,0,0), Position(0,0,3) — the list has 1, the design uses 2",
            "1 under-count: Plate 1x6 (lime) — the list has 1, the design uses 0"])  # none placed: nowhere to point

    def test_known_set_shortfall(self):
        orange = ("orange", "brick", "1x2")
        items = [dict(i, quantity=i["quantity"] - 1) if (i["color"], i["shape"], i["size"]) == orange else i
                 for i in KIT_ITEMS]
        plan = bp.plan({"set": "house-and-tree"}, items, with_booklet=False)
        self.assertEqual(plan["status"], "short")
        self.assertEqual(plan["details"], ["1 over-count: Brick 1x2 (orange) @ Position(3,0,1), Position(3,0,4) "
                                           "— needs 2, owns 1"])
        self.assertEqual(bp.plan({"set": "house-and-tree"}, KIT_ITEMS, with_booklet=False)["details"], [])


def snapshot(path) -> tuple:
    """The database file's bytes, every table's row count, and every file in
    its folder (a journal or WAL file left behind would show up here)."""
    path = Path(path)
    with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as conn:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
        rows = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
    return hashlib.sha256(path.read_bytes()).hexdigest(), rows, sorted(p.name for p in path.parent.iterdir())


def no_writable_connection():
    return mock.patch.object(db, "connect", side_effect=AssertionError("validation opened a writable connection"))


class TestValidationWritesNothing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "binbuild.db"
        with closing(db.connect(self.path)) as conn:
            seed(conn, KIT_ITEMS)
        self.before = snapshot(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_validator_leaves_the_database_untouched(self):
        with mock.patch.object(db, "DB_PATH", self.path), no_writable_connection():
            with db.reading() as conn:
                items = db.inventory_summary(conn)["items"]
            self.assertEqual(len(items), len(KIT_ITEMS))
            owned = wd.owned_from_items(items)
            self.assertTrue(wd.validate(HOUSE, owned).ok)
            self.assertFalse(wd.validate(HOUSE + "1x1 (3,0,9) round_plate lime\n", owned).ok)
            self.assertIsInstance(path_a.plan_build("chair", PLENTY), path_a.Build)
            self.assertIsInstance(path_a.plan_build("tower", PLENTY), path_a.Failure)
            mv.check_design(HOUSE, owned, {("brick", "brick", "1x2", "orange"): 1})
            bp.options(items)
            for asked in ({"design": "train"}, {"design": "bottle"}, {"set": "house-and-tree"}):
                bp.plan(asked, items)
        self.assertEqual(snapshot(self.path), self.before)

    def test_reading_never_creates_a_database(self):
        missing = Path(self.tmp.name) / "nothing-here.db"
        with db.reading(missing) as conn:
            self.assertEqual(db.inventory_summary(conn)["total_pieces"], 0)
        self.assertFalse(missing.exists())

    def test_reading_can_not_write(self):
        with db.reading(self.path) as conn, self.assertRaises(sqlite3.OperationalError):
            conn.execute("DELETE FROM inventory_items")
        self.assertEqual(snapshot(self.path), self.before)


@unittest.skipUnless(HAVE_SERVER, "FastAPI or uvicorn not installed")
class TestCheckEndpoint(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "binbuild.db"
        self.ctx = full_loop.server(self.tmp.name, None)
        self.api = self.ctx.__enter__()

    def tearDown(self):
        self.ctx.__exit__(None, None, None)
        self.tmp.cleanup()

    def seed(self):
        with closing(db.connect()) as conn:   # the server's temporary database
            seed(conn, KIT_ITEMS)
        return snapshot(self.path)

    def test_check_and_the_build_list_write_nothing(self):
        before = self.seed()
        with no_writable_connection():
            status, body = self.api.call("POST", "/api/builds/check", json_body={"design": "tower"})
            self.assertEqual(status, 200, body)
            self.assertEqual((body["verdict"], body["ok"]), ("not_connected", False))
            self.assertIn("5 floating: Brick 1x1 @ Position(1,18,0), Brick 1x2 @ Position(1,16,0), "
                          "Brick 1x2 @ Position(1,17,1), Brick 1x1 @ Position(1,16,1), "
                          "Brick 1x2 @ Position(1,17,2)", body["details"])
            status, body = self.api.call("POST", "/api/builds/check", json_body={"set": "house-and-tree"})
            self.assertEqual((status, body["verdict"], body["ok"], body["details"]), (200, "fit", True, []))
            self.assertNotIn("booklet", body["plan"])
            status, _ = self.api.call("GET", "/api/builds/options")
            self.assertEqual(status, 200)
        self.assertEqual(snapshot(self.path), before)

    def test_saving_is_the_separate_explicit_call(self):
        before = self.seed()
        status, body = self.api.call("POST", "/api/builds", json_body={"set": "house-and-tree"})
        self.assertEqual(status, 201, body)
        after = snapshot(self.path)
        self.assertEqual(after[1], {**before[1], "builds": before[1]["builds"] + 1})

    def test_no_database_file_is_created(self):
        for method, path, body in (("POST", "/api/builds/check", {"design": "train"}),
                                   ("GET", "/api/builds/options", None)):
            status, reply = self.api.call(method, path, json_body=body)
            self.assertEqual(status, 200, reply)
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
