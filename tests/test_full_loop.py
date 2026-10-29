"""Full-loop tests: the build step, booklets, the build API, and one batch
through every stage.

- booklets: parts, steps, hidden faces, a self-contained page;
- build plans on the corrected kit inventory: the house-and-tree set fits;
  a missing piece or a different colour is named; BrickGPT designs through
  Path A fit, patch, fall short with the shortfall named, or have a loose part;
- the build API: options, create, read, booklet page, undo -> no longer fits;
- the whole loop through the API (upload, gate, classify with a recorded
  reply, review, confirm, build, booklet, undo), on drawn photos and, when it
  is on disk, on the real kit batch.

Standard-library unittest. Run from the repo root:
    python3 -m unittest discover -s tests -v
"""

import copy
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from backend import booklet as bk
from backend import brickgpt_constraint as path_a
from backend import build_plan as bp
from backend import inventory_db as db

try:
    from PIL import Image  # noqa: F401
    from test_photo_gate import KIT, scene
    HAVE_PILLOW = True
except ImportError:
    HAVE_PILLOW = False

try:
    import uvicorn  # noqa: F401
    from backend import full_loop
    HAVE_SERVER = HAVE_PILLOW
except ImportError:
    HAVE_SERVER = False

REPO = Path(__file__).resolve().parent.parent
RECORDED = REPO / "tests" / "fixtures" / "kit-batch-recorded.json"
VIEWS = ("top", "front", "right", "back", "left")


def item(family, shape, size, color, quantity, generator_type=None):
    return {"family": family, "shape": shape, "size": size, "color": color,
            "generator_type": generator_type, "quantity": quantity}


# The kit batch after review and confirm (INVENTORY-LOOP.md): 50 pieces, 2 generator-ready.
KIT_ITEMS = [
    item("brick", "headlight brick", "1x1", "light_bluish_gray", 2),
    item("brick", "round brick", "1x1", "light_bluish_gray", 4),
    item("brick", "tall 1x1 brick with 2 studs on side", "1x1", "lime", 2),
    item("brick", "brick", "1x2", "orange", 2, "1x2"),
    item("brick", "brick with 4 studs on side", "1x4", "blue", 2),
    item("plate", "round plate", "1x1", "lime", 4),
    item("plate", "plate", "1x2", "dark_purple", 4),
    item("plate", "plate with clip", "1x2", "lime", 2),
    item("plate", "plate", "1x2", "trans_clear", 3),
    item("plate", "jumper plate", "1x2", "white", 2),
    item("plate", "hinge plate", "1x4", "black", 1),
    item("plate", "plate", "1x6", "lime", 1),
    item("plate", "plate", "2x2", "magenta", 2),
    item("plate", "plate", "2x4", "medium_azure", 2),
    item("plate", "wedge plate", "2x4", "white", 2),
    item("slope", "1x1 slope (cheese)", "1x1", "medium_blue", 2),
    item("slope", "curved slope", "1x2", "black", 4),
    item("slope", "curved slope", "1x2", "medium_azure", 2),
    item("slope", "curved slope", "1x3", "light_bluish_gray", 2),
    item("tile", "round printed tile", "1x1", "white", 4),
    item("tile", "tile with 2 studs on edge", "2x2", "white", 1),
]
TRAIN_SHORT = {"1x1": 11, "1x2": 8, "1x6": 5, "1x8": 1, "2x2": 1, "2x4": 3, "2x6": 6}


def bricks_from(inventory_file, colors=("red", "blue")):
    """A Path A test inventory as confirmed generator-ready items, each size split over two colours."""
    items = []
    for size, n in path_a.load_inventory(path_a.KIT_DIR / inventory_file).items():
        first = n // 2
        for color, count in ((colors[0], first), (colors[1], n - first)):
            if count:
                items.append(item("brick", "brick", size, color, count, size))
    return items


