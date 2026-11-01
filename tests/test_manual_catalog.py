"""Manual catalog tests: the build list from the manual that came with the kit.

- the catalog: every build has a name, chapter and photographed page; one
  status from the three; only house-and-tree is verified; the only element
  totals are the five the pages print; no parts list anywhere;
- "What can I build?": every manual build is listed, verified first, before
  the BrickGPT designs; a build without a verified piece list gets no fit
  claim and no booklet;
- the house-and-tree booklet follows the picture on page 28;
- draft piece lists (one per diagram-readable build): unverified, within
  the kit, no fit claim until hand-checked; the hand-check tool records the
  steps while building, and a draft hand-checked with steps that place every
  piece is verified with a fit check and a booklet (house and tree's
  treatment); without them it stays unverified;
- the checklist order: the 11 closest to verified first;
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

from backend import booklet
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
CLOSEST = ["submarine", "sailing-ship", "mini-tugboat", "snappy-crab",           # the page's total matches
           "tiny-tentacles", "mini-city-car", "happy-ghost", "bake-a-cake-ephant",  # no unsure lines
           "playful-plane", "puppy-power", "rocket-shuttle"]


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

    def place_all(self, bid, skip=0):
        """Steps that place every piece of a draft, one step per line, each
        piece on its own spot (made-up positions: only the tool is under test).
        skip: leave that many pieces of the last line unplaced."""
        draft = bp.manual_drafts()[bid]
        steps = []
        for n, e in enumerate(draft["elements"], 1):
            qty = e["qty"] - (skip if n == len(draft["elements"]) else 0)
            if qty:
                spots = " ".join(f"@{4 * k},{4 * n},0" for k in range(qty))
                steps += ["--step", f"Add the {bp.line_of(e)}. :: #{n} {spots}"]
        return self.run_tool(bid, *steps)

    def sure_dolphin(self):
        return self.run_tool("dozy-dolphin", "--sure", "medium_azure 1x2 curved slope", "--sure", "#7")

    def test_done_is_refused_while_lines_are_unsure(self):
        code, _, err = self.run_tool("dozy-dolphin", "--done", "--by", "tester")
        self.assertEqual(code, 1)
        self.assertIn("still unsure", err)
        self.assertFalse(bp.manual_drafts()["dozy-dolphin"]["hand_check"]["done"])

    def test_done_needs_steps_that_place_every_piece(self):
        self.sure_dolphin()
        code, _, err = self.run_tool("dozy-dolphin", "--done", "--by", "tester")
        self.assertEqual((code, "no steps recorded yet" in err), (1, True))
        self.assertEqual(self.place_all("dozy-dolphin", skip=1)[0], 0)
        code, _, err = self.run_tool("dozy-dolphin", "--done", "--by", "tester")
        self.assertEqual(code, 1)
        self.assertIn("1× white 2x2 tile with 2 studs on edge not placed yet", err)
        self.assertEqual(self.run_tool("dozy-dolphin", "--step", "Last. :: #11 @0,60,0")[0], 0)
        code, out, _ = self.run_tool("dozy-dolphin", "--done", "--by", "tester", "--notes", "built it")
        self.assertEqual(code, 0, out)
        self.assertIn("Verified: What can I build? checks a bin for it and makes its booklet.", out)

    def test_a_hand_checked_draft_with_steps_gets_the_full_treatment(self):
        self.sure_dolphin()
        self.place_all("dozy-dolphin")
        self.assertEqual(self.run_tool("dozy-dolphin", "--done", "--by", "tester")[0], 0)
        steps = len(bp.manual_drafts()["dozy-dolphin"]["steps"])
        o = next(o for o in bp.manual_options(KIT_ITEMS) if o["id"] == "dozy-dolphin")
        self.assertEqual((o["piece_status"], o["status"], o["has_booklet"], o["set"]),
                         ("verified", "fit", True, "dozy-dolphin"))
        self.assertEqual((o["verified_by"], o["message"]), ("hand-checked against the kit", "You have all 18 pieces."))
        self.assertNotIn("draft", o)
        plan = bp.plan({"set": "dozy-dolphin"}, KIT_ITEMS)                # what POST /api/builds runs
        book = plan["booklet"]
        self.assertEqual((plan["status"], len(book["steps"]), len(book["placements"])), ("fit", steps, 18))
        self.assertEqual(book["source"], "the pieces in your bin (the manual, pages 10, 11)")
        self.assertIn("hand-checked against the kit by tester", book["notes"][1])
        self.assertEqual(sum(p["qty"] for p in book["parts"]), 18)
        no_magenta = [i for i in KIT_ITEMS if i["color"] != "magenta"]
        short = next(o for o in bp.manual_options(no_magenta) if o["id"] == "dozy-dolphin")
        self.assertEqual((short["status"], short["message"]), ("short", "Missing 2× magenta 2x2 plate."))
        self.assertNotIn("booklet", bp.plan({"set": "dozy-dolphin"}, no_magenta))   # no booklet when short
        verified = [o for o in bp.manual_options(KIT_ITEMS) if o["piece_status"] == "verified"]
        self.assertEqual([o["id"] for o in verified], ["dozy-dolphin", "house-and-tree"])  # first, in book order
        self.assertEqual([o["id"] for o in bp.manual_options(KIT_ITEMS)[:2]], ["dozy-dolphin", "house-and-tree"])
        self.assertTrue(all(o["has_booklet"] and o.get("set") for o in verified))

    def test_hand_checked_without_steps_stays_unverified(self):
        path = self.dir / "happy-ghost.json"
        d = json.loads(path.read_text())
        d.update(status="hand-checked", hand_check={"done": True, "on": "2026-11-01", "by": "x", "notes": ""})
        path.write_text(json.dumps(d))
        o = next(o for o in bp.manual_options(KIT_ITEMS) if o["id"] == "happy-ghost")
        self.assertEqual((o["status"], o["piece_status"], o["has_booklet"], o["draft"]),
                         ("unverified", "diagram-readable", False, "hand-checked, waiting for its steps"))
        self.assertNotIn("happy-ghost", bp.known_sets())
        with self.assertRaises(KeyError):
            bp.plan({"set": "happy-ghost"}, KIT_ITEMS)

    def test_steps_refuse_over_placing_and_bad_positions(self):
        bad = ["Plates. :: #3 @0,0,0 @2,0,0 @4,0,0",       # 3 magenta plates, the list has 2
               "Plates. :: #3 @0,0",                        # not x,y,z
               "Plates. :: #3 @0,0,-1",                     # below the table
               "Plates. :: #3 0,0,0",                       # no @
               "Plates. :: #99 @0,0,0",                     # no such line
               "Plates. :: #3 @0,0,0 along z",
               "Roof. :: #5 @0,0,0 down up",
               "no separator #3 @0,0,0"]
        for spec in bad:
            code, _, err = self.run_tool("dozy-dolphin", "--step", spec)
            self.assertEqual(code, 2, (spec, err))
        self.assertNotIn("steps", bp.manual_drafts()["dozy-dolphin"])
        code, _, _ = self.run_tool("dozy-dolphin", "--step",
                                   "Roof. :: black 1x2 curved slope @2,0,7 down -x @4,0,7 down +x; #2 @0,0,0 along y")
        self.assertEqual(code, 0)
        place = bp.manual_drafts()["dozy-dolphin"]["steps"][0]["place"]
        self.assertEqual(place, [{"line": "black 1x2 curved slope", "at": [2, 0, 7], "down": "+x"},
                                 {"line": "black 1x2 curved slope", "at": [4, 0, 7], "down": "+x"},
                                 {"line": "black 1x4 hinge plate", "at": [0, 0, 0], "along": "y"}])

    def test_record_types_the_steps(self):
        answers = iter(["Lay the hinge plate flat.", "#2 @0,0,0", "nonsense @1", "", "Plates on it.",
                        "#3 @0,0,1 @2,0,1", "", ""])
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = manual_check.main(["dozy-dolphin", "--record"], ask=lambda _: next(answers))
        self.assertEqual(code, 0)
        self.assertIn("no line 'nonsense'", out.getvalue())
        self.assertIn("2 steps added.", out.getvalue())
        steps = bp.manual_drafts()["dozy-dolphin"]["steps"]
        self.assertEqual([(s["text"], len(s["place"])) for s in steps], [("Lay the hinge plate flat.", 1),
                                                                         ("Plates on it.", 2)])
        _, out, _ = self.run_tool("dozy-dolphin", "--undo-step")
        self.assertEqual(len(bp.manual_drafts()["dozy-dolphin"]["steps"]), 1)
        self.run_tool("dozy-dolphin", "--clear-steps")
        self.assertEqual(bp.manual_drafts()["dozy-dolphin"]["steps"], [])

    def test_preview_writes_the_booklet_so_far(self):
        self.run_tool("dozy-dolphin", "--step", "Lay the hinge plate flat. :: #2 @0,0,0")
        page = self.dir / "preview.html"
        code, out, _ = self.run_tool("dozy-dolphin", "--preview", str(page))
        self.assertEqual(code, 0)
        html = page.read_text()
        self.assertIn("Dozy Dolphin (preview)", html)
        self.assertIn("Still to place:", html)
        self.assertIn("<svg", html)
        self.assertFalse(bp.manual_drafts()["dozy-dolphin"]["hand_check"]["done"])

    def test_set_fixes_a_count_and_undo_resets(self):
        code, out, _ = self.run_tool("happy-ghost", "--set", "white 1x2 jumper plate=2")
        self.assertEqual(code, 0)
        d = bp.manual_drafts()["happy-ghost"]
        self.assertEqual(d["elements_total"], 13)
        self.place_all("happy-ghost")
        code, _, _ = self.run_tool("happy-ghost", "--done", "--by", "tester")
        self.assertEqual(code, 0)
        self.assertTrue(bp.manual_drafts()["happy-ghost"]["hand_check"]["done"])
        self.run_tool("happy-ghost", "--undo")
        d = bp.manual_drafts()["happy-ghost"]
        self.assertEqual((d["status"], bool(d["steps"])), ("draft", True))   # back to draft, steps kept
        self.assertNotIn("happy-ghost", bp.known_sets())

    def test_listing_starts_with_the_closest(self):
        code, out, _ = self.run_tool()
        self.assertEqual(code, 0)
        first = [line.split()[1] for line in out.splitlines()[:12]]
        self.assertEqual(first[:11], CLOSEST)
        self.assertTrue(all(line.startswith("*") for line in out.splitlines()[:11]))
        self.assertFalse(out.splitlines()[11].startswith("*"))

    def test_unknown_build_and_bad_set(self):
        self.assertEqual(self.run_tool("castle")[0], 2)
        self.assertEqual(self.run_tool("happy-ghost", "--set", "nonsense")[0], 2)
        self.assertEqual(self.run_tool("happy-ghost", "--set", "gold 1x2 brick=1")[0], 2)
        self.assertEqual(self.run_tool("happy-ghost", "--sure", "#99")[0], 2)


class TestChecklistOrder(unittest.TestCase):
    def test_the_11_closest_come_first(self):
        ordered = bp.checklist_order(bp.manual_drafts())
        self.assertEqual(len(ordered), len(DRAFTS))
        self.assertEqual([d["id"] for d, _ in ordered[:11]], CLOSEST)
        self.assertEqual({why for _, why in ordered[:4]}, {bp.CLOSEST["total"]})
        self.assertEqual({why for _, why in ordered[4:11]}, {bp.CLOSEST["sure"]})
        self.assertFalse(any(why for _, why in ordered[11:]))
        for d, _ in ordered[:4]:
            self.assertEqual(d["count_check"]["page_says"], d["elements_total"])
        self.assertTrue(all(d["unsure_elements"] == 0 and "read_by" not in d for d, _ in ordered[4:11]))

    def test_the_printable_page_follows_it(self):
        ordered = bp.checklist_order(bp.manual_drafts())
        page = booklet.render_checklist([d for d, _ in ordered], first={d["id"]: w for d, w in ordered if w})
        self.assertEqual(page.count('class="start"'), 11)
        at = [page.index(f"<p class=\"note\">{bid} ·") for bid in CLOSEST]
        self.assertEqual(at, sorted(at))
        self.assertLess(at[-1], page.index('<p class="note">dozy-dolphin ·'))
        self.assertIn('<td class="n">#1</td>', page)
        self.assertIn("--record", page)


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
            self.assertEqual(page.count('class="start"'), 11)
            self.assertLess(page.index("Submarine"), page.index("Dozy Dolphin"))

    def test_a_hand_checked_draft_gets_its_booklet_through_the_api(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as drafts:
            for p in bp.DRAFTS_DIR.glob("*.json"):
                shutil.copy(p, drafts)
            path = Path(drafts) / "snappy-crab.json"
            d = json.loads(path.read_text())
            for e in d["elements"]:
                e.update(sure=True, doubt=None)
            d["steps"] = [{"text": f"Add the {bp.line_of(e)}.",
                           "place": [{"line": bp.line_of(e), "at": [2 * k, 2 * n, 0]} for k in range(e["qty"])]}
                          for n, e in enumerate(d["elements"])]
            d.update(status="hand-checked", hand_check={"done": True, "on": "2026-11-01", "by": "tester", "notes": ""})
            path.write_text(json.dumps(d))
            with mock.patch.object(bp, "DRAFTS_DIR", Path(drafts)), full_loop.server(tmp, None) as api:
                with closing(db.connect()) as conn:
                    seed(conn, KIT_ITEMS)
                status, body = api.call("GET", "/api/builds/options")
                self.assertEqual(body["manual"]["verified"], 2)
                crab = next(o for o in body["options"] if o["id"] == "snappy-crab")
                self.assertEqual((crab["status"], crab["has_booklet"], crab["set"]), ("fit", True, "snappy-crab"))
                status, build = api.call("POST", "/api/builds", json_body={"set": crab["set"]})
                self.assertEqual((status, build["status"], build["steps"]), (201, "fit", len(d["elements"])))
                status, page = api.call("GET", build["booklet_url"], raw=True)
                self.assertEqual(status, 200)
                self.assertIn("Snappy crab", page)
                self.assertIn("the manual, page 9", page)


if __name__ == "__main__":
    unittest.main()
