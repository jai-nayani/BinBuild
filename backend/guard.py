"""Guards for the public deploy: a shared key on the routes that spend
credits, and a per-IP rate limit on every write.

Off unless BINBUILD_ACCESS_KEY is set. The public deploy sets it from a Modal
secret (deploy/modal_app.py); on the home network nothing changes. With it set:

- paid routes, the ones that call a paid API (classify: Muse Spark on
  Baseten, plus SAM 3.1 on the Meta Model API; Wonder generate: the Meta
  Model API), answer 401 unless the request carries the key in the
  X-BinBuild-Key header, and allow PAID calls per client IP per window;
- every other POST (upload, retake, review, confirm, undo, plan or check a
  build) needs no key but allows WRITE calls per client IP per window;
- GET routes (health, the build list, the catalog, booklets) stay open.

The rate limit is counted before the key is checked, so guessing keys is
limited too. Counts are kept in memory: the deploy runs one container.
Standard library only (plus FastAPI, which the backend already uses).
"""

import os
import secrets
import threading
import time
from collections import deque

from fastapi import HTTPException, Request

ACCESS_KEY_ENV = "BINBUILD_ACCESS_KEY"
HEADER = "X-BinBuild-Key"


def public() -> bool:
    """Running as the public deploy (the shared key is configured)."""
    return bool(os.environ.get(ACCESS_KEY_ENV, "").strip())


def client_ip(request: Request) -> str:
    """The caller's address. Behind the deploy's proxy that is the last
    X-Forwarded-For entry (the one the proxy added, not one the caller sent)."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded.strip():
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


class RateLimit:
    """At most `limit` calls per `window` seconds per client IP."""

    def __init__(self, name, limit, window):
        self.name, self.limit, self.window = name, limit, window
        self.calls = {}
        self.lock = threading.Lock()

    def hit(self, ip):
        now = time.monotonic()
        with self.lock:
            recent = self.calls.setdefault(ip, deque())
            while recent and recent[0] <= now - self.window:
                recent.popleft()
            if len(recent) >= self.limit:
                wait = int(recent[0] + self.window - now) + 1
                raise HTTPException(429, f"too many {self.name} requests from your address; try again in {wait} s",
                                    headers={"Retry-After": str(wait)})
            recent.append(now)


PAID = RateLimit("paid", 20, 3600)      # classify and generate: 20 an hour per IP
WRITE = RateLimit("write", 60, 600)     # every other POST: 60 every 10 minutes per IP


def paid(request: Request):
    """Dependency for routes that spend credits: rate limit, then the key."""
    if not public():
        return
    PAID.hit(client_ip(request))
    sent = request.headers.get(HEADER, "")
    if not secrets.compare_digest(sent.encode(), os.environ[ACCESS_KEY_ENV].strip().encode()):
        raise HTTPException(401, f"this calls a paid API, so on the public demo it needs the access key "
                                 f"(header {HEADER}); browsing builds and booklets needs none")


def write(request: Request):
    """Dependency for every other POST: rate limit only."""
    if public():
        WRITE.hit(client_ip(request))