def without(items, family, shape, size, color, n=1):
    out = copy.deepcopy(items)
    for i in out:
        if (i["family"], i["shape"], i["size"], i["color"]) == (family, shape, size, color):
            i["quantity"] -= n
    return [i for i in out if i["quantity"] > 0]


class TestBooklet(unittest.TestCase):
    def test_placement_sizes(self):
        plate = bk.place({"family": "plate", "shape": "plate", "size": "1x6", "color": "lime"}, [0, 0, 0])
        self.assertEqual((plate["dims"], plate["kind"]), ([6, 1, 1], "plate"))
        brick = bk.place({"family": "brick", "shape": "brick", "size": "6x2", "color": "red"}, [0, 0, 0], along="y")
        self.assertEqual(brick["dims"], [2, 6, 3])
        slope = bk.place({"family": "slope", "shape": "curved slope", "size": "1x2", "color": "black"}, [0, 0, 4])
        self.assertEqual((slope["dims"], slope["kind"], slope["down"]), ([2, 1, 2], "curved", "+x"))
        round_brick = bk.place({"family": "brick", "shape": "round brick", "size": "1x1", "color": "red"}, [0, 0, 0])
        round_plate = bk.place({"family": "plate", "shape": "round plate", "size": "1x1", "color": "red"}, [0, 0, 0])
        self.assertEqual((round_brick["dims"][2], round_plate["dims"][2]), (3, 1))

    def test_hidden_studs_and_faces_are_not_drawn(self):
        part = {"family": "brick", "shape": "brick", "size": "1x1", "color": "red"}
        apart = bk.picture([bk.place(part, [0, 0, 0]), bk.place(part, [3, 0, 0])])
        stacked = bk.picture([bk.place(part, [0, 0, 0]), bk.place(part, [0, 0, 3])])
        self.assertEqual(apart.count("<ellipse"), 4)    # two studs, two ellipses each
        self.assertEqual(stacked.count("<ellipse"), 2)  # the lower stud is under the upper brick

    def test_page(self):
        book = bp.plan_set("house-and-tree", KIT_ITEMS)["booklet"]
        page = bk.render_html(book)
        self.assertIn("<title>House and tree", page)
        self.assertNotIn("<script", page)
        for part in ("lime 1x6 plate", "orange 1x2 brick", "black 1x2 curved slope",
                     "light bluish gray 1x1 round brick", "lime 1x1 round plate"):
            self.assertIn(part, page)
        # one big picture on the cover and one per step, plus a small picture per part
        self.assertEqual(page.count('<div class="pic">'), 1 + len(book["steps"]))
        self.assertEqual(page.count('class="card step"'), 5)


