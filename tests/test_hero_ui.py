"""The hero and the capture hub (app/index.html, app/style.css, app/app.js).

- hero: the first screen; the name, the tagline, 3 beats (scatter, identify,
  build), an inline SVG of generic bricks that assemble with plain CSS
  keyframes (no video, no image files, nothing loaded from elsewhere; with
  reduced motion the bricks just sit built), "Get started", the sample-bin
  link, the backend status line and the "not affiliated" footer;
- capture hub: a 3-column grid of 6 panels in order (tip out one flat layer,
  top, front, right, back, left); the 5 photo panels open the same native
  camera input (capture="environment"); no other file inputs;
- phone app: the manifest stays standalone and lists real PNG icons (192,
  512, a maskable 512); a 180x180 apple-touch-icon is linked; all of them are
  in the offline shell;
- behaviour (the real app.js in Node, tests/retake_popup_harness.js): Get
  started opens the hub; panels go next -> taken -> clear or retake; Next
  stays disabled until all 5 photos pass the check; a tapped panel's photo
  lands in that slot and the batch still uploads top, front, right, back, left;
  tapping a red panel opens that photo's retake; a refused Identify (401)
  offers the sample bin and loads it for review; no Wonder or Model API call.

Standard-library unittest. Run from the repo root:
    python3 -m unittest discover -s tests -v
"""

import json
import re
import shutil
import struct
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path

try:
    from backend import photo_gate
except ImportError:                  # Pillow not installed
    photo_gate = None

APP = Path(__file__).resolve().parent.parent / "app"
HARNESS = Path(__file__).resolve().parent / "retake_popup_harness.js"
NODE = shutil.which("node")
VIEWS = ("top", "front", "right", "back", "left")
HTML = (APP / "index.html").read_text()
CSS = (APP / "style.css").read_text()


class Page(HTMLParser):
    """Every element in document order, with its attributes, classes, the ids of its parents and its text."""

    VOID = {"input", "img", "br", "hr", "meta", "link", "rect", "path", "circle"}

    def __init__(self):
        super().__init__()
        self.elements, self.stack = [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        node = {"tag": tag, "attrs": attrs, "classes": set(attrs.get("class", "").split()), "text": "",
                "parents": [e["attrs"].get("id") for e in self.stack]}
        self.elements.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID and self.stack:
            self.stack.pop()

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i]["tag"] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        for node in self.stack:
            node["text"] += data


def page():
    p = Page()
    p.feed(HTML)
    return p.elements


def by_id(elements, id_):
    return next(e for e in elements if e["attrs"].get("id") == id_)


def inside(elements, id_):
    return [e for e in elements if id_ in e["parents"]]


def png_size(path):
    """(width, height, colour type) from the PNG header: type 2 is RGB, 6 is RGBA."""
    data = path.read_bytes()[:26]
    assert data[:8] == b"\x89PNG\r\n\x1a\n", path
    width, height = struct.unpack(">II", data[16:24])
    return width, height, data[25]


