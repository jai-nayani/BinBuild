"""Manual catalog tests: the build list from the manual that came with the kit.

- the catalog: every build has a name, chapter and photographed page; one
  status from the three; only house-and-tree is verified; the only element
  totals are the five the pages print; no parts list anywhere;
- "What can I build?": every manual build is listed, verified first, before
  the BrickGPT designs; a build without a verified piece list gets no fit
  claim and no booklet;
- the house-and-tree booklet follows the picture on page 28;
- draft piece lists (one per diagram-readable build): unverified, within
  the kit, no fit claim until hand-checked; a hand-checked draft gets a fit
  check but no booklet; the hand-check tool;
- the API: the manual summary, the catalog, the checklist, and the verified
  build's booklet.

Standard-library unittest. Run from the repo root:
    python3 -m unittest discover -s tests -v
"""

import io
import json
import shutil
import tempfile
import unittest
from collections import Counter
from contextlib import closing, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from backend import build_plan as bp
from backend import inventory_db as db
from backend import inventory_vocab as vocab
from backend import manual_check

try:
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


DRAFTS = bp.manual_drafts()


def kit_key(e):
    return e["family"], e["shape"], e["size"], e["color"]


BY_ID = {b["id"]: b for b in BUILDS}
HAND = {i: d for i, d in DRAFTS.items() if d.get("read_by") != "muse-wonder-1.0"}
WONDER = {i: d for i, d in DRAFTS.items() if d.get("read_by") == "muse-wonder-1.0"}


class TestDrafts(unittest.TestCase):
    def test_the_18_hand_drafts_are_the_diagram_readable_builds(self):
        readable = {b["id"] for b in BUILDS if b["status"] == "diagram-readable"}
        self.assertEqual(set(HAND), readable)
        self.assertEqual(len(HAND), 18)

    def test_wonder_drafts_are_for_unlisted_fixed_models_only(self):
        for bid, d in WONDER.items():
            b = BY_ID[bid]
            self.assertEqual(b["status"], "not-yet-piece-verified", bid)   # the catalog still says so
            self.assertNotEqual(b["kind"], "activity", bid)               # pure activities have no draft
            self.assertIn("Read by Muse Wonder", d["warning"])
            if "stated_elements" in b:
                self.assertEqual(d["count_check"]["page_says"], b["stated_elements"])
                self.assertEqual(d["count_check"]["list_total"], d["elements_total"])
        self.assertFalse(any(b["kind"] == "activity" for b in BUILDS if b["id"] in DRAFTS))

    def test_drafts_are_unverified_and_say_so(self):
        for d in DRAFTS.values():
            self.assertEqual(d["status"], "draft", d["id"])
            self.assertFalse(d["hand_check"]["done"], d["id"])
            self.assertIn("not checked against the kit", d["warning"])
            self.assertRegex(d["read_from"], r"photos? IMG_")

    def test_totals_and_vocabulary(self):
        for d in DRAFTS.values():
            self.assertEqual(d["elements_total"], sum(e["qty"] for e in d["elements"]), d["id"])
            self.assertEqual(d["unsure_elements"], sum(e["qty"] for e in d["elements"] if not e["sure"]), d["id"])
            for e in d["elements"]:
                self.assertIn(e["family"], vocab.FAMILIES)
                self.assertIn(e["color"], vocab.COLORS)
                self.assertTrue(e["sure"] or e["doubt"], (d["id"], e))

    def test_no_draft_needs_more_than_the_kit_has(self):
        kit = {kit_key(i): i["quantity"] for i in KIT_ITEMS}
        for d in DRAFTS.values():
            need = Counter()
            for e in d["elements"]:
                need[kit_key(e)] += e["qty"]
            for key, n in need.items():
                self.assertLessEqual(n, kit.get(key, 0), (d["id"], key))

    def test_waiting_drafts_get_no_fit_claim(self):
        manual = {o["id"]: o for o in bp.manual_options(KIT_ITEMS)}
        for bid in DRAFTS:
            o = manual[bid]
            self.assertEqual((o["status"], o["piece_status"], o["draft"]),
                             ("unverified", BY_ID[bid]["status"], "waiting for a hand-check"))
            self.assertFalse(PARTS_KEYS & set(o))
            self.assertNotIn("missing", o)
            self.assertIn("waiting for a hand-check", o["message"])
        self.assertFalse(any("draft" in o for bid, o in manual.items() if bid not in DRAFTS))