class TestBuildPlan(unittest.TestCase):
    def test_house_and_tree_fits_the_kit(self):
        result = bp.plan_set("house-and-tree", KIT_ITEMS)
        self.assertEqual((result["status"], result["pieces"], result["missing"]), ("fit", 7, []))
        book = result["booklet"]
        self.assertEqual(len(book["steps"]), 5)
        self.assertEqual(len(book["placements"]), 7)
        self.assertEqual({p["label"]: p["qty"] for p in book["parts"]}, {
            "lime 1x6 plate": 1, "orange 1x2 brick": 2, "black 1x2 curved slope": 2,
            "light bluish gray 1x1 round brick": 1, "lime 1x1 round plate": 1})

    def test_missing_piece_is_named_and_there_is_no_booklet(self):
        result = bp.plan_set("house-and-tree", without(KIT_ITEMS, "brick", "brick", "1x2", "orange"))
        self.assertEqual(result["status"], "short")
        self.assertNotIn("booklet", result)
        self.assertEqual(result["message"], "Missing 1× orange 1x2 brick.")

    def test_a_different_colour_is_a_different_piece(self):
        items = without(KIT_ITEMS, "plate", "plate", "1x6", "lime") + [item("plate", "plate", "1x6", "white", 1)]
        self.assertEqual([m["label"] for m in bp.plan_set("house-and-tree", items)["missing"]], ["lime 1x6 plate"])

    def test_shape_spelling_is_normalised(self):
        items = without(KIT_ITEMS, "slope", "curved slope", "1x2", "black", 4) + [
            item("slope", "Curved  Slope", "1x2", "black", 2)]
        self.assertEqual(bp.plan_set("house-and-tree", items)["status"], "fit")

    def test_only_generator_ready_bricks_reach_brickgpt(self):
        self.assertEqual({t: n for t, n in bp.generator_counts(KIT_ITEMS).items() if n}, {"1x2": 2})

    def test_brickgpt_design_on_the_kit_is_a_named_shortfall(self):
        result = bp.plan_design("train", KIT_ITEMS)
        self.assertEqual(result["status"], "short")
        self.assertEqual(result["shortfall"], TRAIN_SHORT)
        self.assertEqual((result["short_bricks"], result["generator_ready"], result["other_pieces"]), (35, {"1x2": 2}, 48))
        self.assertNotIn("booklet", result)
        self.assertIn("Short of 35 bricks", result["message"])

    def test_brickgpt_design_that_fits_gets_one_step_per_layer(self):
        items = bricks_from("test-inventory-fits.json")
        result = bp.plan_design("chair", items)
        self.assertEqual(result["status"], "fit")
        book = result["booklet"]
        layers = {p["at"][2] for p in book["placements"]}
        self.assertEqual(len(book["steps"]), len(layers))
        self.assertEqual(sum(len(s["add"]) for s in book["steps"]), 86)
        used = {}
        for p in book["placements"]:
            key = (p["part"]["size"], p["part"]["color"])
            used[key] = used.get(key, 0) + 1
        owned = {(i["size"], i["color"]): i["quantity"] for i in items}
        self.assertTrue(all(n <= owned[k] for k, n in used.items()), "a colour was used more often than owned")

    def test_patched_design(self):
        result = bp.plan_design("train", bricks_from("test-inventory-near-miss.json"))
        self.assertEqual(result["status"], "patched")
        self.assertTrue(any("Patched" in note for note in result["booklet"]["notes"]))

    def test_design_with_a_loose_part(self):
        self.assertEqual(bp.plan_design("tower", bricks_from("test-inventory-fits.json"))["status"], "not_connected")

    def test_unknown_requests(self):
        with self.assertRaises(KeyError):
            bp.plan_set("castle", KIT_ITEMS)
        with self.assertRaises(KeyError):
            bp.plan_design("guitar", KIT_ITEMS)  # a BrickGPT category with no pre-generated design
        with self.assertRaises(KeyError):
            bp.plan({}, KIT_ITEMS)

    def test_options_order(self):
        found = bp.options(KIT_ITEMS)
        self.assertEqual([(o["id"], o["status"]) for o in found[:2]], [("house-and-tree", "fit"), ("train", "short")])
        self.assertEqual({o["status"] for o in found[-2:]}, {"not_connected"})
        self.assertEqual(len(found), 1 + len(bp.designs()))


def seed(conn, items, batch_id="20261029-000000-aaaaaa"):
    """Confirm `items` into the inventory as one batch whose photos passed the gate."""
    photos = [{"view": v, "file": f"{n}-{v}.jpg", "bytes": 1, "sha256": hashlib.sha256(f"{batch_id}{v}".encode()).hexdigest(),
               "gate": {"passed": True, "reasons": [], "metrics": {}}} for n, v in enumerate(VIEWS, 1)]
    db.register_batch(conn, batch_id, "2026-10-29T00:00:00+00:00", photos, db.photos_fingerprint(photos))
    detections = [{"family": i["family"], "shape": i["shape"], "size": i["size"], "color": i["color"],
                   "plain": bool(i["generator_type"]), "count": i["quantity"], "confidence": 1.0,
                   "region": {"bbox": [0, 0, 1, 1], "point": None}} for i in items]
    db.replace_detections(conn, batch_id, detections, "test")
    db.confirm_batch(conn, batch_id)
    return batch_id


