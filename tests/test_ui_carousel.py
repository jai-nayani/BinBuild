"""The booklet carousel, its booklet view, and the clean close-up.

- backend: "What can I build?" marks booklet builds with the booklet's own
  finished-model picture (booklet.picture) as the cover; the empty-bin gate
  is unchanged, and the sample bin gives exactly the booklet builds;
- the app (the real app.js in Node, tests/retake_popup_harness.js): the
  build view is a sideways snap carousel of only those builds (cover, name,
  piece count on a card, nothing else), tapping a card makes its booklet and
  opens it, and Back lands on the same card; an empty bin shows no cards;
- close-up: a piece Spark flagged unsure is named again from one photo of
  just that piece, through Spark's single-photo call, and its row updates
  where it sits (same id, same dot); sure, removed and confirmed pieces are
  refused before any model call, and a close-up of zero, two or no real
  pieces changes nothing; fix, remove, put back and add still work after it.

Every paid client is a fake here: no Wonder, Model API or Baseten call.
Standard-library unittest. Run from the repo root:
    python3 -m unittest discover -s tests -v
"""

import io
import json
import re
import shutil
import subprocess
import tempfile
import unittest
import urllib.error
import urllib.request
import uuid
from contextlib import closing
from pathlib import Path

from backend import booklet as bk
from backend import build_plan as bp
from backend import inventory_db as db

try:
    from PIL import Image
    from backend import full_loop
    from test_full_loop import KIT_ITEMS, seed
    HAVE_SERVER = True
except ImportError:
    HAVE_SERVER = False

try:
    from backend import photo_gate
except ImportError:
    photo_gate = None

REPO = Path(__file__).resolve().parent.parent
APP = REPO / "app"
HARNESS = Path(__file__).resolve().parent / "retake_popup_harness.js"
NODE = shutil.which("node")
VIEWS = ("top", "front", "right", "back", "left")
CSS = (APP / "style.css").read_text()
JS = (APP / "app.js").read_text()


def booklet_options(items):
    return [o for o in bp.options(items) if o["kind"] == "manual" and o["has_booklet"]]


class TestCovers(unittest.TestCase):
    def test_cover_is_the_booklets_finished_model(self):
        found = booklet_options(KIT_ITEMS)
        # 9: the paintbrush's booklet was withdrawn (the book's brush lies on
        # its side, which the physical validator cannot express), and the two
        # cakes' lists are disputed by their pictures (backend/manual/drafts).
        self.assertEqual(len(found), 9)
        for gone in ("paintbrush", "birthday-cake-message", "blueberry-cake"):
            self.assertNotIn(gone, [o["id"] for o in found])
        for o in found:
            with self.subTest(o["id"]):
                book = bp.plan_set(o["set"], KIT_ITEMS)["booklet"]
                self.assertEqual(o["cover"], bk.cover(book))
                self.assertTrue(o["cover"].startswith("<svg"))
                self.assertEqual(o["pieces"], sum(p["qty"] for p in book["parts"]))

    def test_apple_visitor_is_shown_as_hungry_bird(self):
        card = next(o for o in booklet_options(KIT_ITEMS) if o["id"] == "apple-visitor")
        book = bp.plan_set(card["set"], KIT_ITEMS)["booklet"]
        self.assertEqual((card["title"], book["title"]), ("Hungry bird", "Hungry bird"))
        self.assertIn("<title>Hungry bird", bk.render_html(book))

    def test_no_cover_without_a_booklet(self):
        for o in bp.options(KIT_ITEMS):
            if not o.get("has_booklet"):
                self.assertNotIn("cover", o, o["id"])


@unittest.skipUnless(HAVE_SERVER, "FastAPI, uvicorn or Pillow not installed")
class TestGateUnchanged(unittest.TestCase):
    def test_empty_bin_then_sample_bin(self):
        class NoSpark:
            def identify_pieces(self, *a, **k):
                raise AssertionError("Spark called")

        with tempfile.TemporaryDirectory() as tmp, full_loop.server(tmp, NoSpark()) as api:
            status, body = api.call("GET", "/api/builds/options")
            self.assertEqual((status, body["options"]), (200, []))
            self.assertIn("scan_first", body)
            status, sample = api.call("POST", "/api/inventory/sample")
            self.assertEqual(status, 200, sample)
            self.assertEqual(api.call("GET", "/api/builds/options")[1]["options"], [],
                             "loaded but not confirmed: still no cards")
            status, done = api.call("POST", f"/api/inventory/batch/{sample['batch_id']}/confirm")
            self.assertEqual((status, done["pieces_added"]), (200, 50))
            status, body = api.call("GET", "/api/builds/options")
            self.assertEqual(status, 200)
            cards = [o for o in body["options"] if o["kind"] == "manual" and o["has_booklet"]]
            self.assertEqual([o["id"] for o in cards], [o["id"] for o in booklet_options(KIT_ITEMS)])
            self.assertTrue(all(o["cover"].startswith("<svg") for o in cards))


