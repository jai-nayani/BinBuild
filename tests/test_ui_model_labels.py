"""Phone model attribution and honest progress, using the real app with fakes."""

import copy
import unittest
from pathlib import Path

from test_ui_carousel import OPTIONS, detection, play, review_body
from test_wonder_ui_jobs import options


class TestModelPresentation(unittest.TestCase):
    def review(self, sample=False, masks=True):
        piece = detection(1, "brick", "brick", "1x2", "red", .9, False, point=[100, 100])
        if masks:
            piece["region"]["mask"] = {"path": "M0 0L10 0L10 10Z", "box": [90, 90, 110, 110], "size": [10, 10]}
        body = review_body([piece])
        if sample:
            body["batch"]["classifier"] = "sample: recorded"
        return play(use_sample=True, review=body, review_visuals=True)["ui"]

    def test_live_masks_toggle_and_enlarge_without_moving_coordinates(self):
        ui = self.review()
        self.assertEqual(ui["masks"]["model"], "✂ Cut out by SAM 3.1")
        self.assertEqual(ui["masks"]["caption"], "Each outline is one piece, cut out by SAM 3.1 (1 of 1)")
        self.assertTrue(ui["masks"]["masks_visible"])
        self.assertFalse(ui["masks"]["dots_visible"])
        self.assertEqual(ui["dots"]["toggle"], "Show SAM masks")
        self.assertFalse(ui["dots"]["masks_visible"])
        self.assertTrue(ui["dots"]["dots_visible"])
        self.assertTrue(ui["enlarged"]["photo_expanded"])
        self.assertFalse(ui["shrunk"]["photo_expanded"])
        for key in ("dots", "outlines"):
            self.assertEqual(ui["dots"][key], ui["enlarged"][key])

    def test_sample_outlines_are_recorded_and_no_masks_means_no_chip(self):
        ui = self.review(sample=True)["masks"]
        self.assertEqual(ui["model"], "✂ Recorded SAM 3.1 outlines")
        self.assertEqual(ui["caption"], "Recorded SAM 3.1 outlines (Oct 28). Each outline is one piece.")
        ui = self.review(masks=False)["masks"]
        self.assertIsNone(ui["model"])
        self.assertIsNone(ui["toggle"])
        self.assertTrue(ui["dots_visible"])

    def test_ideas_tracker_only_advances_on_server_stages_and_cards_have_chips(self):
        o = options()
        o["wonder"]["ideas"] = []
        choices = options()["wonder"]["ideas"]
        polls = [[200, {"state": "running", "stage": stage, "message": stage}] for stage in ("designing", "checking")]
        polls.append([200, {"state": "done", "stage": "done", "message": "Ready", "ideas": choices}])
        ui = play(open_builds=True, build_options=o, wonder_job={"find": True, "polls": polls})["ui"]["wonder"]
        self.assertEqual([[s["state"] for s in p["tracker"]] for p in ui["progress"]], [
            ["active", "waiting"], ["done", "active"], ["done", "done"]])
        self.assertIn("✨ Designed by Muse Wonder · ✓ checked by BinBuild", ui["ideas"][0])

    def test_booklet_tracker_and_conditional_spark_chip(self):
        for words in ("muse-spark", "binbuild", None):
            with self.subTest(words=words):
                build = {"title": "Lookout", "booklet_url": "/api/builds/7/booklet", "step_words": words}
                polls = [[200, {"state": "running", "stage": stage}] for stage in ("checking", "writing")]
                polls.append([200, {"state": "done", "stage": "done", "build": build}])
                ui = play(open_builds=True, build_options=options(), wonder_job={"polls": polls, "open_link": True})["ui"]["wonder"]
                self.assertEqual([[s["state"] for s in p["tracker"]] for p in ui["progress"]], [
                    ["active", "waiting", "waiting"], ["done", "active", "waiting"],
                    ["done", "done" if words == "muse-spark" else "failed" if words == "binbuild" else "waiting", "done"]])
                self.assertIn("Designed by Muse Wonder", ui["booklet"]["chips"])
                self.assertEqual("Steps written by Muse Spark" in ui["booklet"]["chips"], words == "muse-spark")
        self.assertEqual(play(open_builds=True, build_options=copy.deepcopy(OPTIONS), tap_card=0)["ui"]["booklet"]["chips"], [])

    def test_masks_finish_fading_within_one_and_a_half_seconds_and_respect_reduced_motion(self):
        css = (Path(__file__).resolve().parent.parent / "app/style.css").read_text()
        self.assertIn("animation: mask-appear 0.3s both", css)
        self.assertIn(".outlines path { animation: none; }", css.split("@media (prefers-reduced-motion: reduce)")[1])
