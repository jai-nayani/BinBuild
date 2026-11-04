"""Two identification requests and their fallback, with fakes only."""

import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from backend import full_loop
from backend.sam_client import SamError
from test_photo_gate import photo_gate, scene
from test_sam import FakeSam, FakeTiles
import test_sam


REPO = Path(__file__).resolve().parent.parent
HARNESS = REPO / "tests" / "retake_popup_harness.js"
VIEWS = ("top", "front", "right", "back", "left")


def play(flow):
    notices = {v: photo_gate.retake_notice(v, ["blurry"]) for v in VIEWS}
    command = [shutil.which("node"), str(HARNESS), json.dumps({"notices": notices, "fail": [], "identify_flow": flow})]
    out = subprocess.run(command, capture_output=True, text=True, timeout=30, check=True)
    return json.loads(out.stdout)["ui"]["identify_flow"]


class TestSamPhoneFlow(unittest.TestCase):
    def test_stub_then_sam_and_real_report(self):
        review = {
            "batch": {"id": "b1", "status": "classified"}, "pieces": 1, "photos_ready": True,
            "count_photo": {"url": "/photo", "width": 100, "height": 100},
            "detections": [{"id": 1, "status": "proposed", "source": "spark", "family": "brick",
                            "shape": "brick", "size": "1x2", "color": "red", "plain": True, "count": 1,
                            "region": {"point": [5, 5], "mask": {"path": "M0 0L1 1Z", "box": [0, 0, 10, 10],
                                                                    "size": [10, 10]}}}],
        }
        ui = play({"review": review})
        self.assertEqual([r["path"] for r in ui["requests"]], [
            "/api/inventory/batch/b1/classify?segmenter=stub", "/api/inventory/batch/b1/classify?segmenter=sam"])
        self.assertEqual([[s["state"] for s in r["tracker"]] for r in ui["requests"]], [
            ["active", "waiting", "waiting"], ["done", "active", "waiting"]])
        self.assertEqual(ui["requests"][1]["tracker"][0]["detail"], "found 2 pieces · 3.5 s")
        self.assertEqual([s["detail"] for s in ui["tracker"]], [
            "found 2 pieces · 3.5 s", "2 of 2 cut out · 1.2 s", "4.5 s"])
        self.assertEqual(ui["review_tracker"], ui["tracker"])
        self.assertEqual(ui["view"], ["check-view"])
        self.assertEqual(ui["status"], "SAM 3.1 cut out 2 of 2 pieces in 1.2 s.")
        self.assertIn("cut out by SAM 3.1", ui["caption"])

    def test_failed_sam_still_opens_whole_photo_review(self):
        for status in (502, 503):
            with self.subTest(status=status):
                ui = play({"sam_status": status})
                self.assertEqual(ui["view"], ["check-view"])
                self.assertEqual(ui["status"], "SAM 3.1 failed, so these are Spark's whole-photo pieces: SAM service unavailable")
                self.assertEqual(len(ui["requests"]), 2)
                self.assertEqual([s["state"] for s in ui["tracker"]], ["done", "failed", "failed"])

    def test_existing_identification_has_no_invented_counts_or_times(self):
        ui = play({"stub_body": {"pieces": 2}, "sam_body": {"pieces": 2}})
        self.assertEqual([s["detail"] for s in ui["tracker"]], ["already identified"] * 3)

    def test_missing_timings_are_not_filled_in(self):
        ui = play({"stub_body": {"pieces": 2, "run": {"calls": [{}]}},
                   "sam_body": {"pieces": 2, "run": {"sam_pass": {"masks": 1, "points": 2}}}})
        self.assertEqual([s["detail"] for s in ui["tracker"]], ["found 2 pieces", "1 of 2 cut out", "Done"])

    def test_tracker_names_the_actual_primary_backup_or_mixed_models(self):
        meta, baseten = "muse-spark-1.3", "meta-models/muse-spark-open-1026"
        for models, fallbacks, label in (([meta], 0, "Muse Spark 1.3"),
                                         ([baseten], 1, "Baseten backup"),
                                         ([meta, baseten], 1, "Muse Spark 1.3 + Baseten backup"),
                                         ([baseten], 0, "Muse Spark Open (Baseten)")):
            with self.subTest(models=models, fallbacks=fallbacks):
                report = {"answered_by": models, "fallbacks": fallbacks, "reasons": []}
                ui = play({"stub_body": {"pieces": 21, "run": {"calls": [{"seconds": 38}], "spark": report}},
                           "sam_body": {"pieces": 21, "run": {"sam_pass": {
                               "masks": 21, "points": 21, "sam": {"seconds": 1.2},
                               "spark_tiles": {"seconds": 7}, "spark": report}}}})
                self.assertEqual(ui["tracker"][0]["detail"], "found 21 pieces · 38 s · " + label)
                self.assertEqual(ui["tracker"][1]["detail"], "21 of 21 cut out · 1.2 s")
                self.assertEqual(ui["tracker"][2]["detail"], "7 s · " + label)


class TestSamSplitApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.photos = []
        for n in range(1, 6):
            output = io.BytesIO()
            scene(seed=710 + n).save(output, "JPEG", quality=92)
            cls.photos.append((f"{n}.jpg", output.getvalue()))

    def run_passes(self, sam):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        spark = FakeTiles(pieces=test_sam.TestRefineWithSam.PIECES)
        with full_loop.server(tmp.name, spark, sam) as api:
            status, up = api.call("POST", "/api/inventory/batch", files=self.photos)
            self.assertEqual(status, 201, up)
            path = f"/api/inventory/batch/{up['batch_id']}"
            status, whole = api.call("POST", path + "/classify?segmenter=stub")
            self.assertEqual(status, 200, whole)
            status, refined = api.call("POST", path + "/classify?segmenter=sam")
            review_status, review = api.call("GET", path + "/review")
            self.assertEqual(review_status, 200, review)
        return spark, whole, status, refined, review

    def test_split_pass_adds_masks(self):
        spark, whole, status, refined, review = self.run_passes(FakeSam(r=12))
        self.assertEqual(status, 200, refined)
        self.assertEqual((spark.calls, spark.tile_calls), (1, 1))
        self.assertEqual(refined["run"]["sam_pass"]["masks"], len(whole["detections"]))
        self.assertTrue(all(d["region"]["mask"]["path"] for d in review["detections"]))

    def test_sam_failure_keeps_the_whole_photo_proposals(self):
        class BrokenSam:
            model = "broken-sam"
            def segment_points(self, *args):
                raise SamError("offline failure")

        spark, whole, status, refined, review = self.run_passes(BrokenSam())
        self.assertEqual(status, 502)
        self.assertIn("whole-photo proposals are kept", refined["detail"])
        self.assertEqual(review["detections"], whole["detections"])
        self.assertEqual((spark.calls, spark.tile_calls), (1, 0))

    def test_missing_sam_key_is_clear_before_a_sam_call(self):
        spark, whole, status, refined, review = self.run_passes(None)
        self.assertEqual(status, 503)
        self.assertIn("SAM 3.1 is not set up", refined["detail"])
        self.assertEqual(review["detections"], whole["detections"])
        self.assertEqual((spark.calls, spark.tile_calls), (1, 0))