# --- the app in Node ---------------------------------------------------------

def play(**scenario):
    notices = {v: photo_gate.retake_notice(v, ["blurry"]) for v in VIEWS}
    out = subprocess.run([NODE, str(HARNESS), json.dumps({"notices": notices, "fail": [], **scenario})],
                         capture_output=True, text=True, timeout=60, check=True)
    return json.loads(out.stdout)


COVER = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10" role="img"><rect width="10" height="10"/></svg>'
OPTIONS = {
    "inventory": {"total_pieces": 50, "generator_ready": 2, "other": 48},
    "options": [
        {"kind": "manual", "id": "house-and-tree", "title": "House and tree", "set": "house-and-tree",
         "piece_status": "verified", "status": "fit", "has_booklet": True, "pieces": 7, "cover": COVER},
        {"kind": "manual", "id": "guitar", "title": "Guitar", "set": "guitar",
         "piece_status": "verified", "status": "fit", "has_booklet": True, "pieces": 3, "cover": COVER},
        {"kind": "manual", "id": "dozy-dolphin", "title": "Dozy Dolphin",
         "piece_status": "verified", "status": "fit", "has_booklet": False, "pieces": 18},
        {"kind": "manual", "id": "submarine", "title": "Submarine",
         "piece_status": "not-yet-piece-verified", "status": "unverified", "has_booklet": False},
        {"kind": "brickgpt", "id": "train", "title": "Train", "status": "fit", "has_booklet": False, "pieces": 40},
    ],
}


@unittest.skipUnless(NODE and photo_gate, "Node or Pillow not installed")
class TestCarouselInTheApp(unittest.TestCase):
    def test_only_booklet_builds_as_cards(self):
        ui = play(open_builds=True, build_options=OPTIONS)["ui"]
        carousel = ui["builds"]["carousel"]
        self.assertIsNotNone(carousel)
        self.assertEqual([c["id"] for c in carousel["cards"]], ["house-and-tree", "guitar"])
        for card, name, pieces in zip(carousel["cards"], ("House and tree", "Guitar"), ("7 pieces", "3 pieces")):
            self.assertEqual(card["classes"], ["build-card"])
            self.assertEqual(card["child_classes"], ["build-cover", "build-name", "build-pieces"])
            self.assertEqual(card["texts"], ["", name, pieces])
            self.assertEqual(card["cover"], COVER)
        shown = " ".join(carousel["list_texts"])
        for hidden in ("Dozy Dolphin", "Submarine", "Train"):
            self.assertNotIn(hidden, shown)

    def test_snap_contract(self):
        self.assertRegex(CSS, r"\.build-carousel \{[^}]*display: flex[^}]*overflow-x: auto[^}]*overflow-y: hidden"
                              r"[^}]*scroll-snap-type: x mandatory")
        self.assertRegex(CSS, r"\.build-card \{[^}]*scroll-snap-align: center")
        self.assertIn("o.kind === 'manual' && o.has_booklet", JS, "the same has_booklet the app already used")
        self.assertIn("id = 'build-carousel'", JS)

    def test_tapping_a_card_opens_its_booklet_and_back_lands_on_it(self):
        result = play(open_builds=True, build_options=OPTIONS, tap_card=1, carousel_scroll=240)
        ui = result["ui"]
        self.assertEqual(ui["booklet"]["view"], ["booklet-view"])
        self.assertEqual(ui["booklet"]["title"], "Guitar")
        self.assertTrue(ui["booklet"]["frame"].endswith("/api/builds/7/booklet"), ui["booklet"])
        self.assertIn('POST /api/builds {"set":"guitar"}', ui["booklet"]["requests"])
        self.assertEqual(ui["after_booklet_back"], {"view": ["build-view"], "scroll_left": 240,
                                                    "focused_card": "guitar"})
        self.assertFalse([r for r in result["requests"] if "wonder" in r or r.endswith("/classify")])

    def test_empty_bin_has_no_cards(self):
        ui = play(open_builds=True)["ui"]
        self.assertIsNone(ui["builds"]["carousel"])
        self.assertEqual(ui["builds"]["catalog_entries"], 0)
        self.assertEqual(ui["builds"]["buttons"], ["📷 Scan a handful", "Use sample images"])


