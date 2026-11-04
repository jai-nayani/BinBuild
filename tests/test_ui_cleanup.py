"""Capture and review clean-ups preserve the existing API actions."""

import json
import unittest
from pathlib import Path

from test_ui_carousel import VOCAB, detection, play, review_body


class TestCleanPhoneFlow(unittest.TestCase):
    def test_capture_has_only_one_main_action_and_secondary_sample_link(self):
        ui = play()["ui"]
        self.assertEqual(ui["capture_before"], {"upload": True, "identify": False})
        self.assertEqual(ui["capture_after"], {"upload": False, "identify": True})
        ui = play(fail=["front"])["ui"]
        self.assertEqual(ui["capture_after"], {"upload": True, "identify": False})
        self.assertEqual(ui["capture_end"], {"upload": False, "identify": True})
        html = (Path(__file__).resolve().parent.parent / "app/index.html").read_text()
        self.assertIn('class="btn btn-link" id="sample-images-btn">No pieces handy? Use the sample pieces</button>', html)

    def test_unsure_pieces_are_first_and_other_rows_are_collapsed(self):
        pieces = [detection(n, "brick", "brick", "1x2", "red", .9, n in (2, 4)) for n in range(1, 5)]
        ui = play(use_sample=True, review=review_body(pieces), review_visuals=True)["ui"]["masks"]
        self.assertEqual(ui["folded"], [{"summary": "✓ 2 pieces look right", "open": False}])
        self.assertEqual([g["buttons"] for g in ui["groups"][:2]], [["Fix", "📷 Retake this piece"]] * 2)
        self.assertIn("One by one ▾", ui["groups"][2]["buttons"])
        self.assertFalse(any("Remove" in b for g in ui["groups"] for b in g["buttons"]))

    def test_confirm_and_undo_send_the_same_accept_confirm_and_undo_requests(self):
        pieces = [detection(1, "brick", "brick", "1x2", "red", .9, False),
                  detection(2, "plate", "plate", "1x2", "blue", .9, False, status="corrected")]
        ui = play(use_sample=True, vocab=VOCAB, review=review_body(pieces), confirm_undo=True)["ui"]
        sent = ui["lifecycle_requests"]
        self.assertEqual([(r["method"], r["path"]) for r in sent], [
            ("POST", "/api/inventory/batch/sample1/review"),
            ("POST", "/api/inventory/batch/sample1/confirm"),
            ("GET", "/api/inventory/batch/sample1/review"),
            ("POST", "/api/inventory/undo-last-batch?batch_id=sample1"),
            ("GET", "/api/inventory/batch/sample1/review"),
        ])
        self.assertEqual(json.loads(sent[0]["json"]), {"corrections": [{"detection_id": 1, "status": "accepted"}]})
        self.assertTrue(all(r["json"] is None for r in sent[1:]))
        self.assertIn("Took 2 pieces", ui["after_undo"]["status"])

    def test_backend_line_only_appears_when_unreachable(self):
        self.assertFalse(play()["ui"]["backend"]["shown"])
        down = play(backend_down=True)["ui"]["backend"]
        self.assertTrue(down["shown"])
        self.assertIn("not reachable", down["text"])

    def test_legacy_generator_names_and_confidence_claims_are_not_rendered(self):
        body = review_body([detection(1, "brick", "brick", "1x2", "red", .99, False)])
        body["detections"][0]["generator_type"] = "1x2"
        ui = play(use_sample=True, review=body, review_visuals=True)["ui"]["masks"]
        self.assertNotIn("BrickGPT", json.dumps(ui))
        js = (Path(__file__).resolve().parent.parent / "app/app.js").read_text()
        self.assertNotIn("% sure", js)
        self.assertNotIn("edit-generator", js)
