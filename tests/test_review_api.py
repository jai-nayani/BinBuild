"""Review-screen API tests: what the phone's "Check the pieces" screen calls.

- the batch list (so a batch waiting for review is found after a reload);
- the counted photo, upright and scaled down, with its upright size so the
  piece points land on the pieces (also for a photo with an EXIF rotation);
- the vocabulary for the fix form;
- the screen's own sequence: fix a whole row, fix one piece, remove and put
  back, add a missed piece, accept the rest, confirm, undo, and undo refused
  for an older batch.

Standard-library unittest; needs the backend requirements (else skipped).
Run from the repo root:  python3 -m unittest discover -s tests -v
"""

import io
import tempfile
import unittest
import urllib.request
from unittest import mock

from backend import inventory_db as db

try:
    from PIL import Image
    from test_photo_gate import scene
    from backend import full_loop
    import uvicorn  # noqa: F401
    HAVE_SERVER = True
except ImportError:
    HAVE_SERVER = False


def jpeg(img, orientation=None):
    out = io.BytesIO()
    if orientation:
        exif = Image.Exif()
        exif[0x0112] = orientation
        img.save(out, "JPEG", quality=92, exif=exif)
    else:
        img.save(out, "JPEG", quality=92)
    return out.getvalue()


def piece(family, shape, size, color, plain, at):
    return {"family": family, "shape": shape, "size": size, "color": color, "plain": plain, "confidence": 0.9, "at": at}


PIECES = [
    piece("brick", "brick", "1x2", "lime", True, [0.1, 0.1]),   # really a tall 1x1 with side studs
    piece("brick", "brick", "1x2", "lime", True, [0.2, 0.1]),
    piece("plate", "plate", "1x3", "trans_clear", True, [0.3, 0.2]),
    piece("plate", "plate", "1x3", "trans_clear", True, [0.4, 0.2]),
    piece("brick", "brick", "1x2", "orange", True, [0.5, 0.5]),
    piece("tile", "tile", "1x2", "black", True, [0.9, 0.9]),    # not a piece: removed in review
]


