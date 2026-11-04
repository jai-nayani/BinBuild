"""Offline checks for the Wonder background-job API and its lock."""

import ast
import os
import tempfile
import threading
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from backend import full_loop, guard, inventory_db, main, wonder_designer
from backend.spark_client import SparkError
from backend.wonder_client import WonderError, WonderReply
from test_full_loop import KIT_ITEMS, seed
from test_wonder import HOUSE, OWNED, Scripted, reply


class BlockingWonder:
    """Fail once, then wait on the test before returning a valid proposal."""

    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def respond(self, text, instructions=None, previous_id=None):
        self.calls += 1
        if self.calls == 1:
            bad = HOUSE + "1x1 (9,9,0) round_tile white\n1x1 (9,9,5) round_plate lime\n"
            return WonderReply("one", reply(bad), "completed", {}, 0.0)
        self.entered.set()
        if not self.release.wait(10):
            raise WonderError("the test did not release the fake")
        return WonderReply("two", reply(HOUSE, "Little house"), "completed", {}, 0.0)


class OfflineSpark:
    def chat(self, *args, **kwargs):
        raise SparkError("offline test fake")


class TestWonderJobs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ctx = full_loop.server(self.tmp.name, None)
        self.api = self.ctx.__enter__()
        with closing(inventory_db.connect()) as conn:
            seed(conn, KIT_ITEMS)
        self.fake = BlockingWonder()
        env = {k: v for k, v in os.environ.items() if k != guard.ACCESS_KEY_ENV}
        env.update({"BINBUILD_WONDER": "1", "BINBUILD_WONDER_TRIES": "3"})
        self.env = mock.patch.dict(os.environ, env, clear=True)
        self.env.start()
        self.client = mock.patch.object(main.WonderClient, "from_env", return_value=self.fake)
        self.client.start()
        self.spark = mock.patch.object(main.SparkClient, "from_env", return_value=OfflineSpark())
        self.spark.start()

    def tearDown(self):
        self.fake.release.set()
        deadline = time.monotonic() + 10
        while main._wonder_busy.locked() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.spark.stop()
        self.client.stop()
        self.env.stop()
        self.ctx.__exit__(None, None, None)
        self.tmp.cleanup()

    def post(self, headers=None):
        return self.api.call("POST", "/api/builds/wonder", json_body={"target": "a simple house"}, headers=headers)

    def poll(self, job_id):
        return self.api.call("GET", "/api/builds/wonder/jobs/" + job_id)

    def finish(self, job_id):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            status, body = self.poll(job_id)
            self.assertEqual(status, 200)
            if body["state"] != "running":
                return body
            time.sleep(0.01)
        self.fail("job did not finish")

    def test_progress_and_second_start_is_refused(self):
        status, start = self.post()
        self.assertEqual(status, 202)
        job_id = start["job_id"]
        self.assertTrue(self.fake.entered.wait(5))
        status, progress = self.poll(job_id)
        self.assertEqual(status, 200)
        self.assertEqual((progress["state"], progress["attempt"], progress["max_attempts"]), ("running", 2, 3))
        self.assertIn("checker found 2 problems", progress["message"])
        self.assertEqual(self.post()[0], 409)
        self.fake.release.set()
        result = self.finish(job_id)
        self.assertEqual(result["state"], "done")
        self.assertEqual(result["build"]["status"], "fit")
        self.assertIn("Found on try 2 of 3", result["build"]["message"])
        self.assertIn("booklet_url", result["build"])

    def test_unknown_job_explains_that_it_may_have_been_lost(self):
        status, body = self.poll("missing-job")
        self.assertEqual(status, 404)
        self.assertIn("this design job was lost (the server restarted); try again", body["detail"])

    def test_status_and_example_are_open_while_post_needs_key(self):
        sample_job = {"state": "running", "attempt": 1, "max_attempts": 3, "message": "working"}
        with main._wonder_jobs_lock:
            main._wonder_jobs["public-test-job"] = sample_job
        try:
            with mock.patch.dict(os.environ, {guard.ACCESS_KEY_ENV: "test-key-not-a-secret"}), \
                    mock.patch.object(guard, "PAID", guard.RateLimit("paid", 20, 3600)), \
                    mock.patch.object(main.booklet, "render_html", side_effect=lambda book: " ".join(book["notes"])):
                self.assertEqual(self.post()[0], 401)
                self.assertEqual(self.poll("public-test-job"), (200, sample_job))
                status, page = self.api.call("GET", "/api/wonder/example", raw=True)
                self.assertEqual(status, 200)
                self.assertIn("Oct 29", page)
                self.assertIn("not made from your bin", page)
                self.assertIn("Nobody has built it yet", page)
        finally:
            with main._wonder_jobs_lock:
                main._wonder_jobs.pop("public-test-job", None)

    def test_worker_exception_sets_failed_and_releases_lock(self):
        class Broken:
            def respond(self, *args, **kwargs):
                raise RuntimeError("unexpected internal failure")

        with mock.patch.object(main.WonderClient, "from_env", return_value=Broken()), \
                mock.patch.object(main.traceback, "print_exc") as logged:
            status, start = self.post()
            self.assertEqual(status, 202)
            result = self.finish(start["job_id"])
            self.assertEqual(result["state"], "failed")
            self.assertIn("failed", result["message"])
            deadline = time.monotonic() + 3
            while main._wonder_busy.locked() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertFalse(main._wonder_busy.locked())
            logged.assert_called_once_with()

    def test_step_writer_setup_error_is_logged_and_keeps_the_booklet(self):
        from backend import step_writer

        fake = Scripted([reply(HOUSE, "Little house")])
        with mock.patch.object(main.WonderClient, "from_env", return_value=fake), \
                mock.patch.object(main.SparkClient, "from_env", side_effect=SparkError("offline fake")), \
                mock.patch.object(main.traceback, "print_exc") as logged:
            status, start = self.post()
            self.assertEqual(status, 202)
            result = self.finish(start["job_id"])
            self.assertEqual(result["state"], "done", result)
            self.assertEqual(result["build"]["status"], "fit")
            logged.assert_called_once_with()
            status, stored = self.api.call("GET", "/api/builds/" + str(result["build"]["build_id"]))
            self.assertEqual(status, 200)
            self.assertIn(step_writer.FALLBACK_NOTE, stored["booklet"]["notes"])

    def test_missing_key_is_a_fast_503_and_releases_lock(self):
        with mock.patch.object(main.WonderClient, "from_env", side_effect=WonderError("no Meta Model API key")):
            status, body = self.post()
        self.assertEqual(status, 503)
        self.assertIn("not set up", body["detail"])
        self.assertFalse(main._wonder_busy.locked())

    def test_unexpected_client_setup_error_releases_lock(self):
        endpoint = next(route.endpoint for route in main.app.routes
                        if getattr(route, "path", None) == "/api/builds/wonder" and "POST" in route.methods)
        with mock.patch.object(main.WonderClient, "from_env", side_effect=OSError("setup failed")):
            with self.assertRaisesRegex(OSError, "setup failed"):
                endpoint(main.WonderRequest(target="a simple house"))
        self.assertFalse(main._wonder_busy.locked())

    def test_thread_start_error_cleans_up_job_and_releases_lock(self):
        endpoint = next(route.endpoint for route in main.app.routes
                        if getattr(route, "path", None) == "/api/builds/wonder" and "POST" in route.methods)
        with main._wonder_jobs_lock:
            before = set(main._wonder_jobs)
        with mock.patch.object(main.threading, "Thread") as thread:
            thread.return_value.start.side_effect = RuntimeError("cannot start thread")
            with self.assertRaisesRegex(RuntimeError, "cannot start thread"):
                endpoint(main.WonderRequest(target="a simple house"))
        self.assertFalse(main._wonder_busy.locked())
        with main._wonder_jobs_lock:
            self.assertEqual(set(main._wonder_jobs), before)


