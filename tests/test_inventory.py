"""Inventory loop tests: database, review, confirm, undo, summary, Spark client.

Standard library only (Pillow is used by one test when installed). Run from
the repo root:
    python3 -m unittest discover -s tests -v
"""

import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from backend import inventory_db as db
from backend import inventory_vocab as vocab
from backend import spark_client

VIEWS = ("top", "front", "right", "back", "left")


def photos(tag):
    """Five photos that already passed the photo gate (see test_photo_gate for the gate itself)."""
    return [{"view": v, "file": f"{n}-{v}.jpg", "sha256": f"{tag}{n}", "bytes": 100 + n,
             "gate": {"passed": True, "reasons": [], "metrics": {}}}
            for n, v in enumerate(VIEWS, 1)]


def piece(family, size, color, plain=False, shape="", count=1):
    return {"photo_view": "top", "family": family, "size": size, "color": color, "plain": plain,
            "shape": shape, "count": count, "confidence": 0.8, "region": {"bbox": [0, 0, 10, 10], "point": None}}


# The house-and-tree set plus a few non-generator pieces.
HOUSE = [
    piece("plate", "1x6", "lime", plain=True, shape="plate"),
    piece("brick", "1x2", "orange", plain=True, shape="brick"),
    piece("brick", "2x1", "orange", plain=True, shape="brick"),  # size written the other way round
    piece("slope", "1x2", "black", shape="curved slope", count=2),
    piece("brick", "1x1", "light_bluish_gray", shape="round brick"),
    piece("plate", "1x1", "lime", shape="round plate"),
]


class DbCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = db.connect(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def add_batch(self, batch_id, detections=HOUSE, tag=None):
        db.register_batch(self.conn, batch_id, "2026-10-28T00:00:00+00:00", photos(tag or batch_id), tag or batch_id)
        if detections:
            db.replace_detections(self.conn, batch_id, detections, "test")


class TestDatabase(DbCase):
    def test_tables_exist(self):
        names = {r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertTrue({"batches", "batch_photos", "detections", "inventory_items", "builds"} <= names)

    def test_register_is_idempotent(self):
        first, created = db.register_batch(self.conn, "b1", "t", photos("x"), "fp1")
        again, created_again = db.register_batch(self.conn, "b1", "t", photos("x"), "fp1")
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first, again)
        self.assertEqual(len(db.batch_photos(self.conn, "b1")), 5)

    def test_fingerprint_finds_reupload(self):
        db.register_batch(self.conn, "b1", "t", photos("x"), "fp1")
        self.assertEqual(db.batch_by_fingerprint(self.conn, "fp1")["id"], "b1")
        self.assertIsNone(db.batch_by_fingerprint(self.conn, "fp2"))

    def test_detections_get_generator_type_only_for_plain_bricks(self):
        self.add_batch("b1")
        rows = {(d["family"], d["size"], d["color"]): d for d in db.batch_review(self.conn, "b1")["detections"]}
        self.assertEqual(rows[("brick", "1x2", "orange")]["generator_type"], "1x2")
        self.assertIsNone(rows[("brick", "1x1", "light_bluish_gray")]["generator_type"])  # round brick
        self.assertIsNone(rows[("plate", "1x6", "lime")]["generator_type"])  # plates never feed BrickGPT

    def test_invalid_piece_is_rejected(self):
        db.register_batch(self.conn, "b1", "t", photos("x"), "fp1")
        with self.assertRaises(ValueError):
            db.replace_detections(self.conn, "b1", [piece("brick", "1x2", "chartreuse")], "test")
        with self.assertRaises(ValueError):
            db.replace_detections(self.conn, "b1", [piece("gizmo", "1x2", "red")], "test")

    def test_reclassify_replaces_proposals(self):
        self.add_batch("b1")
        db.replace_detections(self.conn, "b1", [piece("brick", "2x4", "red", plain=True)], "test")
        self.assertEqual(len(db.batch_review(self.conn, "b1")["detections"]), 1)


class TestReview(DbCase):
    def test_correction_keeps_original(self):
        self.add_batch("b1", [piece("brick", "1x2", "dark_orange", plain=True)])
        det = db.batch_review(self.conn, "b1")["detections"][0]
        review = db.review_batch(self.conn, "b1", corrections=[{"detection_id": det["id"], "color": "orange"}])
        fixed = review["detections"][0]
        self.assertEqual(fixed["color"], "orange")
        self.assertEqual(fixed["status"], "corrected")
        self.assertEqual(fixed["original"]["color"], "dark_orange")
        self.assertEqual(review["corrections"], 1)

    def test_correction_rederives_generator_type(self):
        self.add_batch("b1", [piece("plate", "1x2", "orange", plain=True)])
        det = db.batch_review(self.conn, "b1")["detections"][0]
        review = db.review_batch(self.conn, "b1", corrections=[{"detection_id": det["id"], "family": "brick"}])
        self.assertEqual(review["detections"][0]["generator_type"], "1x2")

    def test_accept_without_changes(self):
        self.add_batch("b1", [piece("tile", "1x1", "white")])
        det = db.batch_review(self.conn, "b1")["detections"][0]
        review = db.review_batch(self.conn, "b1", corrections=[{"detection_id": det["id"], "status": "accepted"}])
        self.assertEqual(review["detections"][0]["status"], "accepted")
        self.assertIsNone(review["detections"][0]["original"])

    def test_reject_and_add(self):
        self.add_batch("b1", [piece("tile", "1x1", "white")])
        det = db.batch_review(self.conn, "b1")["detections"][0]
        review = db.review_batch(
            self.conn, "b1",
            corrections=[{"detection_id": det["id"], "status": "rejected"}],
            additions=[{"family": "brick", "size": "1x2", "color": "orange", "plain": True, "count": 2}],
        )
        self.assertEqual(review["pieces"], 2)
        self.assertEqual([d["source"] for d in review["detections"]], ["spark", "manual"])

    def test_unknown_detection(self):
        self.add_batch("b1")
        with self.assertRaises(db.NotFound):
            db.review_batch(self.conn, "b1", corrections=[{"detection_id": 9999, "status": "accepted"}])

    def test_manual_pieces_on_unclassified_batch(self):
        self.add_batch("b1", detections=None)
        db.review_batch(self.conn, "b1", additions=[{"family": "plate", "size": "2x2", "color": "magenta"}])
        self.assertEqual(db.get_batch(self.conn, "b1")["status"], "classified")


class TestConfirm(DbCase):
    def test_confirm_adds_kept_pieces(self):
        self.add_batch("b1")
        result = db.confirm_batch(self.conn, "b1")
        self.assertEqual(result["pieces_added"], 7)
        self.assertFalse(result["already_confirmed"])
        self.assertEqual(db.inventory_summary(self.conn)["total_pieces"], 7)
        statuses = {d["status"] for d in db.batch_review(self.conn, "b1")["detections"]}
        self.assertEqual(statuses, {"accepted"})

    def test_confirm_twice_adds_once(self):
        self.add_batch("b1")
        db.confirm_batch(self.conn, "b1")
        again = db.confirm_batch(self.conn, "b1")
        self.assertTrue(again["already_confirmed"])
        self.assertEqual(again["pieces_added"], 0)
        self.assertEqual(again["pieces_in_batch"], 7)
        self.assertEqual(db.inventory_summary(self.conn)["total_pieces"], 7)

    def test_rejected_pieces_stay_out(self):
        self.add_batch("b1")
        det = db.batch_review(self.conn, "b1")["detections"][0]  # the lime 1x6 plate
        db.review_batch(self.conn, "b1", corrections=[{"detection_id": det["id"], "status": "rejected"}])
        self.assertEqual(db.confirm_batch(self.conn, "b1")["pieces_added"], 6)

    def test_nothing_to_confirm(self):
        self.add_batch("b1", detections=None)
        with self.assertRaises(db.Conflict):
            db.confirm_batch(self.conn, "b1")
        with self.assertRaises(db.NotFound):
            db.confirm_batch(self.conn, "nope")

    def test_confirmed_batch_is_locked(self):
        self.add_batch("b1")
        db.confirm_batch(self.conn, "b1")
        det = db.batch_review(self.conn, "b1")["detections"][0]
        with self.assertRaises(db.Conflict):
            db.review_batch(self.conn, "b1", corrections=[{"detection_id": det["id"], "status": "rejected"}])
        with self.assertRaises(db.Conflict):
            db.replace_detections(self.conn, "b1", HOUSE, "test")


class TestUndo(DbCase):
    def test_undo_takes_out_the_last_batch_only(self):
        self.add_batch("b1")
        self.add_batch("b2", [piece("brick", "2x4", "red", plain=True, count=3)])
        db.confirm_batch(self.conn, "b1")
        db.confirm_batch(self.conn, "b2")
        self.assertEqual(db.inventory_summary(self.conn)["total_pieces"], 10)
        undone = db.undo_last_batch(self.conn)
        self.assertEqual(undone, {"batch_id": "b2", "pieces_removed": 3})
        self.assertEqual(db.inventory_summary(self.conn)["total_pieces"], 7)
        self.assertEqual(db.get_batch(self.conn, "b2")["status"], "classified")
        self.assertEqual(db.undo_last_batch(self.conn)["batch_id"], "b1")
        self.assertEqual(db.inventory_summary(self.conn)["total_pieces"], 0)
        self.assertIsNone(db.undo_last_batch(self.conn))

    def test_undo_follows_confirm_order_not_upload_order(self):
        self.add_batch("b1")
        self.add_batch("b2", [piece("brick", "2x4", "red", plain=True)])
        db.confirm_batch(self.conn, "b2")
        db.confirm_batch(self.conn, "b1")
        self.assertEqual(db.undo_last_batch(self.conn)["batch_id"], "b1")

    def test_expected_batch_makes_retry_safe(self):
        self.add_batch("b1")
        self.add_batch("b2", [piece("brick", "2x4", "red", plain=True)])
        db.confirm_batch(self.conn, "b1")
        db.confirm_batch(self.conn, "b2")
        db.undo_last_batch(self.conn, expected_batch_id="b2")
        with self.assertRaises(db.Conflict):  # a retry of the same undo
            db.undo_last_batch(self.conn, expected_batch_id="b2")
        self.assertEqual(db.inventory_summary(self.conn)["total_pieces"], 7)

    def test_undone_batch_can_be_corrected_and_reconfirmed(self):
        self.add_batch("b1")
        db.confirm_batch(self.conn, "b1")
        db.undo_last_batch(self.conn)
        det = db.batch_review(self.conn, "b1")["detections"][0]
        db.review_batch(self.conn, "b1", corrections=[{"detection_id": det["id"], "count": 2}])
        self.assertEqual(db.confirm_batch(self.conn, "b1")["pieces_added"], 8)
        self.assertEqual(db.inventory_summary(self.conn)["total_pieces"], 8)


class TestSummary(DbCase):
    def test_split_generator_ready_from_everything_else(self):
        self.add_batch("b1", HOUSE + [
            piece("brick", "1x4", "blue", shape="brick with studs on side", count=2),
            piece("brick", "1x3", "red", plain=True),        # plain, but not one of the 8 sizes
            piece("brick", "2x4", "red", plain=True),
            piece("unknown", None, "unknown"),
            piece("tile", "1x1", "white", shape="printed round tile", count=4),
        ])
        db.confirm_batch(self.conn, "b1")
        s = db.inventory_summary(self.conn)
        self.assertEqual(s["total_pieces"], 7 + 2 + 1 + 1 + 1 + 4)
        gen = s["generator_ready"]
        self.assertEqual(list(gen["types"]), list(vocab.GENERATOR_TYPES))
        self.assertEqual(gen["types"]["1x2"], {"total": 2, "colors": {"orange": 2}})
        self.assertEqual(gen["types"]["2x4"], {"total": 1, "colors": {"red": 1}})
        self.assertEqual(gen["types"]["1x4"]["total"], 0)  # modified 1x4 bricks are not generator-ready
        self.assertEqual(gen["total"], 3)
        fam = s["other"]["families"]
        self.assertEqual(fam["brick"], {"total": 4, "colors": {"blue": 2, "light_bluish_gray": 1, "red": 1}})
        self.assertEqual(fam["plate"], {"total": 2, "colors": {"lime": 2}})
        self.assertEqual(fam["slope"], {"total": 2, "colors": {"black": 2}})
        self.assertEqual(fam["tile"], {"total": 4, "colors": {"white": 4}})
        self.assertEqual(s["other"]["total"], 12)
        self.assertEqual(s["unknown"], {"total": 1, "colors": {"unknown": 1}})
        self.assertEqual(s["batches_confirmed"], 1)

    def test_summary_merges_batches(self):
        self.add_batch("b1")
        self.add_batch("b2", [piece("brick", "1x2", "orange", plain=True)])
        db.confirm_batch(self.conn, "b1")
        db.confirm_batch(self.conn, "b2")
        s = db.inventory_summary(self.conn)
        self.assertEqual(s["generator_ready"]["types"]["1x2"], {"total": 3, "colors": {"orange": 3}})
        self.assertEqual(s["batches_confirmed"], 2)

    def test_unconfirmed_batches_are_not_inventory(self):
        self.add_batch("b1")
        self.assertEqual(db.inventory_summary(self.conn)["total_pieces"], 0)


class TestVocab(unittest.TestCase):
    def test_sizes(self):
        self.assertEqual(vocab.normalize_size("2 x 1"), "1x2")
        self.assertEqual(vocab.normalize_size("4×2"), "2x4")
        self.assertEqual(vocab.normalize_size("1x2x1"), "1x2")
        self.assertIsNone(vocab.normalize_size(""))
        self.assertIsNone(vocab.normalize_size("round"))

    def test_colors_and_families(self):
        self.assertEqual(vocab.normalize_color("Lime green"), "lime")
        self.assertEqual(vocab.normalize_color("light grey"), "light_bluish_gray")
        self.assertEqual(vocab.normalize_color("Light Bluish Gray"), "light_bluish_gray")
        self.assertEqual(vocab.normalize_color("transparent"), "trans_clear")
        self.assertEqual(vocab.normalize_color("grey"), "unknown")
        self.assertEqual(vocab.normalize_family("Plates"), "plate")
        self.assertEqual(vocab.normalize_family("curved slope"), "slope")
        self.assertEqual(vocab.normalize_family("spaceship"), "unknown")

    def test_strict_checks(self):
        self.assertEqual(vocab.check_size("2x1"), "1x2")
        self.assertIsNone(vocab.check_size(""))
        for bad in ("2x1 brick", "big"):
            with self.assertRaises(ValueError):
                vocab.check_size(bad)
        with self.assertRaises(ValueError):
            vocab.check_color("Lime green")


class TestSparkClient(unittest.TestCase):
    KEY = "test-key-0123456789"

    def test_key_from_env_file(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(spark_client.KEY_NAME, None)
            env = Path(tmp) / ".env"
            env.write_text(f"# comment\nOTHER=1\nexport {spark_client.KEY_NAME}='{self.KEY}'\n")
            self.assertEqual(spark_client.load_api_key(env), self.KEY)
            with self.assertRaises(spark_client.SparkError) as caught:
                spark_client.load_api_key(Path(tmp) / "missing.env")
            self.assertNotIn(self.KEY, str(caught.exception))

    def test_key_never_in_repr_or_errors(self):
        client = spark_client.SparkClient(self.KEY, retries=0)
        self.assertNotIn(self.KEY, repr(client))
        error = urllib.error.HTTPError(
            spark_client.BASE_URL, 401, "Unauthorized", {}, io.BytesIO(f"bad key {self.KEY}".encode()))
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(spark_client.SparkError) as caught:
                client.chat([{"role": "user", "content": "hi"}])
        self.assertIn("HTTP 401", str(caught.exception))
        self.assertNotIn(self.KEY, str(caught.exception))

    def test_request_shape(self):
        client = spark_client.SparkClient(self.KEY, retries=0)
        content = '```json\n{"checks": [{"image": 1, "real_lego": "yes"}], "pieces": [], "total": 0}\n```'
        reply = {"choices": [{"message": {"content": content}, "finish_reason": "stop"}], "usage": {"total_tokens": 5}}
        seen = {}

        def fake_urlopen(request, timeout):
            seen["url"], seen["body"] = request.full_url, json.loads(request.data)
            seen["auth"] = request.get_header("Authorization")
            return io.BytesIO(json.dumps(reply).encode())

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            data, _ = client.identify_pieces(b"jpeg", [("front", b"jpeg2")])
        self.assertEqual(data["pieces"], [])
        self.assertEqual(seen["url"], "https://inference.baseten.co/v1/chat/completions")
        self.assertEqual(seen["body"]["model"], "meta-models/muse-spark-open-1026")
        self.assertEqual(seen["auth"], f"Api-Key {self.KEY}")
        images = [p for p in seen["body"]["messages"][0]["content"] if p["type"] == "image_url"]
        self.assertEqual(len(images), 2)

    def test_reply_without_checks_is_an_error(self):
        client = spark_client.SparkClient(self.KEY, retries=0)
        reply = {"choices": [{"message": {"content": '{"pieces": [], "total": 0}'}, "finish_reason": "stop"}]}
        with mock.patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(reply).encode())):
            with self.assertRaises(spark_client.SparkError):
                client.identify_pieces(b"jpeg")

    def test_image_checks(self):
        data = {"checks": [{"image": 1, "real_lego": "Yes"}, {"image": "2", "real_lego": "no", "reason": "a screen"},
                           {"image": 3, "real_lego": "probably"}, "junk"]}
        answers = spark_client.image_checks(data, 4)
        self.assertEqual([answers[n]["answer"] for n in (1, 2, 3, 4)], ["yes", "no", "uncertain", "uncertain"])
        self.assertEqual(answers[2]["reason"], "a screen")

    def test_cut_off_reply_is_an_error(self):
        client = spark_client.SparkClient(self.KEY, retries=0)
        reply = {"choices": [{"message": {"content": '{"pieces": ['}, "finish_reason": "length"}]}
        with mock.patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(reply).encode())):
            with self.assertRaises(spark_client.SparkError):
                client.identify_pieces(b"jpeg")


try:
    import PIL  # noqa: F401
    HAVE_PILLOW = True
except ImportError:
    HAVE_PILLOW = False


@unittest.skipUnless(HAVE_PILLOW, "Pillow not installed")
class TestToDetection(unittest.TestCase):
    def test_spark_item_to_detection(self):
        from backend.inventory_pipeline import to_detection
        from backend.segmenter import Region
        d = to_detection({"family": "Bricks", "size": "2 x 1", "color": "Orange", "plain": True,
                          "confidence": 1.4, "at": [0.5, 0.25], "shape": "brick"}, Region((100, 200, 300, 600)))
        self.assertEqual((d["family"], d["size"], d["color"], d["plain"]), ("brick", "1x2", "orange", True))
        self.assertEqual(d["region"]["point"], [200, 300])
        self.assertEqual(d["confidence"], 1.0)
        odd = to_detection({"family": "thing", "color": "grey", "plain": "yes", "at": "middle"}, Region((0, 0, 9, 9)))
        self.assertEqual((odd["family"], odd["color"], odd["plain"], odd["region"]["point"]), ("unknown", "unknown", False, None))


if __name__ == "__main__":
    unittest.main()
