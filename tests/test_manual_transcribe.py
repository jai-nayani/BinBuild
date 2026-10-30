"""Wonder transcription tests: drafts for the manual builds that print no list.

- scope: 82 builds (the 87 without a list, minus 5 pure activities); every
  in-scope page maps to a photo; the owned list is the kit's 50 pieces, the
  hinge plate included (a parts list needs no LDraw geometry);
- checking a reply: only listed pieces, within their counts, every unsure
  line with a reason, the right build, lines of one kind merged; "no fixed
  model" writes nothing;
- the loop: a reply that breaks the rules gets one retry with the errors
  (images only on the first call); a second failure writes nothing;
- drafts: the same format as the 18 hand drafts, marked draft and read by
  Wonder; existing drafts are never overwritten unless they are earlier
  Wonder drafts (and never once hand-checked);
- the recorded live replies replay into the committed drafts;
- a hand-checked Wonder draft gets a bin check and no booklet, like the 18.

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

from backend import build_plan as bp
from backend import manual_check
from backend import manual_transcribe as mt
from backend.wonder_client import WonderReply
from test_full_loop import KIT_ITEMS

try:
    from PIL import Image  # noqa: F401  (the kit's inventory is read through the pipeline)
    HAVE_PILLOW = True
except ImportError:
    HAVE_PILLOW = False

needs_pillow = unittest.skipUnless(HAVE_PILLOW, "Pillow not installed")
OWNED = mt.kit_owned() if HAVE_PILLOW else {}
RECORDED = Path(__file__).resolve().parent / "fixtures" / "wonder-transcribe-recorded.json"
CRAB = next(b for b in mt.todo_builds() if b["id"] == "snappy-crab")


def element(qty, code, color, size, sure=True, doubt=""):
    return {"qty": qty, "code": code, "color": color, "size": size, "sure": sure, "doubt": doubt, "as_seen": "x"}


class Fake:
    """Wonder replaced by written replies; keeps what it was sent."""

    def __init__(self, replies):
        self.replies, self.sent = list(replies), []

    def respond(self, text, instructions=None, previous_id=None, images=()):
        self.sent.append({"text": text, "instructions": instructions, "previous_id": previous_id,
                          "images": len(images)})
        n = len(self.sent)
        r = self.replies[n - 1]
        return WonderReply(f"r{n}", r if isinstance(r, str) else json.dumps(r), "completed",
                           {"input_tokens": 5000, "output_tokens": 4000}, 60.0)


class TestScope(unittest.TestCase):
    @needs_pillow
    def test_the_kit_and_the_list(self):
        self.assertEqual(sum(OWNED.values()), 50)
        listed = mt.listed_pieces(OWNED)
        self.assertEqual((len(listed), sum(n for _, _, _, n, _ in listed)), (21, 50))
        self.assertIn(("hinge_plate", "black", "1x4"), {(c, col, s) for c, col, s, _, _ in listed})

    def test_82_builds_with_photos(self):
        todo = mt.todo_builds()
        self.assertEqual(len(todo), 82)
        self.assertFalse(any(b["kind"] == "activity" or b["status"] != "not-yet-piece-verified" for b in todo))
        for b in todo:
            self.assertTrue(mt.photos_for(b), b["id"])
        self.assertEqual(mt.photos_for(next(b for b in todo if b["id"] == "super-pug")), ["IMG_3619", "IMG_3631"])

    @needs_pillow
    def test_prompt(self):
        text = mt.instructions(OWNED)
        self.assertIn("hinge_plate black 1x4 ×1", text)
        self.assertIn("NEVER add or swap in pieces just to reach that number", text)
        request = mt.request_text(CRAB)
        self.assertIn("The page says it uses 9 elements", request)
        self.assertIn("read only this one", request)


@needs_pillow
class TestCheckReply(unittest.TestCase):
    def test_rules(self):
        data = {"build": "snappy-crab", "fixed_model": True, "elements": [
            element(5, "brick", "orange", "1x2"),                       # the kit has 2
            element(1, "brick", "red", "2x4"),                          # not owned
            element(2, "round_tile", "white", "1x1", sure=False),       # unsure without a reason
            element(1, "plate", "lime", "1x6", sure=True)]}
        elements, errors = mt.check_reply(data, CRAB, OWNED)
        joined = "\n".join(errors)
        self.assertIn("red 2x4 brick is not one of the kit's pieces", joined)
        self.assertIn("sure=false needs a reason", joined)
        self.assertIn("orange 1x2 brick: 5 listed, the kit has 2", joined)
        self.assertIn("lime 1x6 plate", {f"{e['color']} {e['size']} {e['shape']}" for e in elements})

    def test_merge_and_wrong_build(self):
        data = {"build": "submarine", "fixed_model": True, "elements": [
            element(1, "round_tile", "white", "1x1"),
            element(1, "round_tile", "white", "1x1", sure=False, doubt="second eye hidden")]}
        elements, errors = mt.check_reply(data, CRAB, OWNED)
        self.assertEqual(errors, ["'build' must be 'snappy-crab'"])
        self.assertEqual(len(elements), 1)
        self.assertEqual((elements[0]["qty"], elements[0]["sure"], elements[0]["doubt"]), (2, False, "second eye hidden"))

    def test_no_fixed_model(self):
        self.assertEqual(mt.check_reply({"build": "snappy-crab", "fixed_model": False}, CRAB, OWNED), ([], []))


@needs_pillow
class TestLoop(unittest.TestCase):
    GOOD = {"build": "snappy-crab", "fixed_model": True, "seen": "a crab", "count_note": "", "elements": [
        element(1, "hinge_plate", "black", "1x4"), element(2, "clip_plate", "lime", "1x2"),
        element(2, "round_tile", "white", "1x1"), element(2, "cheese_slope", "medium_blue", "1x1", False, "drawn dark"),
        element(1, "plate", "dark_purple", "1x2", False, "prints blue")]}

    def run_one(self, replies):
        fake = Fake(replies)
        with mock.patch.object(mt, "photo_jpeg", return_value=b"jpeg"):
            return mt.transcribe(CRAB, fake, OWNED, log=lambda *_: None), fake

    def test_retry_with_the_errors_then_a_draft(self):
        bad = dict(self.GOOD, elements=[element(3, "brick", "orange", "1x2")])
        record, fake = self.run_one([bad, self.GOOD])
        self.assertEqual(record["status"], "draft")
        self.assertEqual([s["images"] for s in fake.sent], [1, 0])
        self.assertEqual(fake.sent[1]["previous_id"], "r1")
        self.assertIn("orange 1x2 brick: 3 listed, the kit has 2", fake.sent[1]["text"])
        d = record["draft"]
        self.assertEqual((d["status"], d["read_by"], d["elements_total"], d["unsure_elements"]),
                         ("draft", "muse-wonder-1.0", 8, 3))
        self.assertEqual(d["count_check"], {"page_says": 9, "list_total": 8, "matches": False})
        self.assertEqual(record["usd"], round(2 * (5000 * 4 + 4000 * 20) / 1e6, 4))

    def test_two_failures_write_nothing(self):
        record, _ = self.run_one(["not json", {"build": "snappy-crab", "elements": []}])
        self.assertEqual(record["status"], "rejected")
        self.assertNotIn("draft", record)

    def test_no_fixed_model_writes_nothing(self):
        record, _ = self.run_one([{"build": "snappy-crab", "fixed_model": False, "reason": "variants"}])
        self.assertEqual((record["status"], record["reason"]), ("no fixed model", "variants"))

    def test_same_format_as_the_hand_drafts(self):
        record, _ = self.run_one([self.GOOD])
        hand = json.loads((bp.DRAFTS_DIR / "dozy-dolphin.json").read_text())
        self.assertTrue(set(hand) <= set(record["draft"]))
        self.assertEqual(set(hand["elements"][0]), set(record["draft"]["elements"][0]))


class TestWriting(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        for p in bp.DRAFTS_DIR.glob("*.json"):
            shutil.copy(p, self.dir)
        self.patches = [mock.patch.object(bp, "DRAFTS_DIR", self.dir),
                        mock.patch.object(manual_check, "DRAFTS_DIR", self.dir)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_never_overwrites_hand_drafts_or_hand_checked_ones(self):
        hand = json.loads((self.dir / "dozy-dolphin.json").read_text())
        self.assertFalse(mt.write_draft(dict(hand, read_by="muse-wonder-1.0", elements=[]), force=True))
        self.assertEqual(json.loads((self.dir / "dozy-dolphin.json").read_text()), hand)
        new = {"id": "made-up", "hand_check": {"done": False}}
        self.assertTrue(mt.write_draft(new))
        self.assertFalse(mt.write_draft(dict(new, seen="again")))                 # no force: kept
        wonder = dict(new, read_by="muse-wonder-1.0")
        (self.dir / "made-up.json").write_text(json.dumps(wonder))
        self.assertTrue(mt.write_draft(dict(wonder, seen="again"), force=True))   # an earlier Wonder draft: replaced
        (self.dir / "made-up.json").write_text(json.dumps(dict(wonder, hand_check={"done": True})))
        self.assertFalse(mt.write_draft(dict(wonder, seen="third"), force=True))  # hand-checked: kept

    def test_a_hand_checked_wonder_draft_gets_a_bin_check_and_no_booklet(self):
        wonder = [i for i, d in bp.manual_drafts().items() if d.get("read_by") == "muse-wonder-1.0"]
        self.assertTrue(wonder)
        bid = "submarine" if "submarine" in wonder else wonder[0]
        draft = bp.manual_drafts()[bid]
        sure = [f"{e['color']} {e['size']} {e['shape']}" for e in draft["elements"] if not e["sure"]]
        args = [bid] + [a for line in sure for a in ("--sure", line)] + ["--done", "--by", "tester"]
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(manual_check.main(args), 0)
        o = next(o for o in bp.manual_options(KIT_ITEMS) if o["id"] == bid)
        self.assertEqual((o["piece_status"], o["has_booklet"]), ("verified", False))
        self.assertIn(o["status"], ("fit", "short"))
        self.assertIn("Build it from the book", o["message"])


@needs_pillow
@unittest.skipUnless(RECORDED.is_file(), "no recorded transcription run")
class TestRecorded(unittest.TestCase):
    def test_recorded_replies_replay_into_the_committed_drafts(self):
        recorded = json.loads(RECORDED.read_text())
        builds = {b["id"]: b for b in mt.todo_builds()}
        for bid, replies in recorded["replies"].items():
            with mock.patch.object(mt, "photo_jpeg", return_value=b"jpeg"):
                record = mt.transcribe(builds[bid], Fake(replies), OWNED, log=lambda *_: None)
            committed = json.loads((bp.DRAFTS_DIR / f"{bid}.json").read_text())
            for key in ("read_from",):  # the date is when it ran
                record["draft"].pop(key)
                committed.pop(key)
            self.assertEqual(record["draft"], committed, bid)


if __name__ == "__main__":
    unittest.main()
