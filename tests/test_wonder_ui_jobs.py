"""The phone polls a fake Wonder job and opens its booklet in the app."""

import copy
import unittest
from pathlib import Path

from test_ui_carousel import OPTIONS, play


def options():
    result = copy.deepcopy(OPTIONS)
    result["wonder"] = {"enabled": True, "busy": False, "targets": ["a simple house"], "recent": [],
                        "max_tries": 3, "per_try": {"seconds": 120, "usd": 0.25}}
    return result


class TestWonderJobsOnPhone(unittest.TestCase):
    def test_design_first_polls_and_opens_booklet(self):
        job = {"open_link": True, "polls": [
            [200, {"state": "running", "attempt": 1, "max_attempts": 3,
                   "message": "Try 1 of 3: the checker found 2 problems, Wonder is fixing them"}],
            [200, {"state": "done", "message": "Design ready", "build": {
                "title": "Test house", "status": "fit", "booklet_url": "/api/builds/7/booklet",
                "message": "Checked", "tries": [{"n": 1}], "seconds": 2.5, "usd": 0.01,
            }}],
        ]}
        result = play(open_builds=True, build_options=options(), wonder_job=job)
        ui = result["ui"]
        self.assertEqual([(x["tag"], x["className"], x["text"]) for x in ui["builds"]["list_order"]], [
            ("DIV", "wonder", ""), ("H3", "build-section", "From the kit's book"), ("DIV", "build-carousel", "")])
        self.assertIn("✨ Design something new from my pieces", ui["wonder"]["text"])
        self.assertTrue(any("up to 3 tries" in text and "$0.25" in text for text in ui["wonder"]["text"]))
        self.assertEqual([p["delay"] for p in ui["wonder"]["progress"]], [4000, 4000])
        self.assertIn("Try 1 of 3: the checker found 2 problems", ui["wonder"]["progress"][0]["after"])
        self.assertEqual([r for r in result["requests"] if "/api/builds/wonder" in r], [
            "POST /api/builds/wonder", "GET /api/builds/wonder/jobs/job-1", "GET /api/builds/wonder/jobs/job-1"])
        self.assertEqual(ui["wonder"]["status"], "Design ready")
        self.assertFalse(ui["wonder"]["button_disabled"])
        self.assertEqual(ui["wonder"]["booklet"]["view"], ["booklet-view"])
        self.assertEqual(ui["wonder"]["booklet"]["title"], "Test house")
        self.assertTrue(ui["wonder"]["booklet"]["frame"].endswith("/api/builds/7/booklet"))
        self.assertEqual(ui["wonder"]["after_back"], ["build-view"])

    def test_no_key_offers_recorded_example_in_the_app(self):
        job = {"post": [401, {"detail": "key required"}], "open_link": True}
        result = play(open_builds=True, build_options=options(), wonder_job=job)
        ui = result["ui"]["wonder"]
        self.assertEqual(ui["status"],
                         "Designing a new model calls Muse Wonder, so the public demo needs the access key.")
        self.assertEqual(ui["links"][0]["text"], "See a recorded Wonder design")
        self.assertEqual(ui["booklet"]["view"], ["booklet-view"])
        self.assertTrue(ui["booklet"]["frame"].endswith("/api/wonder/example"))
        self.assertEqual(ui["after_back"], ["build-view"])
        self.assertFalse(any("/jobs/" in r for r in result["requests"]))

    def test_job_failure_and_lost_job_are_shown(self):
        for response, message in [
            ([200, {"state": "failed", "message": "Wonder failed"}], "Wonder failed"),
            ([404, {"detail": "this design job was lost (the server restarted); try again"}], "this design job was lost"),
        ]:
            with self.subTest(message=message):
                job = {"polls": [response]}
                ui = play(open_builds=True, build_options=options(), wonder_job=job)["ui"]["wonder"]
                self.assertIn(message, ui["status"])
                self.assertFalse(ui["button_disabled"])
                self.assertEqual(ui["links"], [])

    def test_service_worker_cache_is_version_16(self):
        worker = (Path(__file__).resolve().parent.parent / "app" / "sw.js").read_text()
        self.assertIn("var CACHE_NAME = 'binbuild-v16';", worker)
