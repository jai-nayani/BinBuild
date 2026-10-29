"""Wonder in the app: "Generate a new design" in What can I build?

- flag off (the default): the build list is exactly as before, and the
  generate endpoint refuses without touching Wonder;
- flag on: the recorded live run gives a validated design with its parts
  list, placements and booklet, stored as a build with the inventory and
  batches it came from; a fix on the second try passes; five failing tries
  give a named shortfall and nothing that looks like a design; no key, an
  empty inventory and a second tap while one runs are refused; reading the
  build list never calls Wonder.

No Model API call: Wonder is replaced by recorded or written replies.
Standard-library unittest. Run from the repo root:
    python3 -m unittest discover -s tests -v
"""

import json
import os
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from backend import inventory_db as db

try:
    import uvicorn  # noqa: F401
    from backend import full_loop, main, wonder_designer
    from backend.wonder_client import WonderError
    from test_full_loop import KIT_ITEMS, seed
    from test_wonder import HOUSE, Scripted, reply
    HAVE_SERVER = True
except ImportError:
    HAVE_SERVER = False

RECORDED = Path(__file__).resolve().parent / "fixtures" / "wonder-house-recorded.json"
FLAG_ON = {"BINBUILD_WONDER": "1"}


@unittest.skipUnless(HAVE_SERVER, "FastAPI, uvicorn or Pillow not installed")
class TestWonderInTheApp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ctx = full_loop.server(self.tmp.name, None)
        self.api = self.ctx.__enter__()
        with closing(db.connect()) as conn:
            self.batch = seed(conn, KIT_ITEMS)
        env = {k: v for k, v in os.environ.items() if k != "BINBUILD_WONDER"}
        self.env = mock.patch.dict(os.environ, env, clear=True)
        self.env.start()
        self.wonder = None
        self.from_env = mock.patch.object(main.WonderClient, "from_env", side_effect=self._client)
        self.from_env.start()
        self.calls = 0

    def tearDown(self):
        self.from_env.stop()
        self.env.stop()
        self.ctx.__exit__(None, None, None)
        self.tmp.cleanup()

    def _client(self):
        self.calls += 1
        if self.wonder is None:
            raise AssertionError("Wonder was called")
        return self.wonder

    def generate(self, target="a simple house"):
        return self.api.call("POST", "/api/builds/wonder", json_body={"target": target})

    def test_flag_off_is_exactly_as_before(self):
        status, body = self.api.call("GET", "/api/builds/options")
        self.assertEqual(status, 200)
        self.assertEqual(set(body), {"inventory", "manual", "options"})
        self.assertEqual([o["kind"] for o in body["options"]], ["manual"] * 106 + ["brickgpt"] * 10)
        status, body = self.generate()
        self.assertEqual(status, 404)
        self.assertIn("BINBUILD_WONDER=1", body["detail"])
        self.assertEqual(self.calls, 0)

    def test_options_with_the_flag_on_add_a_section_and_call_nothing(self):
        with mock.patch.dict(os.environ, FLAG_ON):
            status, body = self.api.call("GET", "/api/builds/options")
        self.assertEqual(status, 200)
        self.assertEqual([o["kind"] for o in body["options"]], ["manual"] * 106 + ["brickgpt"] * 10)
        self.assertEqual(body["options"][0]["id"], "house-and-tree")
        w = body["wonder"]
        self.assertEqual((w["enabled"], w["max_tries"], w["busy"], w["recent"]), (True, 5, False, []))
        self.assertIn("a simple house", w["targets"])
        self.assertEqual(self.calls, 0)

    def test_recorded_run_gives_a_validated_design_with_a_booklet(self):
        self.wonder = wonder_designer.ReplayWonder(json.loads(RECORDED.read_text()))
        with mock.patch.dict(os.environ, FLAG_ON):
            status, build = self.generate()
            self.assertEqual(status, 201, build)
            self.assertEqual((build["kind"], build["status"], build["title"]), ("wonder", "fit", "Simple House"))
            self.assertEqual((build["pieces"], sum(p["qty"] for p in build["parts"]), len(build["placements"])),
                             (20, 20, 20))
            self.assertEqual(len(build["tries"]), 1)
            self.assertNotIn("booklet", build)
            status, page = self.api.call("GET", build["booklet_url"], raw=True)
            self.assertEqual(status, 200)
            self.assertIn("Simple House", page)
            status, stored = self.api.call("GET", f"/api/builds/{build['build_id']}")
            self.assertEqual(stored["request"], {"wonder": True, "target": "a simple house"})
            self.assertEqual(stored["inventory_snapshot"]["batches"], [self.batch])
            self.assertEqual(stored["inventory_snapshot"]["total_pieces"], 50)
            status, body = self.api.call("GET", "/api/builds/options")
            recent = body["wonder"]["recent"]
            self.assertEqual([(r["build_id"], r["title"], r["booklet_url"]) for r in recent],
                             [(build["build_id"], "Simple House", build["booklet_url"])])
        self.assertEqual((self.calls, self.wonder.requests), (1, 1))

    def test_a_fix_on_the_second_try_passes(self):
        broken = HOUSE + "1x1 (9,9,0) round_tile white\n1x1 (9,9,5) round_plate lime\n"
        self.wonder = Scripted([reply(broken), reply(HOUSE, "Little house")])
        with mock.patch.dict(os.environ, FLAG_ON):
            status, build = self.generate()
        self.assertEqual((status, build["status"], len(build["tries"])), (201, "fit", 2))
        self.assertEqual([t["errors"] for t in build["tries"]], [2, 0])  # two separate floating pieces, then none
        self.assertIn("Found on try 2 of 5", build["message"])
        self.assertIn("booklet_url", build)

    def test_five_failures_name_the_shortfall_and_show_no_design(self):
        greedy = HOUSE + "2x1 (0,1,0) brick orange\n"
        self.wonder = Scripted([reply(greedy)] * 5)
        with mock.patch.dict(os.environ, FLAG_ON):
            status, build = self.generate()
            self.assertEqual((status, build["status"]), (201, "short"))
            self.assertEqual(build["shortfall"], {"orange 1x2 brick": 1})
            self.assertEqual(build["message"], "No design fits your pieces after 5 tries. Short of 1× orange 1x2 brick.")
            for key in ("booklet_url", "parts", "placements", "design", "pieces"):
                self.assertNotIn(key, build)
            self.assertEqual(self.api.call("GET", f"/api/builds/{build['build_id']}/booklet")[0], 404)
        self.assertEqual(len(self.wonder.sent), 5)

    def test_failures_without_a_shortfall(self):
        floating = HOUSE + "1x1 (9,9,0) round_tile white\n1x1 (9,9,5) round_plate lime\n"
        self.wonder = Scripted([reply(floating)] * 5)
        with mock.patch.dict(os.environ, FLAG_ON):
            status, build = self.generate("a robot")
        self.assertEqual((status, build["status"]), (201, "failed"))
        self.assertIn("No design passed BinBuild's check in 5 tries", build["message"])
        self.assertTrue(any("not held" in p for p in build["problems"]))

    def test_refusals(self):
        with mock.patch.dict(os.environ, FLAG_ON):
            with mock.patch.object(main.WonderClient, "from_env", side_effect=WonderError("no Meta Model API key")):
                status, body = self.generate()
            self.assertEqual(status, 503)
            self.assertIn("not set up", body["detail"])
            self.assertEqual(self.generate("x")[0], 422)     # target too short
            main._wonder_busy.acquire()
            try:
                status, body = self.generate()
                self.assertEqual(status, 409)
            finally:
                main._wonder_busy.release()
            self.assertEqual(self.api.call("POST", f"/api/inventory/undo-last-batch?batch_id={self.batch}")[0], 200)
            status, body = self.generate()
            self.assertEqual(status, 422)
            self.assertIn("no confirmed pieces", body["detail"])
        self.assertEqual(self.calls, 0)

    def test_wonder_errors_are_reported(self):
        class Broken:
            def respond(self, *a, **k):
                raise WonderError("HTTP 500 from the Meta Model API: oops")
        self.wonder = Broken()
        with mock.patch.dict(os.environ, FLAG_ON):
            status, body = self.generate()
        self.assertEqual(status, 502)
        self.assertIn("Muse Wonder failed", body["detail"])
        self.assertFalse(main._wonder_busy.locked())


if __name__ == "__main__":
    unittest.main()