class TestHandCheck(unittest.TestCase):
    """The hand-check tool on copies of the drafts (the repo's files are untouched)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        for p in bp.DRAFTS_DIR.glob("*.json"):
            shutil.copy(p, self.dir)
        self.patches = [mock.patch.object(bp, "DRAFTS_DIR", self.dir), mock.patch.object(manual_check, "DRAFTS_DIR", self.dir)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def run_tool(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = manual_check.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_done_is_refused_while_lines_are_unsure(self):
        code, _, err = self.run_tool("dozy-dolphin", "--done", "--by", "tester")
        self.assertEqual(code, 1)
        self.assertIn("still unsure", err)
        self.assertFalse(bp.manual_drafts()["dozy-dolphin"]["hand_check"]["done"])

    def test_hand_checked_draft_gets_a_fit_check_but_no_booklet(self):
        code, out, _ = self.run_tool("dozy-dolphin", "--sure", "medium_azure 1x2 curved slope",
                                     "--sure", "medium_blue 1x1 1x1 slope (cheese)", "--done", "--by", "tester",
                                     "--notes", "built it")
        self.assertEqual(code, 0, out)
        self.assertIn("HAND-CHECKED", out)
        o = next(o for o in bp.manual_options(KIT_ITEMS) if o["id"] == "dozy-dolphin")
        self.assertEqual((o["piece_status"], o["status"], o["has_booklet"]), ("verified", "fit", False))
        self.assertEqual(o["verified_by"], "hand-checked against the kit")
        self.assertIn("Build it from the book: pages 10, 11.", o["message"])
        no_magenta = [i for i in KIT_ITEMS if i["color"] != "magenta"]
        short = next(o for o in bp.manual_options(no_magenta) if o["id"] == "dozy-dolphin")
        self.assertEqual(short["status"], "short")
        self.assertIn("Missing 2× magenta 2x2 plate.", short["message"])
        # the verified list still gets no booklet, and "What can I build?" shows no booklet button for it
        self.assertNotIn("set", o)

    def test_set_fixes_a_count_and_undo_resets(self):
        code, out, _ = self.run_tool("happy-ghost", "--set", "white 1x2 jumper plate=2")
        self.assertEqual(code, 0)
        d = bp.manual_drafts()["happy-ghost"]
        self.assertEqual(d["elements_total"], 13)
        code, _, _ = self.run_tool("happy-ghost", "--done", "--by", "tester")
        self.assertTrue(bp.manual_drafts()["happy-ghost"]["hand_check"]["done"])
        self.run_tool("happy-ghost", "--undo")
        self.assertEqual(bp.manual_drafts()["happy-ghost"]["status"], "draft")

    def test_unknown_build_and_bad_set(self):
        self.assertEqual(self.run_tool("castle")[0], 2)
        self.assertEqual(self.run_tool("happy-ghost", "--set", "nonsense")[0], 2)
        self.assertEqual(self.run_tool("happy-ghost", "--set", "gold 1x2 brick=1")[0], 2)


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
            self.assertEqual((body["manual"]["drafts_waiting"], body["manual"]["hand_checked"]), (len(DRAFTS), 0))
            status, page = api.call("GET", "/api/manual/checklist", raw=True)
            self.assertEqual(status, 200)
            self.assertEqual(page.count('class="card draft"'), len(DRAFTS))
            self.assertIn("Dozy Dolphin", page)


if __name__ == "__main__":
    unittest.main()
