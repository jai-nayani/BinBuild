"""Second-read tests: Wonder verifies its own drafts, and draws the steps of the ones that agree.

- the second read is independent: the first read's prompt and photos in a new
  conversation, nothing of the first list;
- comparing two lists line by line (kind and count);
- reads that agree verify the draft (a bin check, out of the hand-check
  queue); reads that differ keep it in the queue, closest first as before,
  with the differences on its checklist card and in the hand-check tool;
- steps for a verified list: the existing validator plus "exactly the list",
  then a separate look comparing the design's drawing with the page; at most
  5 retries with the problems of either; "Cannot" stops; a list with the
  hinge plate gets no call; the passing design's layers become steps, and its
  booklet comes through the house-and-tree path (a known set, POST /api/builds);
  no valid design leaves it verified without a booklet, saying why;
- hand-checked drafts are never changed.

No Model API call. Standard-library unittest; run from the repo root:
    python3 -m unittest discover -s tests -v
"""

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from backend import booklet as bk
from backend import build_plan as bp
from backend import manual_check
from backend import manual_transcribe as mt
from backend import manual_verify as mv
from backend import wonder_design as wd
from backend.wonder_client import WonderReply
from test_full_loop import KIT_ITEMS

try:
    from PIL import Image  # noqa: F401  (the kit's inventory is read through the pipeline)
    HAVE_PILLOW = True
except ImportError:
    HAVE_PILLOW = False

OWNED = mt.kit_owned() if HAVE_PILLOW else {}
BUILDS = {b["id"]: b for b in bp.manual_catalog()["builds"]}
SHIP = BUILDS["sailing-ship"]

LIST = [(1, "plate", "medium_azure", "2x4"), (2, "brick", "orange", "1x2"), (1, "round_plate", "lime", "1x1")]
DESIGN = """```design
4x2 (0,0,0) plate medium_azure
2x1 (0,0,1) brick orange
2x1 (2,1,1) brick orange
1x1 (0,0,4) round_plate lime
```"""
FLOATING = DESIGN.replace("1x1 (0,0,4)", "1x1 (6,6,4)")
SAME = {"same": True, "differences": []}
OTHER = {"same": False, "differences": ["the mast is on the stern, the book has it in the middle"]}


def element(qty, code, color, size, sure=True):
    return {"qty": qty, "code": code, "color": color, "size": size, "sure": sure, "doubt": "" if sure else "hidden",
            "as_seen": "x"}


def read_reply(rows, build="sailing-ship"):
    return {"build": build, "fixed_model": True, "reason": "", "seen": "a ship on page 9",
            "elements": [element(*r) for r in rows], "total": sum(r[0] for r in rows), "count_note": ""}


def draft_lines(rows):
    out = []
    for qty, code, color, size in rows:
        family, shape = mt.codes()[code]
        out.append({"qty": qty, "family": family, "shape": shape, "size": size, "color": color, "sure": True,
                    "doubt": None, "as_read": "x"})
    return out


class Fake:
    """Wonder replaced by written replies; keeps what it was sent."""

    def __init__(self, replies):
        self.replies, self.sent, self.requests = list(replies), [], 0

    def respond(self, text, instructions=None, previous_id=None, images=()):
        self.sent.append({"text": text, "instructions": instructions, "previous_id": previous_id,
                          "images": len(images)})
        self.requests += 1
        r = self.replies[len(self.sent) - 1]
        return WonderReply(f"r{len(self.sent)}", r if isinstance(r, str) else json.dumps(r), "completed",
                           {"input_tokens": 5000, "output_tokens": 4000}, 60.0)


class TestCompare(unittest.TestCase):
    def test_line_by_line(self):
        first = draft_lines(LIST)
        self.assertEqual(mv.differences(first, draft_lines(list(reversed(LIST)))), [])
        second = draft_lines([(1, "plate", "medium_azure", "2x4"), (3, "brick", "orange", "1x2"),
                              (1, "cheese_slope", "medium_blue", "1x1")])
        self.assertEqual(mv.differences(first, second), [
            "orange 1x2 brick: first read 2, second read 3",
            "lime 1x1 round plate: first read 1, second read 0",
            "medium_blue 1x1 1x1 slope (cheese): first read 0, second read 1"])