# --- the clean close-up --------------------------------------------------------

VOCAB = {"families": ["brick", "plate", "tile", "slope"],
         "colors": [{"name": n, "hex": "#888888"} for n in ("red", "blue", "orange", "black", "green", "unknown")],
         "shapes": ["brick", "plate", "tile", "curved slope"], "generator_types": ["1x2"]}


def detection(id_, family, shape, size, color, confidence, unsure, status="proposed", source="spark", point=None):
    return {"id": id_, "family": family, "shape": shape, "size": size, "color": color, "plain": True,
            "count": 1, "confidence": confidence, "unsure": unsure, "status": status, "source": source,
            "generator_type": None, "region": {"point": point} if point else None}


def review_body(detections):
    kept = [d for d in detections if d["status"] != "rejected"]
    return {"batch": {"id": "sample1", "status": "classified", "classifier": "spark:test"},
            "detections": detections, "pieces": len(kept), "photos_ready": True,
            "count_photo": {"view": "top", "width": 1000, "height": 1000, "url": "/photo"}}


@unittest.skipUnless(NODE and photo_gate, "Node or Pillow not installed")
class TestCloseUpInTheApp(unittest.TestCase):
    def test_unsure_piece_updated_in_place_and_the_old_actions_still_work(self):
        before = [detection(1, "brick", "brick", "1x2", "red", 0.42, True, point=[100, 100]),
                  detection(2, "plate", "plate", "1x2", "blue", 0.96, False, point=[200, 100]),
                  detection(3, "tile", "tile", "1x2", "black", 0.99, False, status="rejected")]
        updated = [detection(1, "slope", "curved slope", "1x2", "orange", 0.97, False, point=[100, 100]),
                   before[1], before[2]]
        reply = review_body(updated)
        result = play(use_sample=True, review_actions=True, vocab=VOCAB, review=review_body(before),
                      reclassify_reply={**reply, "reclassified": True, "detection": updated[0]},
                      review_reply=reply)
        ui = result["ui"]
        self.assertEqual(ui["retake_buttons_before"], 1, ui["review_before"])
        after = ui["review_after_retake"]
        self.assertEqual(after["status"], "✓ Updated: orange 1x2 curved slope (97% sure).")
        self.assertIn("orange 1x2 curved slope", " ".join(t for g in after["groups"] for t in g["texts"]))
        self.assertNotIn("red 1x2 brick", " ".join(t for g in after["groups"] for t in g["texts"]))
        self.assertEqual([(d["left"], d["top"]) for d in after["dots"]],
                         [(d["left"], d["top"]) for d in ui["review_before"]["dots"]], "the dot did not move")
        self.assertIn("focus", after["dots"][0]["classes"])
        sent = ui["review_requests"]
        self.assertEqual((sent[0]["method"], sent[0]["path"], sent[0]["files"]),
                         ("POST", "/api/inventory/batch/sample1/pieces/1/reclassify", ["close-up.jpg"]))
        self.assertTrue(ui["fix_opened"] and ui["edit_modal_after_fix"])
        self.assertTrue(ui["remove_clicked"] and ui["put_back_clicked"])
        self.assertTrue(ui["add_opened"] and ui["edit_modal_after_add"])
        payloads = [json.loads(r["json"]) for r in sent[1:] if r["json"]]
        self.assertTrue(any(p.get("corrections") for p in payloads), payloads)
        self.assertTrue(any(p.get("additions") for p in payloads), payloads)


class FakeSpark:
    """One close-up call, scripted: pieces and the real-LEGO answer."""

    model = "fake-spark"

    def __init__(self, pieces, answer="yes"):
        self.pieces, self.answer, self.calls = pieces, answer, 0

    def identify_pieces(self, image_jpeg, context=(), max_tokens=0):
        self.calls += 1
        return ({"checks": [{"image": 1, "real_lego": self.answer, "reason": "test"}],
                 "pieces": self.pieces}, object())


def jpeg_bytes():
    out = io.BytesIO()
    Image.new("RGB", (120, 90), (200, 60, 40)).save(out, "JPEG")
    return out.getvalue()


def post_photo(api, path, data):
    boundary = uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"close-up.jpg\"\r\n"
            "Content-Type: image/jpeg\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(api.base + path, data=body, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as err:
        with err:
            return err.code, json.loads(err.read())


PIECE = {"family": "slope", "shape": "curved slope", "size": "1x2", "color": "orange",
         "plain": False, "confidence": 0.97, "at": [0.5, 0.5]}


