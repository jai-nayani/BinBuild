"""The sample's outlines come from the matching recorded SAM requests."""

import copy
import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from PIL import Image

from backend import inventory_db, sample_bin
from backend.inventory_pipeline import to_detection
from backend.segmenter import Region


REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "tests" / "fixtures"


class SampleOutlines(unittest.TestCase):
    def test_verified_pieces_have_recorded_outlines_inside_the_photo(self):
        manifest = sample_bin.manifest()
        recording = json.loads((FIXTURES / "kit-batch-recorded.json").read_text())
        top = next(p for p in manifest["photos"] if p["view"] == "top")
        with Image.open(sample_bin.SAMPLE_DIR / top["file"]) as image:
            width, height = image.size
        sample_region = Region((0, 0, width, height), whole_photo=True)
        self.assertEqual(len(manifest["detections"]), len(recording["reply"]["pieces"]))
        self.assertGreaterEqual(sum("mask" in d["region"] for d in manifest["detections"]), 45)
        for detection, piece in zip(manifest["detections"], recording["reply"]["pieces"]):
            without_mask = copy.deepcopy(detection)
            mask = without_mask["region"].pop("mask", None)
            self.assertEqual(without_mask, to_detection(piece, sample_region))
            if mask:
                x0, y0, x1, y1 = mask["box"]
                self.assertTrue(0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height)
                self.assertTrue(mask["path"])
                self.assertTrue(all(n > 0 for n in mask["size"]))
        fields = ("family", "shape", "size", "color", "plain")
        corrections = [{"piece": r["piece"], "fix": {k: r[k] for k in fields}}
                       for r in recording["review"]]
        self.assertEqual(manifest["corrections"], corrections)

    def test_rebuild_without_source_photo_and_reject_changed_prompts(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            manifest_file = folder / "kit.json"
            manifest_file.write_text(json.dumps(sample_bin.manifest(), indent=1) + "\n")
            before = manifest_file.read_bytes()
            self.assertEqual(sample_bin.outlines(manifest_file, source=folder / "missing.jpg"), 50)
            self.assertEqual(manifest_file.read_bytes(), before, "rebuilding is repeatable without a model call")

            bad = json.loads((FIXTURES / "kit-batch-sam-recorded.json").read_text())
            bad["sam"][0]["points"][0][1] += 1
            bad_file = folder / "bad-sam.json"
            bad_file.write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError, "point prompts"):
                sample_bin.outlines(manifest_file, sam_recorded=bad_file, source=folder / "missing.jpg")
            self.assertEqual(manifest_file.read_bytes(), before, "a mismatch never modifies the sample")

    def test_loading_preserves_outlines_without_creating_clients(self):
        from backend.sam_client import SamClient
        from backend.spark_client import SparkClient
        from backend.wonder_client import WonderClient

        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(SamClient, "from_env", side_effect=AssertionError("SAM call")), \
             mock.patch.object(SparkClient, "from_env", side_effect=AssertionError("Spark call")), \
             mock.patch.object(WonderClient, "from_env", side_effect=AssertionError("Wonder call")), \
             closing(inventory_db.connect(Path(tmp) / "sample.db")) as conn:
            sample_bin.load(conn, Path(tmp) / "data")
            review = inventory_db.batch_review(conn, sample_bin.BATCH_ID)
            self.assertGreaterEqual(sum(bool(d["region"].get("mask")) for d in review["detections"]), 45)
            self.assertIn("recorded SAM 3.1 run (Oct 28)", review["batch"]["classifier"])
            self.assertIn("no model call", review["batch"]["classifier"])


if __name__ == "__main__":
    unittest.main()
