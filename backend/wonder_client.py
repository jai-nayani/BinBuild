"""Muse Wonder client, through the Meta Model API.

As documented at dev.meta.ai (Oct 2026): model "muse-wonder-1.0" (Standard
mode, in preview), the Responses API at POST https://api.meta.ai/v1/responses
with Authorization: Bearer <key>, reasoning effort as reasoning.effort
("minimal" to "max"), reasoning tokens billed as output tokens. Price:
$4.00 per million input tokens, $0.20 cached, $20.00 output
(dev.meta.ai/docs/pricing-rate-limits).

Long reasoning runs in background mode: the request returns at once and the
response is fetched by id until it is done, so no connection has to stay
open for minutes. A retry continues the same conversation with
previous_response_id, so Wonder sees its own design and the validator's
errors.

The key is META_MODEL_API_KEY (or the docs' MODEL_API_KEY) from the
environment, else from the git-ignored .env: held in memory only, never
printed, logged, put in an error message or written anywhere. Standard
library only.
"""

import base64
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .sam_client import KEY_NAMES, output_text
from .spark_client import ENV_FILE, RETRY_STATUS, env_value

BASE_URL = "https://api.meta.ai/v1"
MODEL = "muse-wonder-1.0"
USD_PER_M = {"input": 4.00, "cached": 0.20, "output": 20.00}


class WonderError(RuntimeError):
    pass


def load_api_key(env_file=ENV_FILE) -> str:
    for name in KEY_NAMES:
        value = env_value(name, env_file)
        if value:
            return value
    raise WonderError(f"no Meta Model API key: put {KEY_NAMES[0]}=<key> in .env on this Mac")


def cost_usd(usage) -> float:
    cached = (usage.get("input_tokens_details") or {}).get("cached_tokens", 0)
    fresh = usage.get("input_tokens", 0) - cached
    return round((fresh * USD_PER_M["input"] + cached * USD_PER_M["cached"]
                  + usage.get("output_tokens", 0) * USD_PER_M["output"]) / 1e6, 4)


@dataclass
class WonderReply:
    id: str
    text: str
    status: str
    usage: dict
    seconds: float

    @property
    def usd(self) -> float:
        return cost_usd(self.usage)


class WonderClient:
    def __init__(self, api_key, base_url=BASE_URL, model=MODEL, effort="high", max_output_tokens=64000,
                 timeout=60, wait=1800, poll=5, retries=2):
        self._api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.effort = effort
        self.max_output_tokens = max_output_tokens
        self.timeout = timeout      # per HTTP request
        self.wait = wait            # longest wait for one response, seconds
        self.poll = poll
        self.retries = retries
        self.requests = 0

    @classmethod
    def from_env(cls, env_file=ENV_FILE, **kwargs):
        return cls(load_api_key(env_file), **kwargs)

    def __repr__(self):
        return f"WonderClient(model={self.model!r}, effort={self.effort!r})"

    def _scrub(self, text: str) -> str:
        return text.replace(self._api_key, "[key]") if self._api_key else text

    def _call(self, method, path, body=None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        for attempt in range(self.retries + 1):
            request = urllib.request.Request(
                f"{self.base_url}{path}", data=data, method=method,
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.load(response)
            except urllib.error.HTTPError as err:
                detail = self._scrub(err.read(800).decode("utf-8", "replace"))
                err.close()
                if err.code in RETRY_STATUS and attempt < self.retries:
                    time.sleep(3 * 2 ** attempt)
                    continue
                raise WonderError(f"HTTP {err.code} from the Meta Model API: {detail}") from None
            except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
                if attempt < self.retries:
                    time.sleep(3 * 2 ** attempt)
                    continue
                reason = getattr(err, "reason", err)
                raise WonderError(f"could not reach the Meta Model API: {self._scrub(str(reason))}") from None

    def respond(self, text, instructions=None, previous_id=None, images=()) -> WonderReply:
        """One turn: the user text (plus instructions on the first turn).
        Continues previous_id's conversation when given. images: JPEG bytes
        sent with the text (as input_image parts); text alone otherwise."""
        content = text
        if images:
            content = [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}] + [
                {"type": "input_image",
                 "image_url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")}
                for jpeg in images]}]
        body = {"model": self.model, "input": content, "reasoning": {"effort": self.effort},
                "max_output_tokens": self.max_output_tokens, "background": True, "store": True}
        if instructions:
            body["instructions"] = instructions
        if previous_id:
            body["previous_response_id"] = previous_id
        started = time.monotonic()
        self.requests += 1
        data = self._call("POST", "/responses", body)
        while data.get("status") in ("queued", "in_progress"):
            if time.monotonic() - started > self.wait:
                raise WonderError(f"no answer after {self.wait} s (response {data.get('id')} still {data.get('status')})")
            time.sleep(self.poll)
            data = self._call("GET", f"/responses/{data['id']}")
        status = data.get("status") or "completed"
        if status in ("failed", "cancelled"):
            error = data.get("error") or {}
            raise WonderError(f"Wonder {status}: {self._scrub(str(error.get('message') or error))[:400]}")
        return WonderReply(data.get("id", ""), output_text(data), status, data.get("usage") or {},
                           round(time.monotonic() - started, 1))