class TestHero(unittest.TestCase):
    def test_the_hero_is_the_first_screen(self):
        elements = page()
        views = [e for e in elements if e["tag"] == "section"]
        self.assertEqual(views[0]["attrs"]["id"], "hero-view")
        self.assertNotIn("hidden", views[0]["classes"])
        self.assertTrue(all("hidden" in v["classes"] for v in views[1:]), "every other screen starts hidden")
        self.assertIn('<body class="on-hero">', HTML)

    def test_name_tagline_beats_and_actions(self):
        hero = inside(page(), "hero-view")
        self.assertEqual([e["text"] for e in hero if e["tag"] == "h1"], ["BinBuild"])
        self.assertIn("Your spare parts are a LEGO set you haven't opened yet.",
                      [e["text"] for e in hero if "tagline" in e["classes"]])
        beats = [e for e in hero if e["tag"] == "strong"]
        self.assertEqual([b["text"] for b in beats], ["Scatter", "Identify", "Build"])
        buttons = {e["attrs"].get("id"): e["text"] for e in hero if e["tag"] == "button"}
        self.assertEqual(buttons["start-btn"], "Get started")
        self.assertEqual(buttons["sample-link"], "Just looking? See what the sample bin builds")
        elements = page()
        self.assertTrue(by_id(elements, "backend-line"))
        self.assertIn("Not affiliated with the LEGO Group", [e for e in elements if e["tag"] == "footer"][0]["text"])

    def test_the_animation_is_inline_bricks_only(self):
        hero = inside(page(), "hero-view")
        art = [e for e in hero if e["tag"] == "svg" and "hero-art" in e["classes"]]
        self.assertEqual(len(art), 1)
        bricks = [e for e in inside(page(), "hero-view") if e["tag"] == "g" and "brick" in e["classes"]]
        self.assertGreaterEqual(len(bricks), 6)
        for b in bricks:
            self.assertRegex(b["attrs"]["style"], r"--dx:-?\d+px;--dy:-?\d+px;--r:-?\d+deg;--d:[\d.]+s")
        self.assertFalse([e for e in hero if e["tag"] in ("img", "video", "image", "picture", "object")])
        self.assertNotIn("<text", HTML.split('id="hero-view"')[1].split("</section>")[0], "no lettering in the art")

    def test_plain_css_motion_with_a_still_final_frame(self):
        self.assertNotIn("animation-timeline", CSS, "no scroll-driven CSS: the same in every browser")
        self.assertRegex(CSS, r"\.hero-art \.brick \{[^}]*animation: assemble ")
        self.assertIn("@keyframes assemble", CSS)
        self.assertRegex(CSS, r"100% \{ transform: none; \}", "the last frame is the built house")
        reduce = CSS.split("@media (prefers-reduced-motion: reduce)")[1]
        self.assertRegex(reduce, r"\.hero-art \.brick \{ animation: none; \}")

    def test_nothing_loaded_from_elsewhere(self):
        for name in ("index.html", "style.css", "app.js", "sw.js", "manifest.json"):
            text = (APP / name).read_text()
            self.assertNotRegex(text, r"(href|src)=\"https?://|url\(\"?https?://|\"src\": \"https?://", name)


class TestCaptureGrid(unittest.TestCase):
    def test_six_panels_in_three_columns(self):
        grid = inside(page(), "grid")
        panels = [e for e in grid if "panel" in e["classes"]]
        self.assertEqual([p["attrs"]["id"] for p in panels], ["panel-tip"] + [f"panel-{v}" for v in VIEWS])
        self.assertIn("Tip out one flat layer", panels[0]["text"])
        self.assertRegex(CSS, r"\.grid \{[^}]*grid-template-columns: repeat\(3, minmax\(0, 1fr\)\)")

    def test_photo_panels_open_the_native_camera(self):
        elements = page()
        for v in VIEWS:
            panel = by_id(elements, f"panel-{v}")
            self.assertEqual((panel["tag"], panel["attrs"].get("for")), ("label", "camera-input"), v)
            self.assertEqual(panel["attrs"].get("tabindex"), "0", "reachable from the keyboard")
        self.assertEqual(by_id(elements, "panel-tip")["tag"], "button", "the tip panel opens no camera")

    def test_same_camera_inputs_no_upload_form(self):
        inputs = {e["attrs"]["id"]: e["attrs"] for e in page()
                  if e["tag"] == "input" and e["attrs"].get("type") == "file"}
        self.assertEqual(set(inputs), {"camera-input", "gallery-input", "retake-input", "piece-input"})
        for name in ("camera-input", "retake-input", "piece-input"):
            self.assertEqual((inputs[name].get("capture"), inputs[name].get("accept")), ("environment", "image/*"))
        self.assertFalse([e for e in page() if e["tag"] == "form"])

    def test_next_starts_disabled(self):
        nxt = by_id(page(), "identify-btn")
        self.assertIn("disabled", nxt["attrs"])
        self.assertEqual(nxt["text"], "Next: identify the pieces")


