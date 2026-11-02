"""The PWA as an instruction booklet (app/index.html, app/style.css, app/app.js).

- the page: a cover, then steps 1-9 in order; steps 2-6 are the 5 photos in
  the order the backend expects; every photo step shows a "1x photo" callout
  with its angle drawing and a hint before its "Open camera" (the native
  camera input, capture="environment"); no other file input, so never a
  bare upload form; the "not affiliated" footer stays;
- the font: Nunito bundled with its licence, nothing loaded from elsewhere,
  and in the service worker's offline shell;
- motion: scroll-driven animation only inside @supports, so a browser without
  it (Firefox) shows every page plainly; reduced motion stops everything;
  the snap keyframes exist;
- behaviour (the real app.js in Node, tests/retake_popup_harness.js): the
  step to do now moves along with the photos; a taken photo's number is
  yellow, turns green with a snap only when it passes the photo check (a
  failed one turns red, then green after its retake); on the public demo a
  refused Identify (401) offers the sample bin and leads to step 9, and no
  Wonder or Model API route is ever called.

Standard-library unittest. Run from the repo root:
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
    from backend import photo_gate
except ImportError:                  # Pillow not installed
    photo_gate = None

APP = Path(__file__).resolve().parent.parent / "app"
HARNESS = Path(__file__).resolve().parent / "retake_popup_harness.js"
NODE = shutil.which("node")
VIEWS = ("top", "front", "right", "back", "left")
CSS = (APP / "style.css").read_text()


class Page(HTMLParser):
    """Every element as (tag, attrs, its text), in document order, plus each element's parents."""

    VOID = {"input", "img", "br", "hr", "meta", "link", "source", "rect", "circle", "path"}

    def __init__(self):
        super().__init__()
        self.elements, self.stack = [], []

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "attrs": dict(attrs), "text": "", "parents": [e["attrs"].get("id") for e in self.stack],
                "classes": set(dict(attrs).get("class", "").split())}
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
    p.feed((APP / "index.html").read_text())
    return p.elements


def inside(elements, section_id):
    return [e for e in elements if section_id in e["parents"]]


def blocks(css, at_rule):
    """The text of every block opened by a line starting with at_rule (brace-matched)."""
    out = []
    for m in re.finditer(re.escape(at_rule), css):
        start = css.index("{", m.end())
        depth, i = 0, start
        while True:
            depth += {"{": 1, "}": -1}.get(css[i], 0)
            if depth == 0:
                break
            i += 1
        out.append((m.start(), i, css[start + 1:i]))
    return out


class TestBookletPage(unittest.TestCase):
    def test_cover_then_nine_steps_in_order(self):
        sections = [e for e in page() if e["tag"] == "section"]
        self.assertEqual([s["attrs"]["id"] for s in sections], ["cover"] + [f"step-{n}" for n in range(1, 10)])
        numbers = [e for e in page() if "step-no" in e["classes"]]
        self.assertEqual([e["text"] for e in numbers], [str(n) for n in range(1, 10)])
        self.assertIn("flat layer", sections[1]["text"])

    def test_photo_steps_follow_the_upload_order(self):
        shots = [e for e in page() if e["tag"] == "section" and "shot" in e["classes"]]
        self.assertEqual([s["attrs"]["data-view"] for s in shots], list(VIEWS))
        self.assertEqual([s["attrs"]["id"] for s in shots], [f"step-{n}" for n in range(2, 7)])
        views = re.findall(r"\{ key: '(\w+)', label:", (APP / "app.js").read_text())
        self.assertEqual(tuple(views), VIEWS, "the steps follow app.js's VIEWS, the order files are uploaded in")

    def test_every_photo_step_guides_before_the_camera(self):
        elements = page()
        for n, view in enumerate(VIEWS, 2):
            with self.subTest(view=view):
                step = inside(elements, f"step-{n}")
                qty = [e for e in step if "qty" in e["classes"]]
                self.assertEqual([e["text"] for e in qty], ["1x photo"])
                drawing = [i for i, e in enumerate(step) if e["tag"] == "svg" and f"angle-{view}" in e["classes"]]
                hint = [i for i, e in enumerate(step) if "hint" in e["classes"]]
                camera = [i for i, e in enumerate(step)
                          if e["tag"] == "label" and e["attrs"].get("for") == "camera-input"]
                self.assertEqual(len(drawing), 1)
                self.assertEqual([step[i]["text"] for i in camera], ["Open camera"])
                self.assertTrue(drawing[0] < hint[0] < camera[0], "drawing, then hint, then the camera")

    def test_native_camera_inputs_only(self):
        inputs = {e["attrs"]["id"]: e["attrs"] for e in page()
                  if e["tag"] == "input" and e["attrs"].get("type") == "file"}
        self.assertEqual(set(inputs), {"camera-input", "gallery-input", "retake-input"})
        for name in ("camera-input", "retake-input"):
            self.assertEqual((inputs[name].get("capture"), inputs[name].get("accept")), ("environment", "image/*"))
        self.assertFalse([e for e in page() if e["tag"] == "form"], "no upload form")

    def test_footer_and_no_brand_artwork(self):
        footer = [e for e in page() if e["tag"] == "footer"]
        self.assertIn("Not affiliated with the LEGO Group", footer[0]["text"])
        html = (APP / "index.html").read_text().lower()
        self.assertNotIn("<img src", html)
        self.assertNotIn("lego", CSS.lower())

    def test_nothing_loaded_from_elsewhere(self):
        for name in ("index.html", "style.css", "app.js", "sw.js"):
            text = (APP / name).read_text()
            self.assertNotRegex(text, r"(href|src)=\"https?://|url\(\"?https?://", name)
            self.assertNotIn("fonts.googleapis", text, name)
            self.assertNotIn("fonts.gstatic", text, name)


