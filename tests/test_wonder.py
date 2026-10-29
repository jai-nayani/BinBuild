"""Wonder designer tests: piece geometry, the validator, the retry loop, the
client and the booklet. No Model API call: Wonder is replaced by recorded or
written replies.

- geometry: every modelled part agrees with the LDraw library (when it is
  on the machine); the unidentified hinge plate is not usable;
- validator: a known-good house passes; floating pieces, pieces resting on a
  smooth top, overlaps, over-counts, unowned pieces, off-grid pieces, wrong
  directions, things on a jumper plate and models off the table fail with a
  clear error; slopes, wedge plates, the edge-stud tile, the azure curved
  slope's stud and the clip's overhang behave as LDraw says;
- loop: errors go back to Wonder; a fix passes; after 5 failures the result
  names the shortfall; the recorded live run replays to a valid design;
- client: the documented request, background polling, a clear error without
  a key, the key never in an error;
- booklet: one step per layer, heights from LDraw.

Standard-library unittest. Run from the repo root:
    python3 -m unittest discover -s tests -v
"""

import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from backend import wonder_client as wc
from backend import wonder_design as wd
from backend import wonder_designer as wdr
from test_full_loop import KIT_ITEMS

OWNED = wd.owned_from_items(KIT_ITEMS)
RECORDED = Path(__file__).resolve().parent / "fixtures" / "wonder-house-recorded.json"

HOUSE = """
# the house and tree from page 28 of the manual
6x1 (0,0,0) plate lime
1x1 (1,0,1) round_brick light_bluish_gray
1x1 (1,0,4) round_plate lime
2x1 (3,0,1) brick orange
2x1 (3,0,4) brick orange
2x1 (2,0,7) curved_slope black down=-x
2x1 (4,0,7) curved_slope black down=+x
"""


def check(text):
    return wd.validate(text, OWNED)


class TestGeometry(unittest.TestCase):
    @unittest.skipUnless((wd.LDRAW / "parts" / "3004.dat").is_file(), "LDraw library not on this machine")
    def test_parts_agree_with_ldraw(self):
        self.assertEqual(wd.verify_against_ldraw(), [])

    def test_every_owned_kind_but_the_hinge_plate_is_usable(self):
        usable = {(code, color, size) for code, color, size, _, _ in wd.usable_pieces(OWNED)}
        self.assertEqual(len(usable), 20)
        self.assertEqual(sum(n for *_, n, _ in wd.usable_pieces(OWNED)), 49)  # 50 minus the hinge plate
        self.assertFalse(any(code == "hinge_plate" for code, _, _ in usable))

    def test_heights_from_ldraw(self):
        self.assertEqual(wd.part_for("tall_side_stud_brick", "1x1", "lime").height, 5)
        self.assertEqual(wd.part_for("curved_slope", "2x1", "medium_azure").height, 4)
        self.assertEqual(wd.part_for("curved_slope", "1x2", "black").height, 2)