@unittest.skipUnless(HAVE_SERVER, "FastAPI, uvicorn or Pillow not installed")
class TestBuildApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        spark = mock.Mock(side_effect=AssertionError("Spark called"))
        cls.ctx = full_loop.server(cls.tmp.name, spark)
        cls.api = cls.ctx.__enter__()
        with closing(db.connect()) as conn:
            cls.batch = seed(conn, KIT_ITEMS)

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)
        cls.tmp.cleanup()

    def test_known_set_build_and_booklet(self):
        status, build = self.api.call("POST", "/api/builds", json_body={"set": "house-and-tree"})
        self.assertEqual((status, build["status"], build["steps"]), (201, "fit", 5))
        self.assertNotIn("booklet", build)
        status, page = self.api.call("GET", build["booklet_url"], raw=True)
        self.assertEqual(status, 200)
        self.assertIn("House and tree", page)
        status, stored = self.api.call("GET", f"/api/builds/{build['build_id']}")
        self.assertEqual(status, 200)
        self.assertEqual(len(stored["booklet"]["steps"]), 5)
        self.assertEqual(stored["inventory_snapshot"]["total_pieces"], 50)
        self.assertEqual(stored["inventory_snapshot"]["generator_ready"], {"1x2": 2})

    def test_brickgpt_shortfall_has_no_booklet(self):
        status, build = self.api.call("POST", "/api/builds", json_body={"design": "train"})
        self.assertEqual((status, build["status"], build["shortfall"]), (201, "short", TRAIN_SHORT))
        self.assertNotIn("booklet_url", build)
        status, body = self.api.call("GET", f"/api/builds/{build['build_id']}/booklet")
        self.assertEqual(status, 404)
        self.assertIn("Short of 35 bricks", body["detail"])

    def test_bad_requests(self):
        self.assertEqual(self.api.call("POST", "/api/builds", json_body={})[0], 422)
        self.assertEqual(self.api.call("POST", "/api/builds", json_body={"set": "house-and-tree", "design": "train"})[0], 422)
        self.assertEqual(self.api.call("POST", "/api/builds", json_body={"design": "train", "samples": 9})[0], 422)
        self.assertEqual(self.api.call("POST", "/api/builds", json_body={"set": "castle"})[0], 404)
        self.assertEqual(self.api.call("GET", "/api/builds/9999")[0], 404)

    def test_options(self):
        status, body = self.api.call("GET", "/api/builds/options")
        self.assertEqual(status, 200)
        self.assertEqual(body["inventory"], {"total_pieces": 50, "generator_ready": 2, "other": 48})
        self.assertEqual((body["options"][0]["id"], body["options"][0]["status"]), ("house-and-tree", "fit"))

    def test_undo_takes_the_pieces_out_of_the_build(self):
        status, _ = self.api.call("POST", f"/api/inventory/undo-last-batch?batch_id={self.batch}")
        self.assertEqual(status, 200)
        try:
            status, build = self.api.call("POST", "/api/builds", json_body={"set": "house-and-tree"})
            self.assertEqual((status, build["status"]), (201, "short"))
            self.assertEqual(len(build["missing"]), 5)  # all 5 kinds of piece, 7 pieces
        finally:
            self.assertEqual(self.api.call("POST", f"/api/inventory/batch/{self.batch}/confirm")[0], 200)


def spark_piece(family, shape, size, color, plain, at):
    return {"family": family, "shape": shape, "size": size, "color": color, "plain": plain,
            "confidence": 0.9, "at": at}