class TestPhoneApp(unittest.TestCase):
    def test_manifest_icons(self):
        m = json.loads((APP / "manifest.json").read_text())
        self.assertEqual(m["display"], "standalone")
        pngs = {(i["src"], i["sizes"], i["purpose"]) for i in m["icons"] if i["type"] == "image/png"}
        self.assertEqual(pngs, {("icon-192.png", "192x192", "any"), ("icon-512.png", "512x512", "any"),
                                ("icon-maskable-512.png", "512x512", "maskable")})
        for src, sizes, _ in pngs:
            w, h, _ = png_size(APP / src)
            self.assertEqual(f"{w}x{h}", sizes, src)
        self.assertEqual(png_size(APP / "icon-maskable-512.png")[2], 2, "maskable: full-bleed, no transparency")

    def test_apple_touch_icon(self):
        link = [e for e in page() if e["tag"] == "link" and e["attrs"].get("rel") == "apple-touch-icon"]
        self.assertEqual([(e["attrs"]["href"], e["attrs"].get("sizes")) for e in link],
                         [("apple-touch-icon.png", "180x180")])
        self.assertEqual(png_size(APP / "apple-touch-icon.png"), (180, 180, 2), "180x180 and opaque, as iOS wants")
        metas = {e["attrs"].get("name"): e["attrs"].get("content") for e in page() if e["tag"] == "meta"}
        self.assertEqual(metas.get("apple-mobile-web-app-capable"), "yes")
        self.assertIn('<link rel="manifest" href="manifest.json">', HTML)

    def test_offline_shell(self):
        sw = (APP / "sw.js").read_text()
        for f in ("style.css", "icon-192.png", "icon-512.png", "icon-maskable-512.png", "apple-touch-icon.png"):
            self.assertIn(f"'./{f}'", sw)
            self.assertTrue((APP / f).is_file(), f)
        # it fetches from the server, never from the browser's HTTP cache, which may hold an old page
        self.assertIn("new Request(url, { cache: 'reload' })", sw)
        self.assertIn("cache: 'no-cache'", sw)
        if shutil.which("node"):
            subprocess.run(["node", "--check", str(APP / "sw.js")], check=True, capture_output=True)


def play(**scenario):
    notices = {v: photo_gate.retake_notice(v, ["blurry"]) for v in VIEWS}
    out = subprocess.run([NODE, str(HARNESS), json.dumps({"notices": notices, "fail": [], **scenario})],
                         capture_output=True, text=True, timeout=60, check=True)
    return json.loads(out.stdout)


@unittest.skipUnless(NODE and photo_gate, "Node or Pillow not installed")
class TestBehaviour(unittest.TestCase):
    def test_get_started_opens_the_hub(self):
        ui = play()["ui"]
        self.assertEqual((ui["hero_at_start"], ui["capture_at_start"]), (True, False))
        self.assertEqual((ui["hero_after_start"], ui["capture_after_start"]), (False, True))
        self.assertEqual(ui["panels_at_start"], {"top": ["next"], **{v: [] for v in VIEWS[1:]}})

    def test_panel_states_and_next(self):
        ui = play(fail=["front"])["ui"]
        self.assertEqual(ui["panels_before_upload"], {v: ["taken"] for v in VIEWS})
        self.assertFalse(ui["next_enabled_before_upload"])
        self.assertEqual(ui["panels_after_upload"]["front"], ["failed"])
        self.assertEqual(ui["panels_after_upload"]["top"], ["passed", "locked"])
        self.assertFalse(ui["next_enabled_after_upload"], "Next waits until every photo passes")
        self.assertEqual(ui["panels_at_end"], {v: ["passed", "locked"] for v in VIEWS})
        self.assertTrue(ui["next_enabled_at_end"])

    def test_a_tapped_panel_takes_that_photo(self):
        result = play(order=["left", "top", "back", "right", "front"])
        self.assertEqual(result["batch_upload"], [f"{n}-{v}.jpg" for n, v in enumerate(VIEWS, 1)])
        self.assertEqual(result["batch_sources"], [f"shot-{v}.jpg" for v in VIEWS], "each photo in its own slot")

    def test_tapping_a_red_panel_retakes_that_photo(self):
        result = play(fail=["front", "back"], tap_failed="back")
        self.assertEqual(result["ui"]["tapped_failed_opens"], "The back photo is unclear")
        self.assertEqual([p["uploaded_as"] for p in result["popups"]], ["back", "front"])
        self.assertFalse(result["modal_open_at_end"])

    def test_refused_identify_offers_the_sample_bin(self):
        result = play(identify=401)
        self.assertEqual(result["ui"]["sample_offer"], {"shown": True, "button": "Use the sample bin (50 pieces)"})
        self.assertEqual(result["ui"]["view_after_sample"], ["check-view"], "the sample bin, ready for review")
        self.assertIn("POST /api/inventory/sample", result["requests"])

    def test_no_wonder_or_model_calls(self):
        for scenario in ({}, {"fail": ["right"]}, {"identify": 401}):
            requests = play(**scenario)["requests"]
            self.assertFalse([r for r in requests if "wonder" in r], scenario)
            self.assertEqual([r for r in requests if "/classify" in r],
                             ["POST /api/inventory/batch/b1/classify?segmenter=stub"] if scenario.get("identify") else [])


if __name__ == "__main__":
    unittest.main()
