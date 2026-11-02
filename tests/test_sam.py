"""SAM 3.1 tests: the Model API client, the segmenter, the SAM pass, and the
full loop with it. No Model API or Baseten call: SAM replies are built with
the mask encoder in Meta's own parser package (meta-sam-parser), or played
back from the recorded kit-batch run.

- client: the documented request (model sam-3.1, /v1/responses, Bearer key,
  point tokens in pixels of the image sent); replies parsed with Meta's
  parser (one_bit built here, lossless recorded live); the key from .env,
  a clear error without it, never in an error message; at most 16 points;
- segmenter: 16 points per request, boxes back in the upright photo's
  pixels, a point with no mask still gets a region;
- SAM pass: one proposal per point named from its close-up, the whole-photo
  label kept where SAM found nothing, two points on one piece flagged, the
  whole-photo labels sent as hints, refused once reviewed or confirmed, and
  nothing sent while a photo needs a retake;
- full loop with SAM (recorded replies) on the real kit batch, when on disk.

Standard-library unittest. Run from the repo root:
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

try:
    from meta_sam_parser._mask_codec import _encode_raster  # Meta's encoder, to build realistic replies
    from backend import sam_client as sc
    HAVE_PARSER = True
except ImportError:
    HAVE_PARSER = False

try:
    from PIL import Image
    from backend import inventory_pipeline as ip
    from backend.segmenter import SamSegmenter, WholePhotoSegmenter
    from test_photo_gate import KIT, FakeSpark, scene
    HAVE_PILLOW = HAVE_PARSER
except ImportError:
    HAVE_PILLOW = False
    FakeSpark = object  # the classes below still define; their tests are skipped

try:
    import uvicorn  # noqa: F401
    from backend import full_loop
    from test_full_loop import KIT_ITEMS
    HAVE_SERVER = HAVE_PILLOW
except ImportError:
    HAVE_SERVER = False

REPO = Path(__file__).resolve().parent.parent
SAM_RECORDED = REPO / "tests" / "fixtures" / "kit-batch-sam-recorded.json"
RECORDED = REPO / "tests" / "fixtures" / "kit-batch-recorded.json"
VIEWS = ("top", "front", "right", "back", "left")


def fake_output(points, size, r=20, c=0.9, skip=()):
    """A SAM reply: a round mask of radius r round each (id, x, y) point,
    except ids in skip (SAM found nothing there)."""
    w, h = size
    records = []
    for oid, x, y in points:
        if oid in skip:
            continue
        x0, y0, x1, y1 = max(0, x - r), max(0, y - r), min(w, x + r), min(h, y + r)
        mw, mh = x1 - x0, y1 - y0
        raster = [1 if (i - (x - x0)) ** 2 + (j - (y - y0)) ** 2 <= r * r else 0 for j in range(mh) for i in range(mw)]
        records.append(f"{oid}<|box;x1={x0};y1={y0};x2={x1 - 1};y2={y1 - 1};w={w};h={h};c={c}|>"
                       f"<|mask;x=0;y=0;c={c};data={mh},{mw},{_encode_raster(raster, mw, mh)}|>")
    return "<0f>" + ",".join(records) if records else ""


class FakeSam:
    """Stands in for SamClient: round masks, and a log of what was asked."""

    model = "fake-sam"

    def __init__(self, r=20, skip=()):
        self.r, self.skip, self.requests = r, set(skip), []

    def segment_points(self, image_jpeg, size, points):
        self.requests.append((tuple(size), list(points)))
        text = fake_output(points, size, self.r, skip=self.skip)
        masks, diagnostics = sc.parse_output(text)
        return sc.SamReply(masks, 0.0, {}, text, diagnostics)


class FakeTiles(FakeSpark):
    """FakeSpark that also names close-ups: tile n -> TILE_NAMES[n - 1]."""

    TILE_NAMES = [{"family": "brick", "shape": "brick with studs on side", "size": "1x4", "color": "blue", "plain": False}]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tile_calls, self.hints = 0, []

    def name_tiles(self, sheet_jpeg, count, context=(), hints=None, max_tokens=0):
        self.tile_calls += 1
        self.hints.append(hints)
        tiles = [dict(self.TILE_NAMES[(n - 1) % len(self.TILE_NAMES)], tile=n, confidence=0.9) for n in range(1, count + 1)]
        return {"tiles": tiles}, mock.Mock(seconds=0.0, finish_reason="stop", usage={})


@unittest.skipUnless(HAVE_PARSER, "meta-sam-parser not installed")
class TestSamClient(unittest.TestCase):
    def test_parse_one_bit_reply(self):
        masks, diagnostics = sc.parse_output(fake_output([(0, 100, 120), (5, 300, 40)], (640, 480)))
        self.assertEqual(diagnostics, [])
        self.assertEqual(sorted(masks), [0, 5])
        m = masks[0]
        self.assertEqual((m.box, m.width, m.height, m.confidence), ((80, 100, 120, 140), 40, 40, 0.9))
        self.assertEqual(len(m.raster), 40 * 40)
        self.assertTrue(1200 < m.area < 1300)  # a disc of radius 20
        self.assertTrue(sc.outline(m).startswith("M"))

    def test_parse_recorded_lossless_reply(self):
        recorded = json.loads(SAM_RECORDED.read_text())["sam"][0]
        masks, diagnostics = sc.parse_output(recorded["output"])
        self.assertEqual((sorted(masks), diagnostics), (list(range(16)), []))
        for m in masks.values():
            self.assertEqual(len(m.raster), m.width * m.height)
            self.assertTrue(0 <= m.box[0] < m.box[2] <= 1536 and 0 <= m.box[1] < m.box[3] <= 2048)
            self.assertGreater(m.confidence, 0.5)

    def test_simplify_path(self):
        self.assertEqual(sc.simplify_path("M0 0L1 0L2 0L2 1L2 2L1 2L0 2L0 1Z"), "M0 0L2 0L2 2L0 2L0 1Z")

    def test_key_from_env_file_only_and_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {}, clear=True):
            env = Path(tmp) / ".env"
            with self.assertRaises(sc.SamError) as caught:
                sc.load_api_key(env)
            self.assertIn("META_MODEL_API_KEY", str(caught.exception))
            env.write_text("BASETEN_API_KEY=other\nMODEL_API_KEY=docs-name\n")
            self.assertEqual(sc.load_api_key(env), "docs-name")
            env.write_text("META_MODEL_API_KEY='ours'\nMODEL_API_KEY=docs-name\n")
            self.assertEqual(sc.load_api_key(env), "ours")
            self.assertNotIn("ours", repr(sc.SamClient.from_env(env)))

    def test_request_is_the_documented_one(self):
        sent = {}

        class Reply(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def urlopen(request, timeout):
            sent.update(url=request.full_url, auth=request.get_header("Authorization"), body=json.loads(request.data))
            text = fake_output([(3, 10, 12)], (64, 48), r=5)
            return Reply(json.dumps({"output": [{"type": "message", "content": [
                {"type": "output_text", "text": text}]}], "usage": {"images_processed": 1}}).encode())

        client = sc.SamClient("secret-key")
        with mock.patch("urllib.request.urlopen", urlopen):
            reply = client.segment_points(b"\xff\xd8jpeg", (64, 48), [(3, 10, 12)])
        self.assertEqual(sent["url"], "https://api.meta.ai/v1/responses")
        self.assertEqual(sent["auth"], "Bearer secret-key")
        self.assertEqual(sent["body"]["model"], "sam-3.1")
        content = sent["body"]["input"][0]["content"]
        self.assertEqual(content[0], {"type": "input_text", "text": "<0f>3<|point;x=10;y=12;w=64;h=48|>"})
        self.assertTrue(content[1]["image_url"].startswith("data:image/jpeg;base64,"))
        self.assertEqual((sorted(reply.masks), reply.usage, client.requests), ([3], {"images_processed": 1}, 1))

    def test_errors_never_contain_the_key(self):
        def urlopen(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 401, "no", {}, io.BytesIO(b"bad key secret-key"))
        with mock.patch("urllib.request.urlopen", urlopen):
            with self.assertRaises(sc.SamError) as caught:
                sc.SamClient("secret-key", retries=0).segment_points(b"x", (64, 48), [(0, 1, 1)])
        self.assertNotIn("secret-key", str(caught.exception))
        self.assertIn("HTTP 401", str(caught.exception))

    def test_at_most_16_points(self):
        with self.assertRaises(ValueError):
            sc.SamClient("k").segment_points(b"x", (64, 48), [(i, 1, 1) for i in range(17)])


@unittest.skipUnless(HAVE_PILLOW, "Pillow or meta-sam-parser not installed")
class TestSamSegmenter(unittest.TestCase):
    def test_chunks_scale_and_missing_masks(self):
        image = Image.new("RGB", (4032, 3024), (30, 30, 30))
        points = [(100 + 90 * i, 200 + 60 * (i % 7)) for i in range(40)]
        sam = FakeSam(r=10, skip={5})
        regions = SamSegmenter(sam, points).segment(image)
        sam.requests.sort(key=lambda r: r[1][0][0])  # the requests go in parallel
        self.assertEqual([len(p) for _, p in sam.requests], [16, 16, 8])
        self.assertEqual({size for size, _ in sam.requests}, {(2048, 1536)})
        self.assertEqual([p[0] for p in sam.requests[1][1]][:2], [16, 17])  # ids are point numbers
        self.assertEqual(len(regions), 40)
        r = regions[0]  # point (100, 200) -> SAM frame (50, 101) -> a 20 px box -> ~40 px in the photo
        self.assertEqual(r.point, (100.0, 200.0))
        self.assertTrue(r.bbox[0] <= 100 <= r.bbox[2] and r.bbox[1] <= 200 <= r.bbox[3])
        self.assertTrue(35 <= r.bbox[2] - r.bbox[0] <= 45)
        self.assertIsNone(regions[5].mask)
        self.assertEqual(regions[5].score, 0.0)


@unittest.skipUnless(HAVE_PILLOW, "Pillow or meta-sam-parser not installed")
class TestRefineWithSam(unittest.TestCase):
    PIECES = [
        {"family": "brick", "size": "1x4", "color": "blue", "plain": True, "at": [0.2, 0.2]},
        {"family": "brick", "size": "1x4", "color": "blue", "plain": True, "at": [0.6, 0.6]},
        {"family": "brick", "size": "1x4", "color": "blue", "plain": True, "at": [0.602, 0.601]},  # same piece again
        {"family": "plate", "size": "1x1", "color": "lime", "plain": False, "at": [0.8, 0.3]},
    ]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.conn = db.connect(self.dir / "t.db")
        photos = []
        for n, view in enumerate(VIEWS, 1):
            scene(seed=300 + n).save(self.dir / f"{n}-{view}.jpg", quality=90)
            photos.append({"view": view, "file": f"{n}-{view}.jpg", "bytes": 1, "sha256": f"s{n}",
                           "gate": {"passed": True, "reasons": [], "metrics": {}}})
        self.batch = "20261029-010101-abcdef"
        db.register_batch(self.conn, self.batch, "2026-10-29T01:01:01", photos)
        self.spark = FakeTiles(pieces=self.PIECES)
        ip.classify_batch(self.conn, self.batch, self.dir, WholePhotoSegmenter(), self.spark)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def detections(self):
        return sorted(db.batch_review(self.conn, self.batch)["detections"], key=lambda d: d["id"])

    def test_one_proposal_per_point_named_from_its_close_up(self):
        sam = FakeSam(r=12, skip={3})
        report = ip.refine_with_sam(self.conn, self.batch, self.dir, sam, self.spark, out_dir=self.dir)
        self.assertEqual((report["points"], report["masks"], report["pieces"]), (4, 3, 4))
        self.assertEqual(report["no_mask"], [4])
        self.assertEqual(report["same_piece"], {3: 2})
        self.assertEqual(report["kept_whole_photo_label"], [4])
        self.assertEqual(self.spark.calls, 1)  # the whole-photo pass only; the SAM pass adds tile calls
        self.assertEqual(self.spark.tile_calls, 1)
        d = self.detections()
        self.assertEqual([(x["shape"], x["plain"], x["generator_type"]) for x in d[:3]],
                         [("brick with studs on side", False, None)] * 3)
        self.assertEqual((d[3]["family"], d[3]["size"], d[3]["color"]), ("plate", "1x1", "lime"))  # kept
        self.assertEqual(d[2]["raw"]["sam"]["same_piece_as"], 2)
        self.assertTrue(d[0]["region"]["mask"]["path"].startswith("M"))
        self.assertEqual({x["status"] for x in d}, {"proposed"})  # nothing confirmed
        self.assertTrue((self.dir / "sheet-1.jpg").is_file() and (self.dir / "masks.jpg").is_file())

    def test_whole_photo_labels_go_as_hints(self):
        ip.refine_with_sam(self.conn, self.batch, self.dir, FakeSam(), self.spark)
        self.assertEqual(self.spark.hints[0][0], "blue 1x4 brick (brick, plain)")
        self.assertEqual(len(self.spark.hints[0]), 4)
        from backend.spark_client import tile_prompt
        self.assertIn("The first pass said:\n- tile 1: blue 1x4 brick", tile_prompt(4, False, self.spark.hints[0]))

    def test_refused_after_review_or_confirm(self):
        first = self.detections()[0]["id"]
        db.review_batch(self.conn, self.batch, corrections=[{"detection_id": first, "status": "rejected"}])
        sam = FakeSam()
        with self.assertRaises(db.Conflict):
            ip.refine_with_sam(self.conn, self.batch, self.dir, sam, self.spark)
        db.confirm_batch(self.conn, self.batch)
        with self.assertRaises(db.Conflict):
            ip.refine_with_sam(self.conn, self.batch, self.dir, sam, self.spark)
        self.assertEqual(sam.requests, [])

    def test_nothing_sent_while_a_photo_needs_a_retake(self):
        db.set_photo_gate(self.conn, self.batch, "left", {"passed": False, "reasons": ["blurry"], "metrics": {}})
        sam = FakeSam()
        with self.assertRaises(db.PhotosNotReady):
            ip.refine_with_sam(self.conn, self.batch, self.dir, sam, self.spark)
        self.assertEqual((sam.requests, self.spark.tile_calls), ([], 0))


@unittest.skipUnless(HAVE_SERVER, "FastAPI, uvicorn, Pillow or meta-sam-parser not installed")
class TestSamThroughTheApi(unittest.TestCase):
    def test_no_key_is_a_clear_error_before_any_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            spark = FakeTiles()
            with full_loop.server(tmp, spark) as api:  # no SAM given: as if the key were missing
                photos = [(f"{n}.jpg", self.jpeg(scene(seed=400 + n))) for n in range(1, 6)]
                status, up = api.call("POST", "/api/inventory/batch", files=photos)
                status, body = api.call("POST", f"/api/inventory/batch/{up['batch_id']}/classify?segmenter=sam")
                self.assertEqual(status, 503)
                self.assertIn("SAM 3.1 is not set up", body["detail"])
                self.assertEqual((spark.calls, spark.tile_calls), (0, 0))
                status, body = api.call("POST", f"/api/inventory/batch/{up['batch_id']}/classify?segmenter=nope")
                self.assertEqual(status, 422)

    @staticmethod
    def jpeg(img):
        out = io.BytesIO()
        img.save(out, "JPEG", quality=92)
        return out.getvalue()

    def test_replayed_sam_refuses_other_points(self):
        sam = full_loop.ReplaySam(json.loads(SAM_RECORDED.read_text())["sam"])
        with self.assertRaises(sc.SamError):
            sam.segment_points(b"x", (1536, 2048), [(0, 1, 1)])

    @unittest.skipUnless((KIT / "batch.json").is_file() if HAVE_PILLOW else False, "kit batch not on disk")
    def test_full_loop_with_sam_on_the_real_kit_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = full_loop.run(KIT, json.loads(RECORDED.read_text()), Path(tmp),
                                   sam_recorded=json.loads(SAM_RECORDED.read_text()))
        stages = {s["stage"].split(".")[0]: s for s in report["stages"]}
        self.assertEqual((stages["2"]["sam_requests"], stages["2"]["masks"], stages["2"]["points"]), (4, 50, 50))
        self.assertEqual((stages["2"]["no_mask"], stages["2"]["same_piece"]), ([], {}))
        self.assertEqual(stages["3"]["corrected_pieces"], [7, 8, 17, 28, 30, 31, 35, 40, 41, 46, 47])
        self.assertEqual(stages["3"]["confirmed"], 50)
        rows = lambda items: sorted(tuple(sorted(i.items())) for i in items)  # noqa: E731
        self.assertEqual(rows(report["summary"]["items"]), rows(KIT_ITEMS))
        self.assertEqual((report["known_set"]["status"], report["brickgpt"]["status"]), ("fit", "short"))

    @unittest.skipUnless((KIT / "batch.json").is_file() if HAVE_PILLOW else False, "kit batch not on disk")
    def test_full_loop_without_sam_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = full_loop.run(KIT, json.loads(RECORDED.read_text()), Path(tmp))
        stages = {s["stage"].split(".")[0]: s for s in report["stages"]}
        self.assertEqual(stages["3"]["corrected_pieces"], [7, 8, 12, 17, 28, 30, 31, 35, 40, 41, 46, 47, 49])


if __name__ == "__main__":
    unittest.main()