class TestValidator(unittest.TestCase):
    def assertFails(self, text, *phrases):
        c = check(text)
        self.assertFalse(c.ok)
        joined = "\n".join(c.errors)
        for phrase in phrases:
            self.assertIn(phrase, joined)
        return c

    def test_known_good_house(self):
        c = check(HOUSE)
        self.assertTrue(c.ok, c.errors)
        self.assertEqual(c.parts, 7)

    def test_floating_and_resting_on_smooth_tops(self):
        self.assertFails(HOUSE + "1x1 (9,9,0) round_tile white\n1x1 (9,9,5) round_plate lime\n", "not held by any stud")
        self.assertFails(HOUSE + "1x1 (3,0,9) round_plate lime\n", "line 10: not held")  # on a curved slope
        tile_tree = HOUSE.replace("1x1 (1,0,4) round_plate lime", "1x1 (1,0,4) round_tile white")
        self.assertFails(tile_tree + "1x1 (1,0,5) round_plate lime\n", "not held")

    def test_overlap_count_owned_grid(self):
        self.assertFails(HOUSE + "2x1 (3,0,2) plate dark_purple\n", "overlaps line 6")  # line 1 is blank
        c = self.assertFails(HOUSE + "2x1 (0,1,0) brick orange\n", "orange 1x2 brick: uses 3, owns 2")
        self.assertEqual(c.shortfall, {"orange 1x2 brick": 1})
        c = self.assertFails(HOUSE + "1x2 (0,1,0) plate red\n", "not in the inventory at all")
        self.assertEqual(c.shortfall, {"red 1x2 plate": 1})
        self.assertFails(HOUSE + "2x4 (0,1,0) brick orange\n", "you own no brick of size 2x4")
        self.assertFails(HOUSE + "1x2 (19,19,0) plate dark_purple\n", "off the 20x20 base")
        self.assertFails("2x1 (0,0,1) brick orange\n", "no piece stands on the table")
        self.assertFails(HOUSE + "4x1 (0,1,0) hinge_plate black\n", "unknown piece code 'hinge_plate'")
        self.assertFails("this is not a design\n", "can't read")

    def test_directions(self):
        self.assertFails(HOUSE.replace("down=-x", "down=+y"), "must be ±x")
        self.assertFails(HOUSE.replace(" down=-x", ""), "needs 'down=")
        self.assertFails("1x2 (0,0,0) plate dark_purple down=+y\n", "takes no 'down='")

    def test_jumper_plate_holds_nothing(self):
        text = "6x1 (0,0,0) plate lime\n2x1 (0,0,1) jumper_plate white\n1x1 (0,0,2) round_plate lime\n"
        self.assertFails(text, "nothing may go on a jumper plate")

    def test_azure_curved_slope_has_one_stud_at_the_low_end(self):
        base = "1x2 (0,0,0) curved_slope medium_azure down=+y\n"
        self.assertTrue(check(base + "1x1 (0,1,3) round_plate lime\n").ok)          # on the stud
        self.assertFails(base + "1x1 (0,0,4) round_plate lime\n", "not held")         # on the curve
        self.assertFails(base + "1x1 (0,0,3) round_plate lime\n", "overlaps line 1")  # inside the curve

    def test_wedge_plate_studs_on_one_long_edge(self):
        base = "2x4 (0,0,0) wedge_plate white studs=+x\n"
        self.assertTrue(check(base + "1x1 (1,3,1) round_plate lime\n").ok)
        self.assertFails(base + "1x1 (0,3,1) round_plate lime\n", "not held")
        self.assertFails("2x4 (0,0,0) wedge_plate white studs=+y\n", "must be ±x")
        # only the studded half grips the studs below
        under = "1x2 (0,0,0) plate dark_purple\n"
        self.assertFails(under + "2x4 (0,0,1) wedge_plate white studs=+x\n", "not held")
        self.assertTrue(check(under + "2x4 (0,0,1) wedge_plate white studs=-x\n").ok)

    def test_edge_stud_tile(self):
        base = "2x2 (0,0,0) edge_stud_tile white studs=-y\n"
        self.assertTrue(check(base + "1x1 (1,0,1) round_plate lime\n").ok)
        self.assertFails(base + "1x1 (1,1,1) round_plate lime\n", "not held")

    def test_clip_takes_up_the_next_cell(self):
        base = "4x1 (0,0,0) side_stud_brick blue\n2x1 (0,0,3) clip_plate lime clip=+x\n"
        self.assertTrue(check(base).ok)
        self.assertFails(base + "1x1 (2,0,3) round_plate lime\n", "overlaps line 2")


class Scripted:
    """Wonder replaced by written replies; keeps what it was sent."""

    def __init__(self, texts):
        self.texts, self.sent = list(texts), []

    def respond(self, text, instructions=None, previous_id=None):
        self.sent.append({"text": text, "instructions": instructions, "previous_id": previous_id})
        n = len(self.sent)
        return wc.WonderReply(f"r{n}", self.texts[n - 1], "completed",
                              {"input_tokens": 1000, "output_tokens": 500}, 1.0)


def reply(design, title="Test"):
    return f"Title: {title}\n```design\n{design.strip()}\n```"