class TestWonderAttemptConfiguration(unittest.TestCase):
    def test_configured_limit_is_bounded_and_invalid_value_uses_default(self):
        for raw, expected in (("0", 1), ("2", 2), ("5", 5), ("99", 5), ("invalid", 3)):
            with self.subTest(raw=raw), mock.patch.dict(os.environ, {"BINBUILD_WONDER_TRIES": raw}):
                self.assertEqual(wonder_designer.configured_attempts(), expected)
        with mock.patch.dict(os.environ, {k: v for k, v in os.environ.items()
                                          if k != "BINBUILD_WONDER_TRIES"}, clear=True):
            self.assertEqual(wonder_designer.configured_attempts(), 3)

    def test_callback_receives_each_attempt_and_its_errors(self):
        broken = HOUSE + "1x1 (9,9,0) round_tile white\n1x1 (9,9,5) round_plate lime\n"
        fake = Scripted([reply(broken), reply(HOUSE, "Little house")])
        seen = []
        result = wonder_designer.design(fake, OWNED, max_attempts=3, log=lambda *_: None,
                                        on_attempt=lambda n, errors, seconds: seen.append((n, errors, seconds)))
        self.assertTrue(result.ok)
        self.assertEqual(seen, [(1, 2, 1.0), (2, 0, 1.0)])
        self.assertEqual(result.max_attempts, 3)

    def test_deploy_enables_three_attempts(self):
        path = Path(__file__).resolve().parent.parent / "deploy/modal_app.py"
        tree = ast.parse(path.read_text())
        configurations = [node.args[0] for node in ast.walk(tree)
                          if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                          and node.func.attr == "env" and node.args and isinstance(node.args[0], ast.Dict)]
        values = [{key.value: value.value for key, value in zip(node.keys, node.values)
                   if isinstance(key, ast.Constant) and isinstance(value, ast.Constant)}
                  for node in configurations]
        self.assertTrue(any(config.get("BINBUILD_WONDER") == "1" and
                            config.get("BINBUILD_WONDER_TRIES") == "3" for config in values))


if __name__ == "__main__":
    unittest.main()