@unittest.skipUnless(HAVE_SERVER, "FastAPI, uvicorn or Pillow not installed")
class TestReviewScreenApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.spark = full_loop.ReplaySpark({"reply": {"checks": [{"image": n, "real_lego": "yes"} for n in range(1, 6)],
                                                     "pieces": PIECES, "total": len(PIECES)},
                                           "recorded": {"finish_reason": "stop"}})
        cls.ctx = full_loop.server(cls.tmp.name, cls.spark)
        cls.api = cls.ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)
        cls.tmp.cleanup()

    def new_batch(self, seed, top_orientation=None):
        """Upload 5 drawn photos (the top one landscape, optionally with an
        EXIF rotation) and classify them with the canned reply."""
        photos = [(f"{n}-v.jpg", jpeg(scene(seed=seed + n), top_orientation if n == 1 else None)) for n in range(1, 6)]
        status, up = self.api.call("POST", "/api/inventory/batch", files=photos)
        self.assertEqual((status, up["ready"]), (201, True), up)
        status, cls = self.api.call("POST", f"/api/inventory/batch/{up['batch_id']}/classify")
        self.assertEqual(status, 200, cls)
        return up["batch_id"]

    def review(self, batch_id, **payload):
        status, body = self.api.call("POST", f"/api/inventory/batch/{batch_id}/review", json_body=payload)
        self.assertEqual(status, 200, body)
        return body

    def photo(self, url):
        with urllib.request.urlopen(self.api.base + url, timeout=30) as r:
            return r.headers["Content-Type"], Image.open(io.BytesIO(r.read()))

    def test_counted_photo_and_points(self):
        batch = self.new_batch(200)
        status, rev = self.api.call("GET", f"/api/inventory/batch/{batch}/review")
        self.assertEqual(status, 200)
        photo = rev["count_photo"]
        self.assertEqual((photo["view"], photo["width"], photo["height"]), ("top", 2016, 1512))
        kind, img = self.photo(photo["url"])
        self.assertEqual((kind, img.format, max(img.size)), ("image/jpeg", "JPEG", 1600))
        self.assertAlmostEqual(img.size[0] / img.size[1], 2016 / 1512, places=2)
        # Spark's points are in the upright full-size frame: "at" 0.5, 0.5 -> the middle
        orange = next(d for d in rev["detections"] if d["color"] == "orange")
        self.assertEqual(orange["region"]["point"], [1008, 756])

    def test_rotated_photo_is_served_upright(self):
        batch = self.new_batch(210, top_orientation=6)  # stored landscape, shown portrait
        status, rev = self.api.call("GET", f"/api/inventory/batch/{batch}/review")
        photo = rev["count_photo"]
        self.assertEqual((photo["width"], photo["height"]), (1512, 2016))
        _, img = self.photo(photo["url"].split("?")[0] + "?size=400")
        self.assertEqual(img.size, (300, 400))
        self.assertEqual(self.api.call("GET", f"/api/inventory/batch/{batch}/photos/side")[0], 404)
        self.assertEqual(self.api.call("GET", "/api/inventory/batch/nope/photos/top")[0], 404)

    def test_vocab(self):
        status, vocab = self.api.call("GET", "/api/inventory/vocab")
        self.assertEqual(status, 200)
        self.assertIn("window_door", vocab["families"])
        self.assertIn({"name": "lime", "hex": "#b8e21e"}, vocab["colors"])
        self.assertEqual(len(vocab["generator_types"]), 8)
        self.assertIn("curved slope", vocab["shapes"])

    def test_the_screens_sequence(self):
        batch = self.new_batch(220)
        status, listed = self.api.call("GET", "/api/inventory/batches")
        row = next(b for b in listed["batches"] if b["id"] == batch)
        self.assertEqual((row["status"], row["pieces"], row["photos_passed"], row["undoable"]),
                         ("classified", 6, 5, False))
        status, rev = self.api.call("GET", f"/api/inventory/batch/{batch}/review")
        d = rev["detections"]
        lime, clear, orange, tile = [d[0]["id"], d[1]["id"]], [d[2]["id"], d[3]["id"]], d[4]["id"], d[5]["id"]

        # "Fix all 2": the lime row becomes tall 1x1 bricks with side studs, not generator-ready
        fixed = {"family": "brick", "shape": "tall 1x1 brick with 2 studs on side", "size": "1x1", "color": "lime",
                 "plain": False}
        body = self.review(batch, corrections=[dict(fixed, detection_id=i) for i in lime])
        self.assertEqual({x["generator_type"] for x in body["detections"] if x["id"] in lime}, {None})
        # "One by one" -> fix just one of the clear plates
        self.review(batch, corrections=[{"detection_id": clear[0], "family": "plate", "shape": "plate", "size": "1x2",
                                         "color": "trans_clear", "plain": True}])
        # "Remove", "Put back", "Remove" the tile
        self.review(batch, corrections=[{"detection_id": tile, "status": "rejected"}])
        body = self.review(batch, corrections=[{"detection_id": tile, "status": "accepted"}])
        self.assertEqual(next(x["status"] for x in body["detections"] if x["id"] == tile), "accepted")
        body = self.review(batch, corrections=[{"detection_id": tile, "status": "rejected"}])
        self.assertEqual(body["pieces"], 5)
        # "Add a piece Spark missed": 2 at once
        body = self.review(batch, additions=[{"family": "plate", "shape": "plate", "size": "1x4", "color": "green",
                                              "plain": True, "count": 2}])
        self.assertEqual(body["pieces"], 7)
        # "Add to my inventory": untouched pieces accepted first, then confirm
        untouched = [x["id"] for x in body["detections"] if x["status"] == "proposed"]
        self.assertEqual(untouched, [clear[1], orange])
        self.review(batch, corrections=[{"detection_id": i, "status": "accepted"} for i in untouched])
        status, conf = self.api.call("POST", f"/api/inventory/batch/{batch}/confirm")
        self.assertEqual((status, conf["pieces_in_batch"]), (200, 7))
        items = {(i["family"], i["shape"], i["size"], i["color"]): i["quantity"]
                 for i in conf["summary"]["items"]}
        self.assertEqual(items[("brick", "tall 1x1 brick with 2 studs on side", "1x1", "lime")], 2)
        self.assertEqual(items[("plate", "plate", "1x2", "trans_clear")], 1)
        self.assertEqual(items[("plate", "plate", "1x3", "trans_clear")], 1)
        self.assertEqual(items[("plate", "plate", "1x4", "green")], 2)
        self.assertNotIn(("tile", "tile", "1x2", "black"), items)
        # the review is locked once confirmed
        status, _ = self.api.call("POST", f"/api/inventory/batch/{batch}/review",
                                  json_body={"corrections": [{"detection_id": orange, "status": "rejected"}]})
        self.assertEqual(status, 409)

        # a newer batch confirmed after it: undoing the older one is refused
        newer = self.new_batch(230)
        self.assertEqual(self.api.call("POST", f"/api/inventory/batch/{newer}/confirm")[0], 200)
        status, listed = self.api.call("GET", "/api/inventory/batches")
        undoable = [b["id"] for b in listed["batches"] if b["undoable"]]
        self.assertEqual(undoable, [newer])
        self.assertEqual(self.api.call("POST", f"/api/inventory/undo-last-batch?batch_id={batch}")[0], 409)
        status, undo = self.api.call("POST", f"/api/inventory/undo-last-batch?batch_id={newer}")
        self.assertEqual((status, undo["pieces_removed"]), (200, 6))
        status, rev = self.api.call("GET", f"/api/inventory/batch/{newer}/review")
        self.assertEqual(rev["batch"]["status"], "classified")  # open for review again