@unittest.skipUnless(HAVE_SERVER, "FastAPI, uvicorn or Pillow not installed")
class TestFullLoop(unittest.TestCase):
    """One batch through every stage, through the API, without hand edits."""

    def drawn_batch(self, folder):
        folder.mkdir(parents=True)
        photos = []
        for n, view in enumerate(VIEWS, 1):
            out = io.BytesIO()
            scene(seed=40 + n).save(out, "JPEG", quality=92)
            (folder / f"{n}-{view}.jpg").write_bytes(out.getvalue())
            photos.append({"view": view, "file": f"{n}-{view}.jpg"})
        (folder / "batch.json").write_text(json.dumps({"photos": photos}))
        hashes = {p["view"]: hashlib.sha256((folder / p["file"]).read_bytes()).hexdigest() for p in photos}
        pieces = [
            spark_piece("plate", "plate", "1x6", "lime", True, [0.2, 0.2]),
            spark_piece("brick", "brick", "1x2", "orange", True, [0.3, 0.2]),
            spark_piece("brick", "brick", "1x2", "orange", True, [0.4, 0.2]),
            spark_piece("slope", "curved slope", "1x2", "black", False, [0.5, 0.2]),
            spark_piece("tile", "tile", "1x2", "black", True, [0.6, 0.2]),  # a curved slope, fixed in review
            spark_piece("brick", "round brick", "1x1", "light_bluish_gray", False, [0.7, 0.2]),
            spark_piece("plate", "round plate", "1x1", "lime", False, [0.8, 0.2]),
            spark_piece("plate", "plate", "2x4", "medium_azure", True, [0.5, 0.6]),
        ]
        return {"photos_sha256": hashes, "model": "test",
                "reply": {"checks": [{"image": n, "real_lego": "yes"} for n in range(1, 6)], "pieces": pieces,
                          "total": len(pieces)},
                "recorded": {"seconds": 0, "finish_reason": "stop"},
                "review": [{"piece": 4, "family": "slope", "shape": "curved slope", "size": "1x2", "color": "black",
                            "plain": False}]}

    def test_drawn_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            batch = Path(tmp) / "batch"
            recorded = self.drawn_batch(batch)
            report = full_loop.run(batch, recorded, Path(tmp) / "out")
            stages = {s["stage"].split(".")[0]: s for s in report["stages"]}
            self.assertEqual(set(stages["1"]["gate"].values()), {"passed"})
            self.assertEqual((stages["2"]["spark_calls"], stages["2"]["pieces"]), (1, 8))
            self.assertEqual((stages["3"]["corrected"], stages["3"]["confirmed"]), (1, 8))
            self.assertEqual((report["known_set"]["status"], report["known_set"]["steps"]), ("fit", 5))
            self.assertEqual(report["brickgpt"]["status"], "short")
            self.assertEqual((stages["5"]["after_undo"], stages["5"]["after_confirm_again"]), ("short", "fit"))
            page = Path(report["booklets"][0]).read_text()
            self.assertIn("House and tree", page)

    def test_recorded_reply_is_only_played_back_for_its_own_photos(self):
        with tempfile.TemporaryDirectory() as tmp:
            batch = Path(tmp) / "batch"
            self.drawn_batch(batch)
            with self.assertRaises(full_loop.StageFailed):
                full_loop.run(batch, json.loads(RECORDED.read_text()), Path(tmp) / "out")

    @unittest.skipUnless((KIT / "batch.json").is_file() if HAVE_PILLOW else False, "kit batch not on disk")
    def test_real_kit_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = full_loop.run(KIT, json.loads(RECORDED.read_text()), Path(tmp))
        summary = report["summary"]
        self.assertEqual((summary["total_pieces"], summary["generator_ready"]["total"], summary["other"]["total"]),
                         (50, 2, 48))
        self.assertEqual(report["spark_calls"], 1)
        self.assertEqual((report["known_set"]["status"], report["known_set"]["steps"]), ("fit", 5))
        self.assertEqual((report["brickgpt"]["status"], report["brickgpt"]["shortfall"]), ("short", TRAIN_SHORT))
        rows = lambda items: sorted(tuple(sorted(i.items())) for i in items)  # noqa: E731
        self.assertEqual(rows(summary["items"]), rows(KIT_ITEMS))


if __name__ == "__main__":
    unittest.main()