@unittest.skipUnless(HAVE_SERVER, "FastAPI, uvicorn or Pillow not installed")
class TestCloseUpApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.spark = FakeSpark([PIECE])
        self.ctx = full_loop.server(self.tmp.name, self.spark)
        self.api = self.ctx.__enter__()
        with closing(db.connect()) as conn:
            photos = [{"view": v, "file": f"{v}.jpg", "bytes": 1, "sha256": f"close{v}",
                       "gate": {"passed": True, "reasons": [], "metrics": {}}} for v in VIEWS]
            db.register_batch(conn, "20261102-000001-abc123", "2026-11-02T00:00:00", photos,
                              db.photos_fingerprint(photos))
            db.replace_detections(conn, "20261102-000001-abc123", [
                {"family": "brick", "shape": "brick", "size": "1x2", "color": "red", "plain": True,
                 "count": 1, "confidence": 0.42, "region": {"bbox": [0, 0, 9, 9], "point": [10, 20]}},
                {"family": "plate", "shape": "plate", "size": "1x2", "color": "blue", "plain": True,
                 "count": 1, "confidence": 0.96, "region": {"bbox": [0, 0, 9, 9], "point": [30, 40]}},
                {"family": "tile", "shape": "tile", "size": "1x2", "color": "black", "plain": True,
                 "count": 1, "confidence": 0.4, "region": {"bbox": [0, 0, 9, 9], "point": [50, 60]}},
            ], "spark:test")
            rev = db.batch_review(conn, "20261102-000001-abc123")
            self.unsure, self.sure, self.removed = [d["id"] for d in rev["detections"]]
            db.review_batch(conn, "20261102-000001-abc123",
                            corrections=[{"detection_id": self.removed, "status": "rejected"}])
        self.batch = "20261102-000001-abc123"

    def tearDown(self):
        self.ctx.__exit__(None, None, None)
        self.tmp.cleanup()

    def reclassify(self, detection_id, batch=None):
        return post_photo(self.api, f"/api/inventory/batch/{batch or self.batch}/pieces/{detection_id}/reclassify",
                          jpeg_bytes())

    def label_of(self, detection_id):
        with closing(db.connect()) as conn:
            d = next(x for x in db.batch_review(conn, self.batch)["detections"] if x["id"] == detection_id)
        return d

    def test_unsure_flags(self):
        self.assertTrue(self.label_of(self.unsure)["unsure"])
        self.assertFalse(self.label_of(self.sure)["unsure"])
        self.assertFalse(self.label_of(self.removed)["unsure"], "a removed piece is not flagged")

    def test_close_up_updates_the_piece_where_it_sits(self):
        before = self.label_of(self.unsure)
        status, body = self.reclassify(self.unsure)
        self.assertEqual(status, 200, body)
        self.assertEqual(self.spark.calls, 1)
        after = body["detection"]
        self.assertEqual((after["id"], after["region"], after["count"], after["status"]),
                         (before["id"], before["region"], before["count"], before["status"]))
        self.assertEqual((after["family"], after["shape"], after["size"], after["color"], after["plain"]),
                         ("slope", "curved slope", "1x2", "orange", False))
        self.assertEqual((after["confidence"], after["unsure"]), (0.97, False))
        self.assertEqual([d["id"] for d in body["detections"]],
                         [self.unsure, self.sure, self.removed], "no piece added, removed or reordered")
        self.assertEqual(body["pieces"], 2)

    def test_refused_before_any_model_call(self):
        self.assertEqual(self.reclassify(self.sure)[0], 422)
        self.assertEqual(self.reclassify(self.removed)[0], 409)
        self.assertEqual(self.reclassify(9999)[0], 404)
        self.assertEqual(self.spark.calls, 0)

    def test_a_bad_close_up_changes_nothing(self):
        for pieces, answer in (([PIECE, PIECE], "yes"), ([], "yes"), ([PIECE], "no")):
            self.spark.pieces, self.spark.answer = pieces, answer
            status, body = self.reclassify(self.unsure)
            self.assertEqual(status, 422, body)
            after = self.label_of(self.unsure)
            self.assertEqual((after["family"], after["color"], after["confidence"]), ("brick", "red", 0.42))

    def test_confirmed_batch_is_refused_before_any_model_call(self):
        with closing(db.connect()) as conn:
            db.confirm_batch(conn, self.batch)
        self.assertEqual(self.reclassify(self.unsure)[0], 409)
        self.assertEqual(self.spark.calls, 0)


if __name__ == "__main__":
    unittest.main()