class TestListBatches(unittest.TestCase):
    def test_states(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(db, "DB_PATH", f"{tmp}/t.db"):
            conn = db.connect()
            photos = lambda tag: [{"view": v, "file": f"{v}.jpg", "bytes": 1, "sha256": f"{tag}{v}",  # noqa: E731
                                   "gate": {"passed": True, "reasons": [], "metrics": {}}}
                                  for v in ("top", "front", "right", "back", "left")]
            db.register_batch(conn, "20261029-000001-aaaaaa", "2026-10-29T00:00:01", photos("a"))
            db.register_batch(conn, "20261029-000002-bbbbbb", "2026-10-29T00:00:02", photos("b"))
            db.replace_detections(conn, "20261029-000002-bbbbbb", [
                {"family": "brick", "size": "1x2", "color": "red", "plain": True, "count": 3},
                {"family": "plate", "size": "1x2", "color": "red", "count": 1}], "test")
            first = db.batch_review(conn, "20261029-000002-bbbbbb")["detections"][1]["id"]
            db.review_batch(conn, "20261029-000002-bbbbbb", corrections=[{"detection_id": first, "status": "rejected"}])
            rows = {b["id"]: b for b in db.list_batches(conn)}
            self.assertEqual(list(rows), ["20261029-000002-bbbbbb", "20261029-000001-aaaaaa"])  # newest first
            self.assertEqual((rows["20261029-000002-bbbbbb"]["status"], rows["20261029-000002-bbbbbb"]["pieces"]),
                             ("classified", 3))
            self.assertEqual((rows["20261029-000001-aaaaaa"]["status"], rows["20261029-000001-aaaaaa"]["pieces"]),
                             ("uploaded", 0))
            self.assertFalse(any(b["undoable"] for b in rows.values()))
            db.confirm_batch(conn, "20261029-000002-bbbbbb")
            self.assertTrue(db.list_batches(conn)[0]["undoable"])
            conn.close()


if __name__ == "__main__":
    unittest.main()
