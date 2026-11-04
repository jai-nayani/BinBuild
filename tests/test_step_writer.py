"""Spark can write booklet words, but cannot change a checked design."""

import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import step_writer, wonder_design, wonder_designer
from backend.spark_client import SparkError, SparkReply


def checked_booklet():
    return {
        "title": "Wonder House",
        "subtitle": "2 pieces, 2 steps.",
        "source": "the pieces in your bin",
        "notes": ["Nobody has built it yet."],
        "placements": [
            {"part": {"color": "red", "size": "1x2", "family": "brick"}, "at": [0, 0, 0]},
            {"part": {"color": "dark_blue", "size": "1x2", "family": "plate"}, "at": [0, 0, 3]},
        ],
        "parts": [{"label": "red 1x2 brick", "qty": 1}, {"label": "dark blue 1x2 plate", "qty": 1}],
        "steps": [
            {"n": 1, "text": "Original first step.", "add": [0],
             "parts": [{"label": "red 1x2 brick", "qty": 1}]},
            {"n": 2, "text": "Original second step.", "add": [1],
             "parts": [{"label": "dark blue 1x2 plate", "qty": 1}]},
        ],
    }


class FakeSpark:
    def __init__(self, data=None, error=None, finish_reason="stop"):
        self.data = data
        self.error = error
        self.finish_reason = finish_reason
        self.calls = []

    def chat(self, messages):
        self.calls.append(messages)
        if self.error:
            raise self.error
        return SparkReply(json.dumps(self.data), self.finish_reason, {}, 0.0)


def good_reply():
    return {"title": "Little House", "steps": [
        {"n": 1, "text": "Put the red brick on the table."},
        {"n": 2, "text": "Press the dark blue plate on top."},
    ]}


class StepWriterTest(unittest.TestCase):
    def setUp(self):
        self.book = checked_booklet()
        self.cover = patch("backend.step_writer.bk.cover", return_value=(
            '<svg><image href="data:image/png;base64,aGVsbG8="/></svg>'))
        self.cover.start()
        self.addCleanup(self.cover.stop)

    def write(self, spark):
        return step_writer.write_steps(self.book, "a house", spark)

    def test_good_reply_changes_only_words_and_sends_cover_and_layers(self):
        before = copy.deepcopy(self.book)
        spark = FakeSpark(good_reply())
        result = self.write(spark)
        self.assertEqual(result["title"], "Little House")
        self.assertEqual([s["text"] for s in result["steps"]],
                         ["Put the red brick on the table.", "Press the dark blue plate on top."])
        self.assertEqual(result["placements"], before["placements"])
        self.assertEqual(result["parts"], before["parts"])
        self.assertEqual([s["add"] for s in result["steps"]], [s["add"] for s in before["steps"]])
        self.assertEqual([s["parts"] for s in result["steps"]], [s["parts"] for s in before["steps"]])
        self.assertEqual(self.book, before)
        self.assertEqual(result["notes"], before["notes"] + [step_writer.SUCCESS_NOTE])
        self.assertEqual(len(spark.calls), 1)
        content = spark.calls[0][0]["content"]
        self.assertEqual(content[1]["image_url"]["url"], "data:image/png;base64,aGVsbG8=")
        self.assertIn('"layer_heights_in_plates": [3]', content[0]["text"])
        self.assertIn('"label": "dark blue 1x2 plate"', content[0]["text"])

    def test_wrong_count_keeps_all_original_step_texts(self):
        result = self.write(FakeSpark({"title": "Short", "steps": [{"n": 1, "text": "New."}]}))
        self.assertEqual([s["text"] for s in result["steps"]], [s["text"] for s in self.book["steps"]])
        self.assertIn(step_writer.FALLBACK_NOTE, result["notes"])

    def test_wrong_color_keeps_only_that_original_step(self):
        data = good_reply()
        data["steps"][0]["text"] = "Put the green brick on the table."
        result = self.write(FakeSpark(data))
        self.assertEqual(result["steps"][0]["text"], self.book["steps"][0]["text"])
        self.assertEqual(result["steps"][1]["text"], data["steps"][1]["text"])

    def test_multiword_colors_do_not_count_as_separate_colors(self):
        self.assertEqual(step_writer._colors_in("a dark blue plate"), {"dark_blue"})
        self.assertEqual(step_writer._colors_in("a light bluish gray brick"), {"light_bluish_gray"})
        self.assertEqual(step_writer._colors_in("a lime green tile"), {"lime"})

    def test_error_keeps_original_words_and_notes(self):
        result = self.write(FakeSpark(error=SparkError("offline")))
        self.assertEqual(result["title"], self.book["title"])
        self.assertEqual(result["steps"], self.book["steps"])
        self.assertEqual(result["notes"], self.book["notes"] + [step_writer.FALLBACK_NOTE])

    def test_incorrect_step_numbers_keep_original_words(self):
        data = good_reply()
        data["steps"][0]["n"] = 2
        result = self.write(FakeSpark(data))
        self.assertEqual(result["steps"], self.book["steps"])
        self.assertIn(step_writer.FALLBACK_NOTE, result["notes"])

    def test_invalid_title_and_step_lengths_are_ignored(self):
        data = good_reply()
        data["title"] = "No"
        data["steps"][0]["text"] = " "
        data["steps"][1]["text"] = "a" * 241
        result = self.write(FakeSpark(data))
        self.assertEqual(result["title"], self.book["title"])
        self.assertEqual(result["steps"], self.book["steps"])

    def test_cut_off_reply_keeps_original_words(self):
        result = self.write(FakeSpark(good_reply(), finish_reason="length"))
        self.assertEqual(result["steps"], self.book["steps"])
        self.assertIn(step_writer.FALLBACK_NOTE, result["notes"])


class RealCoverTest(unittest.TestCase):
    def test_recorded_design_cover_is_sent_as_png(self):
        design = Path(__file__).resolve().parent.parent / "backend/designs/wonder-simple-house.txt"
        pieces, errors = wonder_design.parse(design.read_text())
        self.assertEqual(errors, [])
        book = wonder_designer.make_booklet("Simple House", pieces, "a simple house")
        spark = FakeSpark({"title": "Simple House", "steps": [
            {"n": step["n"], "text": step["text"]} for step in book["steps"]
        ]})
        result = step_writer.write_steps(book, "a simple house", spark)
        self.assertEqual(len(spark.calls), 1)
        url = spark.calls[0][0]["content"][1]["image_url"]["url"]
        self.assertTrue(url.startswith("data:image/png;base64,iVBORw0KGgo"))
        self.assertEqual(result["placements"], book["placements"])
        self.assertIn(step_writer.SUCCESS_NOTE, result["notes"])


if __name__ == "__main__":
    unittest.main()
