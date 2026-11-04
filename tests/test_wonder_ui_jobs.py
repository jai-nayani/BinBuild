"""The phone polls a fake Wonder job and opens its booklet in the app."""

import copy
import unittest
from pathlib import Path

from test_ui_carousel import OPTIONS, play


def options():
    result = copy.deepcopy(OPTIONS)
    result["wonder"] = {"enabled": True, "busy": False, "inventory_key": "test-inventory", "ideas": [
        {"id": "idea-1", "title": "Azure Lookout", "description": "A small lookout from your plates.",
         "pieces": 12, "cover": "<svg></svg>"}], "recent": [],
                        "max_tries": 3, "per_try": {"seconds": 120, "usd": 0.25}}
    return result


class TestWonderJobsOnPhone(unittest.TestCase):
    def test_find_ideas_renders_three_checked_cards_without_a_fixed_menu(self):
        o = options()
        o["wonder"]["ideas"] = []
        o["wonder"]["recent"] = [{"title": "Old house", "status": "fit", "message": "Saved",
                                  "booklet_url": "/api/builds/4/booklet"}]
        choices = [{"id": str(n), "title": title, "description": "Uses your particular pieces.",
                    "pieces": n + 3, "cover": "<svg></svg>"}
                   for n, title in enumerate(("Lime lookout", "Purple garden", "Azure sculpture"))]
        job = {"find": True, "polls": [[200, {"state": "done", "ideas": choices,
                                             "inventory_key": "changed", "message": "3 checked ideas."}]]}
        result = play(open_builds=True, build_options=o, wonder_job=job)
        ui = result["ui"]["wonder"]
        self.assertEqual(ui["selects"], 0)
        self.assertEqual(len(ui["ideas"]), 3)
        self.assertIn("Lime lookout", ui["ideas"][0])
        self.assertEqual(ui["saved"], [{"tag": "DETAILS", "open": False}])
        self.assertIn("POST /api/builds/wonder/ideas", result["requests"])

    def test_uploaded_book_carousel_hides_designs_with_missing_pieces(self):
        o = options()
        o["options"][0]["status"] = "short"
        result = play(open_builds=True, build_options=o)
        self.assertEqual([c["id"] for c in result["ui"]["builds"]["carousel"]["cards"]], ["guitar"])

    def test_sample_confirmation_offers_trying_own_pieces_without_claiming_a_scan(self):
        sample = {"batch": {"id": "sample1", "status": "confirmed", "classifier": "sample: recorded"},
                  "detections": [], "pieces": 50, "photos_ready": True, "count_photo": None}
        ui = play(use_sample=True, review=sample, try_own_pieces=True)["ui"]
        self.assertEqual(ui["sample_actions"]["title"], "✓ The sample is ready")
        self.assertEqual(ui["sample_actions"]["next"], "📷 Try with my own pieces")
        self.assertEqual(ui["sample_actions"]["back"], "← Back to the start")
        self.assertIn("sample pieces", ui["sample_actions"]["text"])
        self.assertNotIn("Sweep", ui["try_own_pieces"]["status"])
        self.assertEqual(ui["try_own_pieces"]["view"], ["capture-view"])

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
            ("DIV", "wonder", ""), ("H3", "build-section", "Book designs that fit your pieces"), ("DIV", "build-carousel", "")])
        self.assertIn("Three ideas from my pieces", ui["wonder"]["text"])
        self.assertIn("Muse Wonder looks at your pieces and invents three things to build. "
                      "Every design is checked before you see it.", ui["wonder"]["text"])
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

    def test_failed_poll_retries_then_shows_the_completed_design(self):
        for failed in ([0, None], [503, {"detail": "temporarily unavailable"}]):
            with self.subTest(failed=failed):
                job = {"polls": [failed, [200, {"state": "done", "message": "Design ready", "build": {
                    "title": "Test house", "status": "fit", "booklet_url": "/api/builds/7/booklet",
                    "message": "Checked",
                }}]]}
                result = play(open_builds=True, build_options=options(), wonder_job=job)
                ui = result["ui"]["wonder"]
                # A network error also schedules the backend health-check timeout.
                self.assertEqual([p["delay"] for p in ui["progress"]], [4000] * (3 if failed[0] == 0 else 2))
                self.assertEqual(ui["status"], "Design ready")
                self.assertFalse(ui["button_disabled"])
                self.assertEqual(len(ui["links"]), 1)
                self.assertEqual(len([r for r in result["requests"] if "/jobs/" in r]), 2)

    def test_successful_poll_resets_the_consecutive_failure_count(self):
        failed = [502, {"detail": "temporary error"}]
        job = {"polls": [failed] * 3 + [
            [200, {"state": "running", "message": "Still designing"}],
        ] + [failed] * 3 + [
            [200, {"state": "done", "message": "Design ready", "build": {
                "title": "Test house", "status": "fit", "message": "Checked",
            }}],
        ]}
        ui = play(open_builds=True, build_options=options(), wonder_job=job)["ui"]["wonder"]
        self.assertEqual(len(ui["progress"]), 8)
        self.assertEqual(ui["status"], "Design ready")
        self.assertFalse(ui["button_disabled"])

    def test_three_poll_retries_then_explains_where_to_find_the_result(self):
        job = {"polls": [[503, {"detail": "offline"}]] * 5}
        result = play(open_builds=True, build_options=options(), wonder_job=job)
        ui = result["ui"]["wonder"]
        self.assertEqual(len([r for r in result["requests"] if "/jobs/" in r]), 4)
        self.assertEqual(ui["status"], "Lost contact with the design job. It may still finish: reopen What can I "
                         "build? to see it under Saved designs for these pieces.")
        self.assertFalse(ui["button_disabled"])

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
                self.assertEqual(len(ui["progress"]), 1)

    def test_service_worker_cache_is_version_17(self):
        worker = (Path(__file__).resolve().parent.parent / "app" / "sw.js").read_text()
        self.assertIn("var CACHE_NAME = 'binbuild-v17';", worker)
