"""Manual catalog tests: the build list from the manual that came with the kit.

- the catalog: every build has a name, chapter and photographed page; one
  status from the three; only house-and-tree is verified; the only element
  totals are the five the pages print; no parts list anywhere;
- "What can I build?": every manual build is listed, verified first, before
  the BrickGPT designs; a build without a verified piece list gets no fit
  claim and no booklet;
- the house-and-tree booklet follows the picture on page 28;
- the API: the manual summary, the catalog, and the verified build's booklet.

Standard-library unittest. Run from the repo root:
    python3 -m unittest discover -s tests -v
"""

import json
import unittest
from collections import Counter
from contextlib import closing
from pathlib import Path

from backend import build_plan as bp
from backend import inventory_db as db

try:
    import tempfile
    import uvicorn  # noqa: F401
    from backend import full_loop
    from test_full_loop import KIT_ITEMS, seed
    HAVE_SERVER = True
except ImportError:
    HAVE_SERVER = False
    from test_full_loop import KIT_ITEMS

CATALOG = json.loads((Path(__file__).resolve().parent.parent / "backend" / "manual" / "catalog.json").read_text())
BUILDS = CATALOG["builds"]
STATUSES = {"verified", "diagram-readable", "not-yet-piece-verified"}
PARTS_KEYS = {"parts", "elements", "pieces", "piece_list", "parts_list", "bricks"}


class TestCatalog(unittest.TestCase):
    def test_every_build_has_a_name_chapter_and_photographed_page(self):
        chapters = {c["n"]: c for c in CATALOG["chapters"]}
        self.assertEqual(sorted(chapters), [1, 2, 3, 4])
        self.assertEqual(len({b["id"] for b in BUILDS}), len(BUILDS))
        for b in BUILDS:
            self.assertTrue(b["name"].strip(), b["id"])
            first, last = chapters[b["chapter"]]["pages"]
            self.assertTrue(b["pages"], b["id"])
            for page in b["pages"]:
                self.assertTrue(8 <= page <= 96, (b["id"], page))       # pages 1-7 were not photographed
                self.assertNotIn(page, (34, 35), b["id"])                # missing from the photos
            self.assertTrue(first <= b["pages"][0] <= last, b["id"])     # its own chapter
            self.assertIn(b["status"], STATUSES, b["id"])

    def test_counts(self):
        self.assertEqual(len(BUILDS), 106)
        self.assertEqual(Counter(b["status"] for b in BUILDS),
                         {"verified": 1, "diagram-readable": 18, "not-yet-piece-verified": 87})

    def test_only_house_and_tree_is_verified_and_its_set_matches(self):
        verified = [b for b in BUILDS if b["status"] == "verified"]
        self.assertEqual([b["id"] for b in verified], ["house-and-tree"])
        spec = bp.known_sets()[verified[0]["set"]]
        pieces = sum(len(step["place"]) for step in spec["steps"])
        self.assertEqual(pieces, verified[0]["stated_elements"])  # 7, as printed on page 28
        self.assertEqual(spec["manual"]["page"], 28)

    def test_only_the_printed_totals(self):
        stated = {b["id"]: b["stated_elements"] for b in BUILDS if "stated_elements" in b}
        self.assertEqual(stated, {"submarine": 15, "sailing-ship": 8, "mini-tugboat": 10, "snappy-crab": 9,
                                  "house-and-tree": 7})

    def test_no_parts_list_anywhere(self):
        for b in BUILDS:
            self.assertFalse(PARTS_KEYS & set(b), f"{b['id']} carries a parts list")
        self.assertFalse(PARTS_KEYS & set(CATALOG))


class TestWhatCanIBuild(unittest.TestCase):
    def setUp(self):
        self.found = bp.options(KIT_ITEMS)
        self.manual = [o for o in self.found if o["kind"] == "manual"]

    def test_every_manual_build_is_listed_before_brickgpt(self):
        self.assertEqual({o["id"] for o in self.manual}, {b["id"] for b in BUILDS})
        kinds = [o["kind"] for o in self.found]
        self.assertEqual(kinds, ["manual"] * len(BUILDS) + ["brickgpt"] * len(bp.designs()))
        self.assertEqual((self.found[0]["id"], self.found[0]["status"]), ("house-and-tree", "fit"))
        # after the verified build, the rest in book order
        pages = [o["pages"][0] for o in self.manual[1:]]
        self.assertEqual(pages, sorted(pages))

    def test_unverified_builds_get_no_fit_claim_or_booklet(self):
        for o in self.manual[1:]:
            self.assertEqual(o["status"], "unverified", o["id"])
            self.assertNotIn("booklet", o)
            self.assertNotIn("missing", o)
            self.assertNotIn("set", o)
            self.assertFalse(PARTS_KEYS & set(o), o["id"])
            self.assertIn("aren't verified yet", o["message"])
            self.assertTrue(o["where"].startswith("page"))
        sub = next(o for o in self.manual if o["id"] == "submarine")
        self.assertIn("uses 15 elements; which ones isn't listed", sub["message"])

    def test_the_verified_build_is_checked_against_the_bin(self):
        short = bp.options([i for i in KIT_ITEMS if i["color"] != "orange"])[0]
        self.assertEqual((short["id"], short["status"]), ("house-and-tree", "short"))
        self.assertEqual(short["message"], "Missing 2× orange 1x2 brick.")


class TestHouseAndTreeBooklet(unittest.TestCase):
    def test_follows_the_picture_on_page_28(self):
        book = bp.plan_set("house-and-tree", KIT_ITEMS)["booklet"]
        at = {}
        for p in book["placements"]:
            at.setdefault(f"{p['part']['color']} {p['part']['shape']}", []).append(tuple(p["at"]))
        self.assertEqual(at["orange brick"], [(3, 0, 1), (3, 0, 4)])              # stacked
        self.assertEqual(sorted(at["black curved slope"]), [(2, 0, 7), (4, 0, 7)])  # overhanging both sides
        self.assertEqual(at["light_bluish_gray round brick"], [(1, 0, 1)])         # second stud
        self.assertEqual(at["lime round plate"], [(1, 0, 4)])
        self.assertIn("manual, page 28", book["source"])


@unittest.skipUnless(HAVE_SERVER, "FastAPI, uvicorn or Pillow not installed")
class TestManualApi(unittest.TestCase):
    def test_options_manual_and_booklet(self):
        with tempfile.TemporaryDirectory() as tmp, full_loop.server(tmp, None) as api:
            with closing(db.connect()) as conn:
                seed(conn, KIT_ITEMS)
            status, body = api.call("GET", "/api/builds/options")
            self.assertEqual(status, 200)
            self.assertEqual({k: body["manual"][k] for k in ("builds", "verified", "diagram_readable",
                                                            "not_yet_piece_verified")},
                             {"builds": 106, "verified": 1, "diagram_readable": 18, "not_yet_piece_verified": 87})
            self.assertEqual(sum(o["kind"] == "manual" for o in body["options"]), 106)
            first = body["options"][0]
            status, build = api.call("POST", "/api/builds", json_body={"set": first["set"]})
            self.assertEqual((status, build["status"], build["steps"]), (201, "fit", 5))
            status, page = api.call("GET", build["booklet_url"], raw=True)
            self.assertIn("House and tree", page)
            status, catalog = api.call("GET", "/api/manual")
            self.assertEqual((status, len(catalog["builds"])), (200, 106))


if __name__ == "__main__":
    unittest.main()
