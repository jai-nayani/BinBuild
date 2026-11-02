"""The retake pop-up names and shows the same view (bug from the Oct 31 trial).

The review screen's "↺ Retake" button and the pop-up's Retake button both had
id="retake-btn". getElementById returns the first, so the pop-up wrote its
label into the hidden review button and its own button kept the page's
default, "📷 Retake top photo", whatever view had failed: the trial's blurry
front photo was retaken from above.

- every id on the page is unique;
- for each view failing alone, two failing together, and all five: the
  pop-up's title, its own Retake button, the photo in it, its "How:" hint and
  the retake upload all name the same view, one after another.

The second runs the real app/app.js in Node against a fake page built from
app/index.html (tests/retake_popup_harness.js); skipped without Node or
Pillow (the notices come from backend/photo_gate.py).
Standard-library unittest; run from the repo root:
    python3 -m unittest discover -s tests -v
"""

import json
import re
import shutil
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path

try:
    from backend import photo_gate  # the pop-up gets the backend's own retake notices
except ImportError:                  # Pillow not installed
    photo_gate = None

REPO = Path(__file__).resolve().parent.parent
HARNESS = Path(__file__).resolve().parent / "retake_popup_harness.js"
NODE = shutil.which("node")
VIEWS = ("top", "front", "right", "back", "left")
HINTS = dict(re.findall(r"\{ key: '(\w+)', label: '[^']*', hint: '([^']*)' \}", (REPO / "app" / "app.js").read_text()))


class Ids(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []

    def handle_starttag(self, tag, attrs):
        self.ids += [v for k, v in attrs if k == "id"]


def play(fail):
    notices = {v: photo_gate.retake_notice(v, ["blurry"]) for v in VIEWS}
    out = subprocess.run([NODE, str(HARNESS), json.dumps({"notices": notices, "fail": list(fail)})],
                         capture_output=True, text=True, timeout=60, check=True)
    return json.loads(out.stdout)


class TestPage(unittest.TestCase):
    def test_ids_are_unique(self):
        page = Ids()
        page.feed((REPO / "app" / "index.html").read_text())
        dupes = sorted({i for i in page.ids if page.ids.count(i) > 1})
        self.assertEqual(dupes, [], "an id used twice: the app's $(id) only ever finds the first")

    def test_hints_read(self):
        self.assertEqual(tuple(HINTS), VIEWS)


@unittest.skipUnless(NODE and photo_gate, "Node or Pillow not installed")
class TestRetakePopup(unittest.TestCase):
    def check(self, fail):
        result = play(fail)
        self.assertEqual(result["batch_upload"], [f"{n}-{v}.jpg" for n, v in enumerate(VIEWS, 1)])
        self.assertEqual([p["uploaded_as"] for p in result["popups"]], list(fail), "retaken in the order asked")
        for p, view in zip(result["popups"], fail):
            with self.subTest(fail=fail, view=view):
                self.assertEqual(p["title"], f"The {view} photo is unclear")
                self.assertEqual(p["button"], f"📷 Retake {view} photo")
                self.assertEqual(p["image"], view, "the pop-up shows the photo it names")
                self.assertEqual(p["hint"], "How: " + HINTS[view])
                self.assertEqual(p["file_name"], f"{VIEWS.index(view) + 1}-{view}.jpg")
        self.assertFalse(result["modal_open_at_end"])

    def test_each_view_alone(self):
        for view in VIEWS:
            self.check([view])

    def test_front_and_right_like_the_trial(self):
        self.check(["front", "right"])

    def test_all_five(self):
        self.check(list(VIEWS))


if __name__ == "__main__":
    unittest.main()