class TestLoop(unittest.TestCase):
    def test_errors_go_back_and_a_fix_passes(self):
        broken = HOUSE + "1x1 (9,9,0) round_tile white\n1x1 (9,9,5) round_plate lime\n"
        wonder = Scripted([reply(broken), reply(HOUSE, "Little house")])
        result = wdr.design(wonder, OWNED, log=lambda *_: None)
        self.assertTrue(result.ok)
        self.assertEqual((result.title, len(result.attempts)), ("Little house", 2))
        first, second = wonder.sent
        self.assertIn("orange 1x2 ×2", first["instructions"])
        self.assertIn("a simple house", first["text"])
        self.assertEqual((second["instructions"], second["previous_id"]), (None, "r1"))
        self.assertIn("not held by any stud", second["text"])
        self.assertEqual(result.usd, round(2 * (1000 * 4 + 500 * 20) / 1e6, 4))

    def test_five_failures_name_the_shortfall(self):
        greedy = HOUSE + "2x1 (0,1,0) brick orange\n"
        wonder = Scripted([reply(greedy)] * 5)
        result = wdr.design(wonder, OWNED, log=lambda *_: None)
        self.assertFalse(result.ok)
        self.assertEqual(len(result.attempts), 5)
        self.assertEqual(result.shortfall, {"orange 1x2 brick": 1})
        self.assertIn("short of 1× orange 1x2 brick", result.reason)

    def test_reply_without_a_fence(self):
        title, body = wdr.extract("Title: Hut\n2x1 (0,0,0) brick orange\nsome words\n")
        self.assertEqual((title, body), ("Hut", "2x1 (0,0,0) brick orange"))

    def test_prompt_lists_only_owned_pieces(self):
        text = wdr.instructions(OWNED)
        self.assertNotIn("hinge", text)
        self.assertEqual(text.count("\n- "), 20 + 3)   # 20 kinds, then 3 format notes
        self.assertIn("curved_slope medium_azure 1x2 ×2", text)

    def test_recorded_live_runs_replay_to_valid_designs(self):
        for path in (RECORDED, RECORDED.with_name("wonder-house-run1-recorded.json")):
            recorded = json.loads(path.read_text())
            result = wdr.design(wdr.ReplayWonder(recorded), OWNED, recorded["target"], log=lambda *_: None)
            self.assertTrue(result.ok, (path.name, result.attempts[-1].errors))
            self.assertEqual(result.design.strip(), recorded["valid_design"].strip())
            self.assertEqual(len(result.attempts), 1)

    def test_the_candidate_design_file(self):
        text = (Path(wd.__file__).parent / "designs" / "wonder-simple-house.txt").read_text()
        c = check(text)
        self.assertTrue(c.ok, c.errors)
        self.assertEqual(c.parts, 20)
        kinds = {p.code for p in c.pieces}
        self.assertTrue({"jumper_plate", "headlight_brick", "side_stud_brick", "round_tile"} <= kinds)
        plain = sum(1 for p in c.pieces if p.code == "brick")
        self.assertEqual(plain, 2)  # the kit's only 2 plain bricks; the other 18 pieces are beyond BrickGPT


class TestBooklet(unittest.TestCase):
    def test_layers_and_heights(self):
        text = ("4x2 (0,0,0) plate medium_azure\n1x2 (0,0,1) curved_slope medium_azure down=+y\n"
                "1x1 (0,1,4) tall_side_stud_brick lime\n")  # the tall brick on the curved slope's low-end stud
        c = check(text)
        self.assertTrue(c.ok, c.errors)
        book = wdr.make_booklet("Test", c.pieces, "a test")
        self.assertEqual(len(book["steps"]), len({p.z for p in c.pieces}))
        dims = {pl["part"]["shape"] + pl["part"]["color"]: pl["dims"][2] for pl in book["placements"]}
        self.assertEqual(dims["curved slopemedium_azure"], 4)
        self.assertEqual(dims["tall 1x1 brick with 2 studs on sidelime"], 5)


class TestClient(unittest.TestCase):
    def test_no_key_is_a_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(wc.WonderError) as caught:
                wc.load_api_key(Path(tmp) / ".env")
        self.assertIn("META_MODEL_API_KEY", str(caught.exception))

    def test_request_polling_and_key_scrubbing(self):
        sent = []

        class Body(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        states = iter([{"id": "resp_1", "status": "queued"}, {"id": "resp_1", "status": "in_progress"},
                       {"id": "resp_1", "status": "completed", "usage": {"input_tokens": 10, "output_tokens": 20},
                        "output": [{"type": "message", "content": [{"type": "output_text", "text": "Title: X"}]}]}])

        def urlopen(request, timeout):
            sent.append((request.get_method(), request.full_url, request.get_header("Authorization"),
                         json.loads(request.data) if request.data else None))
            return Body(json.dumps(next(states)).encode())

        client = wc.WonderClient("secret-key", poll=0)
        with mock.patch("urllib.request.urlopen", urlopen):
            r = client.respond("design a hut", instructions="rules", previous_id="resp_0")
        method, url, auth, body = sent[0]
        self.assertEqual((method, url, auth), ("POST", "https://api.meta.ai/v1/responses", "Bearer secret-key"))
        self.assertEqual(body["model"], "muse-wonder-1.0")
        self.assertEqual(body["reasoning"], {"effort": "high"})
        self.assertEqual((body["background"], body["previous_response_id"], body["instructions"]),
                         (True, "resp_0", "rules"))
        self.assertEqual([s[:2] for s in sent[1:]], [("GET", "https://api.meta.ai/v1/responses/resp_1")] * 2)
        self.assertEqual((r.text, r.usd), ("Title: X", round((10 * 4 + 20 * 20) / 1e6, 4)))

        def refuse(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 401, "no", {}, io.BytesIO(b"bad key secret-key"))
        with mock.patch("urllib.request.urlopen", refuse):
            with self.assertRaises(wc.WonderError) as caught:
                wc.WonderClient("secret-key", retries=0).respond("x")
        self.assertNotIn("secret-key", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
