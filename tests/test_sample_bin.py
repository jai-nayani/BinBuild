"""The sample bin and the empty-bin gate on "What can I build?".

- gate: with no confirmed pieces (nothing scanned and confirmed, the sample
  not loaded, or loaded but not confirmed yet) the build list exposes zero
  catalog entries, only a scan prompt; once pieces are confirmed it lists
  every build again;
- sample: "Use sample images" (POST /api/inventory/sample) loads the Oct 28
  kit batch's 5 photos and its verified pieces as one batch ready for review,
  with no access key on the public deploy and without creating any Spark, SAM
  or Wonder client, even on a fresh deploy whose database folder doesn't
  exist yet; the review's 13 corrections are applied; loading twice is
  the same batch, and its pieces are never added twice; after confirm the
  inventory is exactly the kit's 50 pieces;
- assets: exactly 5 small JPEGs with no camera metadata, matching the
  manifest; the repo tracks no other photos;
- the app (the real app.js in Node, tests/retake_popup_harness.js): "Use
  sample images" opens "The sample bin: check the pieces"; on an empty bin
  "What can I build?" shows no catalog, only "Scan a handful" and "Use sample
  images".

No Model API call; every database is a temporary one. Standard-library
unittest. Run from the repo root:
    python3 -m unittest discover -s tests -v
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import urllib.request
from collections import Counter
from contextlib import closing
from pathlib import Path
from unittest import mock

from backend import guard
from backend import inventory_db as db
from backend import sample_bin
from test_full_loop import KIT_ITEMS, seed

try:
    import uvicorn  # noqa: F401
    from PIL import Image
    from backend import full_loop, main
    HAVE_SERVER = True
except ImportError:
    HAVE_SERVER = False

try:
    from backend import photo_gate
except ImportError:
    photo_gate = None

REPO = Path(__file__).resolve().parent.parent
HARNESS = Path(__file__).resolve().parent / "retake_popup_harness.js"
NODE = shutil.which("node")
VIEWS = ("top", "front", "right", "back", "left")


def kit_counts(items, qty="quantity"):
    return Counter({(i["family"], i["shape"], i["size"], i["color"]): i[qty] for i in items})


@unittest.skipUnless(HAVE_SERVER, "FastAPI, uvicorn or Pillow not installed")
class TestGateAndSample(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {guard.ACCESS_KEY_ENV: "test-key-not-a-secret"})  # as on the deploy
        self.env.start()
        self.ctx = full_loop.server(self.tmp.name, None)
        self.api = self.ctx.__enter__()
        self.paid = [mock.patch.object(cls, "from_env", side_effect=AssertionError(f"{cls.__name__} was created"))
                     for cls in (main.SamClient, main.WonderClient)]
        self.paid.append(mock.patch.object(main, "make_spark", side_effect=AssertionError("Spark was created")))
        for p in self.paid:
            p.start()

    def tearDown(self):
        for p in self.paid:
            p.stop()
        self.ctx.__exit__(None, None, None)
        self.env.stop()
        self.tmp.cleanup()

    def options(self):
        status, body = self.api.call("GET", "/api/builds/options")
        self.assertEqual(status, 200)
        return body

    def test_no_bin_no_catalog(self):
        body = self.options()
        self.assertEqual(body["options"], [])
        self.assertNotIn("manual", body, "not even the catalog's counts")
        self.assertEqual(body["inventory"]["total_pieces"], 0)
        self.assertIn("Scan a handful", body["scan_first"])

    def test_a_confirmed_batch_opens_the_catalog(self):
        with closing(db.connect()) as conn:
            seed(conn, KIT_ITEMS)
        body = self.options()
        self.assertEqual(len(body["options"]), 116)
        self.assertNotIn("scan_first", body)

    def test_the_sample_loads_with_no_key_and_no_model(self):
        status, body = self.api.call("POST", "/api/inventory/sample")
        self.assertEqual(status, 200, body)
        self.assertEqual((body["batch_id"], body["sample"], body["loaded_now"]), (sample_bin.BATCH_ID, True, True))
        self.assertEqual((body["batch"]["status"], body["pieces"], body["ready"]), ("classified", 50, True))
        self.assertTrue(body["batch"]["classifier"].startswith("sample:"))
        self.assertEqual(sum(d["status"] == "corrected" for d in body["detections"]), 13)
        self.assertEqual(self.options()["options"], [], "loaded is not confirmed: still no catalog")
        status, review = self.api.call("GET", f"/api/inventory/batch/{body['batch_id']}/review")
        self.assertEqual((review["count_photo"]["width"], review["count_photo"]["height"]), (960, 1280))
        with urllib.request.urlopen(self.api.base + review["count_photo"]["url"]) as reply:
            self.assertEqual((reply.status, reply.headers["content-type"]), (200, "image/jpeg"))
            self.assertEqual(reply.read(2), b"\xff\xd8")

    def test_a_fresh_deploy_with_no_database_folder(self):
        # The deploy keeps its database in /tmp/binbuild, empty at every container start: the first
        # write must make the folder (this 500'd on the live demo once the start-up pre-load was gone).
        fresh = Path(self.tmp.name) / "binbuild" / "binbuild.db"
        with mock.patch.object(db, "DB_PATH", fresh):
            self.assertFalse(fresh.parent.exists())
            self.assertEqual(self.options()["options"], [], "reading makes nothing")
            self.assertFalse(fresh.parent.exists())
            status, body = self.api.call("POST", "/api/inventory/sample")
            self.assertEqual((status, body.get("pieces")), (200, 50), body)
            self.assertTrue(fresh.is_file())

    def test_confirm_then_build_and_never_twice(self):
        _, body = self.api.call("POST", "/api/inventory/sample")
        status, again = self.api.call("POST", "/api/inventory/sample")
        self.assertEqual((status, again["batch_id"], again["loaded_now"]), (200, body["batch_id"], False))
        status, done = self.api.call("POST", f"/api/inventory/batch/{body['batch_id']}/confirm")
        self.assertEqual((status, done["pieces_added"]), (200, 50))
        self.api.call("POST", "/api/inventory/sample")
        status, summary = self.api.call("GET", "/api/inventory/summary")
        self.assertEqual(summary["total_pieces"], 50, "the sample's pieces are never added twice")
        self.assertEqual(kit_counts(summary["items"]), kit_counts(KIT_ITEMS))
        built = self.options()
        self.assertEqual(len(built["options"]), 116)
        house = next(o for o in built["options"] if o.get("set") == "house-and-tree")
        self.assertEqual(house["status"], "fit")
        status, info = self.api.call("GET", "/api/inventory/sample")
        self.assertEqual((info["loaded"], info["status"], info["pieces"]), (True, "confirmed", 50))


class TestAssets(unittest.TestCase):
    def test_five_small_photos_without_camera_metadata(self):
        m = sample_bin.manifest()
        self.assertEqual([p["view"] for p in m["photos"]], list(VIEWS))
        files = sorted(p.name for p in sample_bin.SAMPLE_DIR.iterdir())
        self.assertEqual(files, sorted([p["file"] for p in m["photos"]] + ["kit.json"]))
        total = 0
        for p in m["photos"]:
            data = (sample_bin.SAMPLE_DIR / p["file"]).read_bytes()
            total += len(data)
            self.assertEqual(hashlib.sha256(data).hexdigest(), p["sha256"], p["file"])
            self.assertEqual(data[:2], b"\xff\xd8", "a JPEG")
            self.assertNotIn(b"Exif\x00\x00", data, f"{p['file']} carries EXIF (camera, place)")
            self.assertLessEqual(max(p["width"], p["height"]), sample_bin.LONG_EDGE)
        self.assertLess(total, 600 * 1024, "the 5 sample photos stay small")

    def test_the_verified_pieces(self):
        m = sample_bin.manifest()
        self.assertEqual(m["from_batch"], "20261028-192429-119901")
        self.assertNotEqual(m["batch_id"], m["from_batch"], "never the original batch id a real bin may hold")
        self.assertRegex(m["batch_id"], r"^\d{8}-\d{6}-[0-9a-f]{6}$")
        fix = {c["piece"]: c["fix"] for c in m["corrections"]}
        final = Counter()
        for n, d in enumerate(m["detections"]):
            f = {**d, **fix.get(n, {})}
            final[(f["family"], f["shape"], f["size"], f["color"])] += d["count"]
        self.assertEqual(final, kit_counts(KIT_ITEMS), "exactly the kit's 50 verified pieces")
        top = m["photos"][0]
        for d in m["detections"]:
            x, y = d["region"]["point"]
            self.assertTrue(0 <= x <= top["width"] and 0 <= y <= top["height"])

    def test_no_photos_in_the_repo_but_the_sample(self):
        tracked = subprocess.run(["git", "-C", str(REPO), "ls-files", "--cached", "--others", "--exclude-standard"],
                                 capture_output=True, text=True).stdout.split()   # all a commit could include
        if not tracked:
            self.skipTest("not a git checkout")
        photos = [f for f in tracked if re.search(r"\.(jpe?g|heic|heif|webp)$", f, re.I)]
        self.assertEqual(sorted(photos), sorted(f"backend/sample/{p['file']}" for p in sample_bin.manifest()["photos"]))
        self.assertFalse([f for f in tracked if f.startswith("data/") or f.endswith((".db", ".env"))])

    def test_the_deploy_starts_with_an_empty_bin(self):
        text = (REPO / "deploy" / "modal_app.py").read_text()
        self.assertNotIn("seed(", text)
        self.assertFalse((REPO / "backend" / "demo_seed.py").exists())


def play(**scenario):
    notices = {v: photo_gate.retake_notice(v, ["blurry"]) for v in VIEWS}
    out = subprocess.run([NODE, str(HARNESS), json.dumps({"notices": notices, "fail": [], **scenario})],
                         capture_output=True, text=True, timeout=60, check=True)
    return json.loads(out.stdout)


@unittest.skipUnless(NODE and photo_gate, "Node or Pillow not installed")
class TestTheApp(unittest.TestCase):
    def test_use_sample_images_opens_the_sample_review(self):
        ui = play(use_sample=True)["ui"]
        self.assertEqual(ui["view_after_use_sample"], ["check-view"])
        self.assertEqual(ui["check_title_after_use_sample"], "The sample bin: check the pieces")
        self.assertEqual(ui["use_sample_requests"], ["POST /api/inventory/sample", "GET /api/inventory/vocab",
                                                     "GET /api/inventory/batch/sample1/review"])

    def test_an_empty_bin_shows_only_the_scan_prompt(self):
        result = play(open_builds=True)
        builds = result["ui"]["builds"]
        self.assertEqual(builds["view"], ["build-view"])
        self.assertEqual(builds["catalog_entries"], 0)
        self.assertEqual(builds["buttons"], ["📷 Scan a handful", "Use sample images"])
        self.assertEqual(result["ui"]["prompt_sample_view"], ["check-view"])
        self.assertIn("POST /api/inventory/sample", result["ui"]["prompt_sample_requests"])

    def test_the_sample_needs_no_model(self):
        requests = play(use_sample=True, open_builds=True)["requests"]
        self.assertFalse([r for r in requests if r.endswith("/classify") or "wonder" in r], requests)

    def test_the_button_sits_with_the_photo_panels(self):
        html = (REPO / "app" / "index.html").read_text()
        grid_end = html.index("</div>", html.index('id="panel-left"'))
        button = html.index('id="sample-images-btn"')
        self.assertLess(grid_end, button)
        self.assertLess(button, html.index('id="gallery-btn"'))
        self.assertIn(">No pieces handy? Use the sample pieces<", html)


if __name__ == "__main__":
    unittest.main()
