"""Ideas follow the exact inventory and are checked before they become choices."""

import json
import os
import tempfile
import time
import unittest
from contextlib import closing
from unittest import mock

from backend import design_ideas as ideas, full_loop, guard, inventory_db as db, main, sample_bin
from test_full_loop import KIT_ITEMS, seed
from test_wonder import HOUSE, OWNED, Scripted
from test_step_writer_job import FakeSpark, StageJobs


TOWER = "1x1 (0,0,0) round_brick light_bluish_gray\n1x1 (0,0,3) round_brick light_bluish_gray\n1x1 (0,0,6) round_plate lime"
PYRAMID = "2x4 (0,0,0) plate medium_azure\n2x2 (0,1,1) plate magenta\n1x2 (0,1,2) brick orange"


def proposals():
    return [{"title": title, "description": desc, "design": design} for title, desc, design in (
        ("Garden lookout", "A lookout built from long and rounded pieces.", HOUSE),
        ("Lime-topped tower", "Round bricks support a lime top.", TOWER),
        ("Colourful pyramid", "Broad plates support a small stepped peak.", PYRAMID),
    )]


def response(items=None):
    return json.dumps({"ideas": proposals() if items is None else items})


class TestProposalChecks(unittest.TestCase):
    def test_three_different_designs_use_the_supplied_parts(self):
        fake = Scripted([response()])
        found = ideas.propose(fake, OWNED)
        self.assertEqual(len(found), 3)
        self.assertEqual([x["title"] for x in found], [x["title"] for x in proposals()])
        self.assertIn("orange 1x2 ×2", fake.sent[0]["instructions"])
        self.assertIn("Choose the objects yourself", fake.sent[0]["instructions"])
        self.assertNotIn("a chair", fake.sent[0]["instructions"])

    def test_invalid_and_duplicate_models_are_retried(self):
        bad = proposals()
        bad[1]["design"] = "1x1 (0,0,10) round_brick light_bluish_gray"
        bad[2]["design"] = HOUSE
        fake = Scripted([response(bad), response(proposals()[1:])])
        found = ideas.propose(fake, OWNED)
        self.assertEqual(len(found), 3)
        self.assertIn("lowest z must be 0", fake.sent[1]["text"])
        self.assertIn("repeats an accepted idea", fake.sent[1]["text"])
        self.assertEqual(fake.sent[1]["previous_id"], "r1")

    def test_wheelless_car_is_not_offered_and_short_results_are_honest(self):
        item = {**proposals()[0], "title": "Little car"}
        fake = Scripted([response([item])])
        self.assertEqual(ideas.propose(fake, OWNED, max_attempts=1), [])

    def test_inventory_key_changes_for_count_colour_shape_and_source(self):
        one = {"items": [dict(KIT_ITEMS[0])]}
        for field, value in (("quantity", 99), ("color", "red"), ("shape", "other")):
            altered = {"items": [{**one["items"][0], field: value}]}
            self.assertNotEqual(ideas.inventory_key(one, "uploaded"), ideas.inventory_key(altered, "uploaded"))
        self.assertNotEqual(ideas.inventory_key(one, "sample"), ideas.inventory_key(one, "uploaded"))


class TestInventoryIdeasApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.server = full_loop.server(self.tmp.name, None)
        self.api = self.server.__enter__()
        with closing(db.connect()) as conn:
            seed(conn, KIT_ITEMS)
        self.env = mock.patch.dict(os.environ, {"BINBUILD_WONDER": "1"})
        self.env.start()
        self.fake = Scripted([response()])
        self.client = mock.patch.object(main.WonderClient, "from_env", return_value=self.fake)
        self.client.start()

    def tearDown(self):
        deadline = time.monotonic() + 10
        while main._wonder_busy.locked() and time.monotonic() < deadline:
            time.sleep(.01)
        self.client.stop()
        self.env.stop()
        self.server.__exit__(None, None, None)
        self.tmp.cleanup()

    def wait(self, job_id):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            code, job = self.api.call("GET", "/api/builds/wonder/jobs/" + job_id)
            self.assertEqual(code, 200)
            if job["state"] != "running":
                return job
            time.sleep(.02)
        self.fail("job did not finish")

    def start(self):
        code, result = self.api.call("POST", "/api/builds/wonder/ideas", json_body={"source": "uploaded"})
        self.assertEqual(code, 202, result)
        job = self.wait(result["job_id"])
        self.assertEqual(job["state"], "done", job)
        return job

    def test_checked_previews_are_cached_and_selection_keeps_the_same_placements(self):
        jobs = StageJobs()
        for patcher in (mock.patch.object(main, "_wonder_jobs", jobs),
                        mock.patch.object(main, "make_spark", return_value=FakeSpark())):
            patcher.start()
            self.addCleanup(patcher.stop)
        job = self.start()
        self.assertEqual(jobs.stages, ["designing", "designing", "checking", "done"])
        jobs.stages.clear()
        self.assertEqual(len(job["ideas"]), 3)
        self.assertTrue(all(x["cover"].startswith("<svg") for x in job["ideas"]))
        code, options = self.api.call("GET", "/api/builds/options?source=uploaded")
        self.assertEqual(options["wonder"]["ideas"], job["ideas"])
        self.assertNotIn("targets", options["wonder"])
        selected = job["ideas"][0]
        code, started = self.api.call("POST", "/api/builds/wonder", json_body={
            "source": "uploaded", "idea_id": selected["id"], "inventory_key": job["inventory_key"]})
        self.assertEqual(code, 202)
        finished = self.wait(started["job_id"])
        self.assertEqual(jobs.stages, ["checking", "writing", "done"])
        self.assertEqual(finished["build"]["status"], "fit", finished)
        self.assertEqual(finished["build"]["pieces"], selected["pieces"])
        self.assertEqual(finished["build"]["design"].strip(), HOUSE.strip())
        self.assertEqual(len(self.fake.sent), 1, "choosing a preview does not invent a different model")
        self.assertTrue(options["options"], "book designs can also match uploaded pieces")
        self.assertTrue(all(x["status"] == "fit" for x in options["options"]))

    def test_changed_pieces_clear_the_suggestions_and_reject_an_old_selection(self):
        job = self.start()
        with closing(db.connect()) as conn:
            seed(conn, [KIT_ITEMS[0]], batch_id="20261104-000001-bbbbbb")
        code, options = self.api.call("GET", "/api/builds/options?source=uploaded")
        self.assertEqual(options["wonder"]["ideas"], [])
        self.assertNotEqual(options["wonder"]["inventory_key"], job["inventory_key"])
        code, body = self.api.call("POST", "/api/builds/wonder", json_body={
            "source": "uploaded", "idea_id": job["ideas"][0]["id"], "inventory_key": job["inventory_key"]})
        self.assertEqual(code, 409)
        self.assertIn("pieces changed", body["detail"])

    def test_sample_and_uploaded_pieces_are_separate_and_books_must_fit(self):
        with closing(db.connect()) as conn:
            db.undo_last_batch(conn)
            seed(conn, [{**KIT_ITEMS[0], "quantity": 1}], batch_id="20261104-000002-cccccc")
            sample_bin.load(conn, main.DATA_DIR)
            db.confirm_batch(conn, sample_bin.BATCH_ID)
        _, own = self.api.call("GET", "/api/builds/options?source=uploaded")
        _, sample = self.api.call("GET", "/api/builds/options?source=sample")
        self.assertEqual(own["inventory"]["total_pieces"], 1)
        self.assertEqual(own["options"], [])
        self.assertEqual(sample["inventory"]["total_pieces"], 50)
        self.assertTrue(sample["options"])
        self.assertTrue(all(x["status"] == "fit" and x["has_booklet"] for x in sample["options"]))

    def test_ideas_are_guarded_and_cars_are_refused_before_a_model_call(self):
        with mock.patch.dict(os.environ, {guard.ACCESS_KEY_ENV: "fake-local-key"}):
            code, _ = self.api.call("POST", "/api/builds/wonder/ideas", json_body={"source": "uploaded"})
            self.assertEqual(code, 401)
        code, _ = self.api.call("POST", "/api/builds/wonder", json_body={"target": "a little car"})
        self.assertEqual(code, 422)
        self.assertEqual(self.fake.sent, [])


if __name__ == "__main__":
    unittest.main()