class TestFont(unittest.TestCase):
    def test_nunito_is_bundled_with_its_licence(self):
        face = blocks(CSS, "@font-face")[0][2]
        src = re.search(r'url\("([^"]+)"\)', face).group(1)
        self.assertIn("Nunito", face)
        self.assertTrue((APP / src).read_bytes().startswith(b"wOF2"), src)
        self.assertIn("SIL Open Font License", (APP / "fonts" / "OFL.txt").read_text())
        self.assertRegex(CSS, r"body \{[^}]*font-family: \"Nunito\"")

    def test_offline_shell_has_the_style_and_font(self):
        sw = (APP / "sw.js").read_text()
        for path in ("./style.css", "./fonts/nunito-latin.woff2", "./app.js", "./index.html"):
            self.assertIn(f"'{path}'", sw)
            self.assertTrue((APP / path).exists(), path)


class TestMotion(unittest.TestCase):
    def test_scroll_driven_animation_only_where_supported(self):
        supported = blocks(CSS, "@supports (animation-timeline")
        self.assertTrue(supported)
        for m in re.finditer(r"animation-timeline:", CSS):
            self.assertTrue(any(start < m.start() < end for start, end, _ in supported),
                            "animation-timeline outside @supports: a browser without it would misread the rule")
        for _, _, body in supported:
            self.assertIn("prefers-reduced-motion: no-preference", body)

    def test_without_support_every_page_shows(self):
        outside = CSS
        for start, end, _ in sorted(blocks(CSS, "@supports"), reverse=True):
            outside = outside[:start] + outside[end + 1:]
        for rule in re.findall(r"\.page[^{]*\{[^}]*\}", outside):
            self.assertNotIn("opacity", rule)
            self.assertNotIn("animation", rule)

    def test_reduced_motion_stops_everything(self):
        reduce = blocks(CSS, "@media (prefers-reduced-motion: reduce)")[0][2]
        self.assertIn("animation: none !important", reduce)
        self.assertIn("scroll-behavior: auto", reduce)

    def test_the_snap(self):
        self.assertRegex(CSS, r"\.step-no\.snap \{ animation: snap ")
        self.assertIn("@keyframes snap", CSS)
        self.assertRegex(CSS, r"\.step-no\.passed \{[^}]*background: var\(--green\)")
        self.assertRegex(CSS, r"\.step-no\.taken \{[^}]*background: var\(--yellow\)")


def play(fail, identify=None):
    notices = {v: photo_gate.retake_notice(v, ["blurry"]) for v in VIEWS}
    scenario = {"notices": notices, "fail": list(fail), **({"identify": identify} if identify else {})}
    out = subprocess.run([NODE, str(HARNESS), json.dumps(scenario)], capture_output=True, text=True, timeout=60,
                         check=True)
    return json.loads(out.stdout)


@unittest.skipUnless(NODE and photo_gate, "Node or Pillow not installed")
class TestBookletBehaviour(unittest.TestCase):
    def test_the_step_to_do_now_moves_along(self):
        b = play([])["booklet"]
        self.assertEqual(b["current_after_first"], ["step-3"])
        self.assertEqual(b["current_before_upload"], ["step-7"])
        self.assertTrue(all(b["sheet_open_" + v] for v in VIEWS), "every photo is checked on the sheet first")

    def test_numbers_turn_green_only_when_the_photo_passes(self):
        b = play([])["booklet"]
        self.assertEqual(b["before_upload"], {v: ["taken"] for v in VIEWS})
        self.assertEqual(b["after_upload"], {v: ["passed", "snap"] for v in VIEWS})

    def test_a_failed_photo_is_red_until_its_retake_passes(self):
        result = play(["front", "back"])
        b = result["booklet"]
        self.assertEqual(b["after_upload"]["front"], ["failed"])
        self.assertEqual(b["after_upload"]["back"], ["failed"])
        self.assertEqual(b["after_upload"]["top"], ["passed", "snap"])
        self.assertEqual(b["at_end"], {v: ["passed", "snap"] for v in VIEWS})
        self.assertEqual([p["uploaded_as"] for p in result["popups"]], ["front", "back"])

    def test_public_demo_offers_the_sample_bin(self):
        result = play([], identify=401)
        b = result["booklet"]
        self.assertEqual(b["sample_offer"], {"shown": True, "button": "Use the sample bin (50 pieces)"})
        self.assertEqual(b["current_after_sample"], ["step-9"])
        self.assertIn("GET /api/builds/options", result["requests"])
        self.assertFalse([r for r in result["requests"] if "wonder" in r], "no Wonder call")

    def test_no_sample_offer_unless_identify_is_refused(self):
        self.assertNotIn("sample_offer", play([])["booklet"])
        self.assertIn('class="callout hidden" id="sample-offer"', (APP / "index.html").read_text())


if __name__ == "__main__":
    unittest.main()
