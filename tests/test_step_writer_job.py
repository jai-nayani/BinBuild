"""The background job stores Spark's words with the checked booklet."""

import json
import os
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from backend import full_loop, inventory_db, main, step_writer, wonder_designer
from backend.spark_client import SparkReply
from test_full_loop import KIT_ITEMS, seed


class FakeSpark:
    def __init__(self):
        self.calls = 0

    def chat(self, messages):
        self.calls += 1
        prompt = messages[0]["content"][0]["text"]
        data = json.loads(prompt.rsplit("\n", 1)[-1])
        answer = {"title": "My Little House", "steps": [
            {"n": step["n"], "text": "Place the pieces shown."} for step in data["steps"]
        ]}
        return SparkReply(json.dumps(answer), "stop", {}, 0.0)


class StageJobs(dict):
    """Keep the actual assigned stages, including short validation phases."""
    def __init__(self):
        super().__init__()
        self.stages = []

    def __setitem__(self, key, value):
        stages = self.stages

        class Entry(dict):
            def update(self, *args, **kwargs):
                super().update(*args, **kwargs)
                values = dict(*args, **kwargs)
                if "stage" in values:
                    stages.append(values["stage"])

        stages.append(value["stage"])
        super().__setitem__(key, Entry(value))


class TestStepWriterJob(unittest.TestCase):
    def test_recorded_wonder_job_stores_the_fake_spark_words(self):
        recorded = json.loads((Path(__file__).parent / "fixtures" / "wonder-house-recorded.json").read_text())
        spark = FakeSpark()
        jobs = StageJobs()
        with tempfile.TemporaryDirectory() as tmp, full_loop.server(tmp, spark) as api, \
                mock.patch.dict(os.environ, {"BINBUILD_WONDER": "1"}), \
                mock.patch.object(main, "_wonder_jobs", jobs), \
                mock.patch.object(main.WonderClient, "from_env", return_value=wonder_designer.ReplayWonder(recorded)):
            with closing(inventory_db.connect()) as conn:
                seed(conn, KIT_ITEMS)
            status, started = api.call("POST", "/api/builds/wonder", json_body={"target": "a simple house"})
            self.assertEqual(status, 202, started)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                status, job = api.call("GET", "/api/builds/wonder/jobs/" + started["job_id"])
                self.assertEqual(status, 200)
                if job["state"] != "running":
                    break
                time.sleep(0.02)
            self.assertEqual(job["state"], "done", job)
            self.assertEqual(jobs.stages, ["designing", "designing", "checking", "writing", "done"])
            self.assertEqual(job["stage"], "done")
            self.assertEqual(job["build"]["step_words"], "muse-spark")
            self.assertEqual(job["build"]["title"], "My Little House")
            status, build = api.call("GET", "/api/builds/" + str(job["build"]["build_id"]))
            self.assertEqual(status, 200)
            self.assertEqual(build["step_words"], "muse-spark")
            book = build["booklet"]
            self.assertEqual(spark.calls, 1)
            self.assertEqual(book["title"], "My Little House")
            self.assertTrue(all(step["text"] == "Place the pieces shown." for step in book["steps"]))
            self.assertIn(step_writer.SUCCESS_NOTE, book["notes"])
            self.assertTrue(any("Nobody has built it yet" in note for note in book["notes"]))
            self.assertEqual(len(book["placements"]), job["build"]["pieces"])


if __name__ == "__main__":
    unittest.main()