class Drafts(unittest.TestCase):
    """A copy of the drafts; sailing-ship's replaced by a small known list."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        for p in bp.DRAFTS_DIR.glob("*.json"):
            shutil.copy(p, self.dir)
        self.patches = [mock.patch.object(bp, "DRAFTS_DIR", self.dir),
                        mock.patch.object(manual_check, "DRAFTS_DIR", self.dir),
                        mock.patch.object(mt, "photo_jpeg", return_value=b"jpeg"),
                        mock.patch.object(mv, "drawings", return_value=[b"drawing", b"turned"])]
        for p in self.patches:
            p.start()
        for d in bp.manual_drafts().values():  # start from no second reads at all
            for k in ("second_read", "auto_steps", "steps"):
                d.pop(k, None)
            d["status"] = "draft"
            self.write(d)
        self.ship = dict(bp.manual_drafts()["sailing-ship"], elements=draft_lines(LIST), unsure_elements=0,
                         elements_total=4)
        self.write(self.ship)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def write(self, d):
        (self.dir / f"{d['id']}.json").write_text(json.dumps(d))

    def run_one(self, replies):
        fake = Fake(replies)
        record = mv.verify_one(SHIP, bp.manual_drafts()["sailing-ship"], fake, OWNED, log=lambda *_: None)
        return fake, record, bp.manual_drafts()["sailing-ship"]

    def option(self):
        return next(o for o in bp.manual_options(KIT_ITEMS) if o["id"] == "sailing-ship")


@unittest.skipUnless(HAVE_PILLOW, "Pillow not installed")
class TestSecondRead(Drafts):
    def test_independent_of_the_first_list(self):
        fake, _, _ = self.run_one([read_reply(LIST), DESIGN, SAME])
        first = fake.sent[0]
        self.assertEqual((first["text"], first["instructions"], first["previous_id"], first["images"]),
                         (mt.request_text(SHIP), mt.instructions(OWNED), None, 1))
        for e in self.ship["elements"]:
            self.assertNotIn(bp.line_of(e), first["text"])

    def test_agreeing_reads_verify_and_leave_the_queue(self):
        fake, record, d = self.run_one([read_reply(list(reversed(LIST))), DESIGN, SAME])
        self.assertTrue(record["agrees"])
        self.assertEqual((d["status"], d["second_read"]["agrees"], d["second_read"]["differences"]),
                         ("verified", True, []))
        self.assertTrue(bp.reads_agree(d) and bp.verified(d) and not bp.hand_checked(d))
        self.assertNotIn("sailing-ship", [x["id"] for x, _ in bp.checklist_order(bp.manual_drafts())])
        o = self.option()
        self.assertEqual((o["piece_status"], o["verified_by"], o["status"], o["has_booklet"]),
                         ("verified", "two independent reads agree", "fit", True))

    def test_differing_reads_stay_in_the_queue_with_the_differences(self):
        fake, record, d = self.run_one([read_reply([(1, "plate", "medium_azure", "2x4"), (1, "brick", "orange", "1x2"),
                                                    (1, "round_plate", "lime", "1x1")])])
        self.assertEqual(len(fake.sent), 1, "no steps for a list that isn't verified")
        self.assertFalse(record["agrees"])
        self.assertEqual(d["second_read"]["differences"], ["orange 1x2 brick: first read 2, second read 1"])
        self.assertEqual((d["status"], "steps" in d), ("draft", False))
        o = self.option()
        self.assertEqual((o["piece_status"], o["status"], o["has_booklet"]), ("not-yet-piece-verified", "unverified", False))
        queue = [x["id"] for x, _ in bp.checklist_order(bp.manual_drafts())]
        self.assertIn("sailing-ship", queue[:4])        # still first: its total matched the page
        page = bk.render_checklist([x for x, _ in bp.checklist_order(bp.manual_drafts())])
        self.assertIn("A second read of the page disagrees", page)
        self.assertIn("orange 1x2 brick: first read 2, second read 1", page)
        out = io.StringIO()
        with redirect_stdout(out):
            manual_check.main([])
        self.assertIn("second read differs on 1 line", out.getvalue())
        out = io.StringIO()
        with redirect_stdout(out):
            manual_check.main(["sailing-ship"])
        self.assertIn("disagrees; check these first", out.getvalue())

    def test_no_list_from_the_second_read_is_a_disagreement(self):
        _, record, d = self.run_one([{"build": "sailing-ship", "fixed_model": False, "reason": "too small",
                                      "elements": []}])
        self.assertFalse(record["agrees"])
        self.assertIn("the second read gave no list", d["second_read"]["differences"][0])

    def test_the_queue_is_only_what_disagrees_in_the_old_order(self):
        agree = {"submarine", "tiny-tentacles", "dozy-dolphin"}
        for d in bp.manual_drafts().values():
            d["second_read"] = {"agrees": d["id"] in agree, "differences": [] if d["id"] in agree else ["x"],
                                "on": "2026-11-01"}
            self.write(d)
        ordered = bp.checklist_order(bp.manual_drafts())
        ids = [d["id"] for d, _ in ordered]
        self.assertEqual(len(ids), 100 - len(agree))
        self.assertFalse(agree & set(ids))
        self.assertEqual(ids[:9], ["sailing-ship", "mini-tugboat", "snappy-crab",              # totals match
                                   "mini-city-car", "happy-ghost", "bake-a-cake-ephant",     # no unsure lines
                                   "playful-plane", "puppy-power", "rocket-shuttle"])
        self.assertEqual([why for _, why in ordered[:9]], [bp.CLOSEST["total"]] * 3 + [bp.CLOSEST["sure"]] * 6)
        self.assertIsNone(ordered[9][1])


@unittest.skipUnless(HAVE_PILLOW, "Pillow not installed")
class TestSteps(Drafts):
    def test_a_valid_design_becomes_the_booklet_through_the_set_path(self):
        fake, record, d = self.run_one([read_reply(LIST), DESIGN, SAME])
        self.assertEqual(len(fake.sent), 3)
        place, looks = fake.sent[1], fake.sent[2]
        self.assertIsNone(place["previous_id"], "a new conversation")
        self.assertEqual(place["images"], 1)
        self.assertIn("2× orange 1x2 brick", place["text"])     # the verified list, now that it is verified
        self.assertEqual((looks["previous_id"], looks["images"], looks["instructions"]),
                         (None, 3, mv.compare_instructions()))   # its own conversation: the page + 2 drawings
        self.assertNotIn("```", looks["text"])
        self.assertTrue(record["booklet"])
        self.assertEqual((d["auto_steps"]["ok"], d["auto_steps"]["tries"], d["auto_steps"]["picture_checks"],
                          len(d["steps"])), (True, 1, 1, 3))
        self.assertEqual(bp.step_problems(d), [])
        self.assertIn("sailing-ship", bp.known_sets())
        plan = bp.plan({"set": "sailing-ship"}, KIT_ITEMS)
        self.assertEqual((plan["status"], len(plan["booklet"]["steps"]), len(plan["booklet"]["placements"])),
                         ("fit", 3, 4))
        self.assertTrue(any("two independent Muse Wonder reads" in n for n in plan["booklet"]["notes"]))
        self.assertTrue(any("Nobody has built it from these steps yet" in n for n in plan["booklet"]["notes"]))
        self.assertIn("<svg", bk.render_html(plan["booklet"]))

    def test_errors_go_back_at_most_five_times(self):
        fake, record, d = self.run_one([read_reply(LIST)] + [FLOATING] * 6)
        self.assertEqual(len(fake.sent), 1 + 1 + mv.MAX_RETRIES)
        self.assertEqual([s["previous_id"] for s in fake.sent[2:]], [f"r{n}" for n in range(2, 7)])
        self.assertIn("not held by any stud", fake.sent[2]["text"])
        self.assertEqual(fake.sent[2]["images"], 0)
        self.assertFalse(record["booklet"])
        self.assertNotIn("steps", d)
        self.assertIn("6 tries", d["auto_steps"]["reason"])
        o = self.option()
        self.assertEqual((o["piece_status"], o["status"], o["has_booklet"]), ("verified", "fit", False))
        self.assertIn("No step-by-step booklet: no design passed BinBuild's checker and looked like the book's "
                      "picture in 6 tries (the last: 1 checker problem left).", o["message"])
        self.assertNotIn("sailing-ship", bp.known_sets())

    def test_a_retry_that_passes(self):
        fake, record, d = self.run_one([read_reply(LIST), FLOATING, DESIGN, SAME])
        self.assertEqual((record["booklet"], d["auto_steps"]["tries"]), (True, 2))

    def test_a_design_unlike_the_picture_goes_back(self):
        fake, record, d = self.run_one([read_reply(LIST), DESIGN, OTHER, DESIGN, SAME])
        self.assertEqual((record["booklet"], d["auto_steps"]["tries"], d["auto_steps"]["picture_checks"]), (True, 2, 2))
        self.assertEqual(fake.sent[3]["previous_id"], "r2")      # back to the placing conversation
        self.assertIn("the mast is on the stern", fake.sent[3]["text"])

    def test_never_like_the_picture_means_no_booklet(self):
        fake, record, d = self.run_one([read_reply(LIST)] + [DESIGN, OTHER] * 6)
        self.assertEqual(len(fake.sent), 1 + 2 * (1 + mv.MAX_RETRIES))
        self.assertFalse(record["booklet"])
        self.assertIn("not the book's model: the mast is on the stern", d["auto_steps"]["reason"])
        self.assertTrue(bp.verified(d) and not bp.booklet_ready(d))

    def test_exactly_the_list(self):
        short = DESIGN.replace("2x1 (2,1,1) brick orange\n", "")
        check = mv.check_design(mv.wdr.extract(short)[1], OWNED, dict(mv.counts(self.ship["elements"])))
        self.assertTrue(wd.validate(mv.wdr.extract(short)[1], OWNED).ok, "the validator alone would pass it")
        self.assertEqual(check.errors, ["1 under-count: Brick 1x2 (orange) @ Position(0,0,1) — the list has 2, "
                                        "the design uses 1"])

    def test_cannot_stops(self):
        fake, record, d = self.run_one([read_reply(LIST), "Cannot: the mast is held by the clip plate's clip."])
        self.assertEqual(len(fake.sent), 2)
        self.assertIn("the mast is held by the clip plate's clip", d["auto_steps"]["reason"])
        self.assertTrue(bp.verified(d) and not bp.booklet_ready(d))

    def test_the_hinge_plate_gets_no_call(self):
        rows = LIST + [(1, "hinge_plate", "black", "1x4")]
        self.write(dict(self.ship, elements=draft_lines(rows)))
        fake, record, d = self.run_one([read_reply(rows)])
        self.assertEqual(len(fake.sent), 1)
        self.assertIn("no shape for the black 1x4 hinge plate", d["auto_steps"]["reason"])
        o = self.option()
        self.assertEqual((o["piece_status"], o["has_booklet"]), ("verified", False))

    def test_hand_checked_drafts_are_never_changed(self):
        self.write(dict(self.ship, hand_check={"done": True, "on": "2026-11-01", "by": "x", "notes": ""}))
        before = (self.dir / "sailing-ship.json").read_text()
        self.assertNotIn("sailing-ship", [d["id"] for d in mv.in_scope(bp.manual_drafts())])
        self.assertFalse(mv.save(dict(self.ship, seen="changed")))
        self.assertEqual((self.dir / "sailing-ship.json").read_text(), before)


class TestLayers(unittest.TestCase):
    def test_a_piece_held_from_above_goes_in_with_its_holder(self):
        text = ("2x1 (0,0,0) brick orange\n"
                "4x2 (0,0,3) plate medium_azure\n"
                "1x1 (3,1,2) round_plate lime\n")   # hangs under the plate's far end
        check = wd.validate(text, {**OWNED, **{k: 9 for k in OWNED}} if OWNED else {
            ("brick", "brick", "1x2", "orange"): 2, ("plate", "plate", "2x4", "medium_azure"): 2,
            ("plate", "round plate", "1x1", "lime"): 4})
        self.assertTrue(check.ok, check.errors)
        steps = mv.layer_steps(check.pieces)
        self.assertEqual([[p["line"] for p in s["place"]] for s in steps],
                         [["orange 1x2 brick"], ["medium_azure 2x4 plate", "lime 1x1 round plate"]])
        self.assertIn("goes underneath", steps[1]["text"])
        self.assertEqual(steps[1]["place"][0], {"line": "medium_azure 2x4 plate", "at": [0, 0, 3]})


if __name__ == "__main__":
    unittest.main()
