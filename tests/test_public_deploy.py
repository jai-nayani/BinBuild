"""The public deploy (deploy/modal_app.py): one URL, the paid routes guarded,
an empty bin at the start (visitors scan, or use the sample images:
tests/test_sample_bin.py).

- guard (backend/guard.py), with BINBUILD_ACCESS_KEY set as on the deploy:
  classify and Wonder generate answer 401 without the key or with a wrong
  one, and get past the guard with it (an unknown batch is then a 404, before
  any paid call); past the per-IP limit a route answers 429; every POST
  carries a guard and only those two are paid; GET routes stay open; with no
  key configured (the home network) nothing changes;
- one URL: with BINBUILD_APP_DIR the backend serves the PWA at "/" beside
  the API, with Cache-Control: no-cache so a redeploy reaches every browser.

No Model API call; every database is a temporary one. Standard-library
unittest. Run from the repo root:
    python3 -m unittest discover -s tests -v
"""

import os
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from backend import guard

try:
    import uvicorn  # noqa: F401
    from fastapi.routing import APIRoute
    from backend import full_loop, main
    HAVE_SERVER = True
except ImportError:
    HAVE_SERVER = False

REPO = Path(__file__).resolve().parent.parent
KEY = "test-key-not-a-secret"
PUBLIC = {guard.ACCESS_KEY_ENV: KEY}
CLASSIFY = "/api/inventory/batch/20261102-000000-aaaaaa/classify"


@unittest.skipUnless(HAVE_SERVER, "FastAPI or uvicorn not installed")
class TestGuard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ctx = full_loop.server(self.tmp.name, None)
        self.api = self.ctx.__enter__()
        self.limits = [mock.patch.object(guard, "PAID", guard.RateLimit("paid", 20, 3600)),
                       mock.patch.object(guard, "WRITE", guard.RateLimit("write", 60, 600))]
        for p in self.limits:
            p.start()

    def tearDown(self):
        for p in self.limits:
            p.stop()
        self.ctx.__exit__(None, None, None)
        self.tmp.cleanup()

    def post(self, path, key=None, body=None):
        return self.api.call("POST", path, json_body=body, headers={guard.HEADER: key} if key else None)

    def test_paid_routes_need_the_key(self):
        with mock.patch.dict(os.environ, PUBLIC):
            for path in (CLASSIFY, "/api/builds/wonder"):
                body = {"target": "a simple house"} if path.endswith("wonder") else None
                self.assertEqual(self.post(path, body=body)[0], 401, path)
                self.assertEqual(self.post(path, key="wrong", body=body)[0], 401, path)
            status, reply = self.post(CLASSIFY, key=KEY)
            self.assertEqual(status, 404, reply)            # past the guard; no such batch, so no paid call
            self.assertEqual(self.post("/api/builds/wonder", key=KEY, body={"target": "a simple house"})[0], 404)
            self.assertIn(guard.HEADER, self.post(CLASSIFY)[1]["detail"])

    def test_reading_stays_open(self):
        with mock.patch.dict(os.environ, PUBLIC):
            for path in ("/health", "/api/builds/options", "/api/manual", "/api/inventory/summary"):
                self.assertEqual(self.api.call("GET", path)[0], 200, path)
            status, body = self.post("/api/builds/check", body={"set": "house-and-tree"})
            self.assertEqual(status, 200, body)

    def test_per_ip_limits(self):
        with mock.patch.dict(os.environ, PUBLIC), \
                mock.patch.object(guard, "PAID", guard.RateLimit("paid", 2, 3600)), \
                mock.patch.object(guard, "WRITE", guard.RateLimit("write", 3, 600)):
            self.assertEqual([self.post(CLASSIFY)[0] for _ in range(3)], [401, 401, 429])  # counted before the key
            status, body = self.post(CLASSIFY, key=KEY)
            self.assertEqual(status, 429)
            self.assertIn("try again in", body["detail"])
            check = [self.post("/api/builds/check", body={"set": "house-and-tree"})[0] for _ in range(4)]
            self.assertEqual(check, [200, 200, 200, 429])

    def test_off_the_public_deploy_nothing_changes(self):
        env = {k: v for k, v in os.environ.items() if k != guard.ACCESS_KEY_ENV}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(self.post(CLASSIFY)[0], 404)   # no key asked for at home

    def test_every_post_is_guarded_and_only_the_paid_ones_are_paid(self):
        paid, unguarded = set(), []
        for route in main.app.routes:
            if isinstance(route, APIRoute) and "POST" in route.methods:
                calls = {d.call for d in route.dependant.dependencies}
                if guard.paid in calls:
                    paid.add(route.path)
                elif guard.write not in calls:
                    unguarded.append(route.path)
        self.assertEqual(unguarded, [])
        self.assertEqual(paid, {"/api/inventory/batch/{batch_id}/classify", "/api/builds/wonder",
                                "/api/builds/wonder/ideas",
                                "/api/inventory/batch/{batch_id}/pieces/{detection_id}/reclassify"})


@unittest.skipUnless(HAVE_SERVER, "FastAPI or uvicorn not installed")
class TestOneUrl(unittest.TestCase):
    def test_the_pwa_and_the_api_share_an_origin(self):
        with mock.patch.dict(os.environ, {"BINBUILD_APP_DIR": str(REPO / "app")}):
            public_app = main.create_app()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(main, "app", public_app), \
                full_loop.server(tmp, None) as api:
            status, page = api.call("GET", "/", raw=True)
            self.assertEqual(status, 200)
            self.assertIn("<title>BinBuild</title>", page)
            self.assertEqual(api.call("GET", "/app.js", raw=True)[0], 200)
            self.assertEqual(api.call("GET", "/health"), (200, {"status": "ok", "service": "binbuild",
                                                                "version": "0.1.0"}))
            self.assertEqual(api.call("GET", "/api/builds/options")[0], 200)
            for path in ("/", "/app.js", "/style.css", "/sw.js"):   # no stale page after a redeploy
                with urllib.request.urlopen(api.base + path) as reply:
                    self.assertEqual(reply.headers["cache-control"], "no-cache", path)

    def test_at_home_the_root_is_still_the_api(self):
        with tempfile.TemporaryDirectory() as tmp, full_loop.server(tmp, None) as api:
            self.assertEqual(api.call("GET", "/")[1]["service"], "binbuild")


if __name__ == "__main__":
    unittest.main()
