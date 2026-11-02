"""SAM 3.1 client, through the Meta Model API.

As documented at dev.meta.ai/docs/sam (Oct 2026):
- model "sam-3.1", POST https://api.meta.ai/v1/responses (the Responses API),
  Authorization: Bearer <key>;
- point prompts are text tokens (<0f>1<|point;x=..;y=..;w=..;h=..|>,2...), in
  pixels of the image as sent, at most 16 prompted objects per request;
- the reply is one box and one box-local mask per object, under the id the
  prompt gave it. Masks are base85 with a range-coded payload, so they are
  decoded with Meta's own parser (meta-sam-parser), never by hand;
- billing: $2.50 per 1,000 images (dev.meta.ai/docs/pricing-rate-limits).

The key is META_MODEL_API_KEY (or the docs' MODEL_API_KEY) from the
environment, else from the git-ignored .env. It is held in memory only: never
printed, logged, put in an error message or written anywhere.
"""

import base64
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from .spark_client import ENV_FILE, RETRY_STATUS, env_value

BASE_URL = "https://api.meta.ai/v1"
MODEL = "sam-3.1"
KEY_NAMES = ("META_MODEL_API_KEY", "MODEL_API_KEY")
MAX_OBJECTS = 16  # prompted objects per request (dev.meta.ai/docs/sam/segmenting)
USD_PER_IMAGE = 2.50 / 1000


class SamError(RuntimeError):
    pass


def load_api_key(env_file=ENV_FILE) -> str:
    for name in KEY_NAMES:
        value = env_value(name, env_file)
        if value:
            return value
    raise SamError(f"no Meta Model API key: put {KEY_NAMES[0]}=<key> in .env on this Mac")


@dataclass(frozen=True)
class SamMask:
    """One object's mask, local to its box. box is half-open (x0, y0, x1, y1)
    in pixels of the image SAM was sent; raster is row-major 0/1 bytes of
    width x height."""

    box: tuple
    width: int
    height: int
    raster: bytes = field(repr=False)
    confidence: float = None
    encoded: object = field(default=None, repr=False, compare=False)  # the parser's SegmentationMask

    @property
    def area(self) -> int:
        return sum(self.raster)


@dataclass
class SamReply:
    masks: dict          # object id (int) -> SamMask; a prompted object SAM found nothing for is absent
    seconds: float
    usage: dict
    raw_output: str
    diagnostics: list


def parse_output(text: str) -> tuple:
    """SAM's output text -> ({object id: SamMask}, diagnostics)."""
    # Imported here so the backend runs without SAM's parser when SAM is off.
    from meta_sam_parser import CompletedOutcome, decode_mask_to_raster, image_segmentation_format
    parser = image_segmentation_format().create_parser()
    parser.push(text if text.endswith("\n") else text + "\n")
    result = parser.finish(CompletedOutcome()).result
    boxes = {r.object_id: r for r in result.records if r.kind == "box"}
    masks = {}
    for record in result.records:
        if record.kind != "mask":
            continue
        b = record.bounds
        confidence = record.confidence if record.confidence is not None else getattr(
            boxes.get(record.object_id), "confidence", None)
        masks[int(record.object_id)] = SamMask(
            (int(b.left), int(b.top), int(b.right), int(b.bottom)), record.mask.width, record.mask.height,
            decode_mask_to_raster(record.mask), confidence, record.mask)
    diagnostics = [f"{d.severity} {d.code}: {d.message}" for d in result.diagnostics]
    return masks, diagnostics


def output_text(data: dict) -> str:
    """The text of a non-streaming Responses API reply."""
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    parts = []
    for item in data.get("output") or ():
        for content in (item.get("content") or ()) if isinstance(item, dict) else ():
            if isinstance(content, dict) and content.get("type") == "output_text":
                parts.append(content.get("text") or "")
    return "".join(parts)


class SamClient:
    def __init__(self, api_key, base_url=BASE_URL, model=MODEL, timeout=180, retries=2):
        self._api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.retries = retries
        self.requests = 0  # billed images, for the run report

    @classmethod
    def from_env(cls, env_file=ENV_FILE, **kwargs):
        return cls(load_api_key(env_file), **kwargs)

    def __repr__(self):
        return f"SamClient(model={self.model!r}, base_url={self.base_url!r})"

    def _scrub(self, text: str) -> str:
        return text.replace(self._api_key, "[key]") if self._api_key else text

    def _post(self, body: dict) -> dict:
        data = json.dumps(body).encode()
        for attempt in range(self.retries + 1):
            request = urllib.request.Request(
                f"{self.base_url}/responses", data=data, method="POST",
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
            )
            try:
                self.requests += 1
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.load(response)
            except urllib.error.HTTPError as err:
                detail = self._scrub(err.read(500).decode("utf-8", "replace"))
                err.close()
                if err.code in RETRY_STATUS and attempt < self.retries:
                    time.sleep(3 * 2 ** attempt)
                    continue
                raise SamError(f"HTTP {err.code} from the Meta Model API: {detail}") from None
            except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
                if attempt < self.retries:
                    time.sleep(3 * 2 ** attempt)
                    continue
                reason = getattr(err, "reason", err)
                raise SamError(f"could not reach the Meta Model API: {self._scrub(str(reason))}") from None

    def segment_points(self, image_jpeg: bytes, size: tuple, points) -> SamReply:
        """One mask per point. points: (object id, x, y) in pixels of the
        image as sent, whose (width, height) is size; at most MAX_OBJECTS."""
        from meta_sam_parser import FramePrompt, PromptObject, PromptPoint, build_object_prompt
        points = list(points)
        if not 0 < len(points) <= MAX_OBJECTS:
            raise ValueError(f"1 to {MAX_OBJECTS} points per request, got {len(points)}")
        prompt = build_object_prompt(size=tuple(size), objects=[
            PromptObject(id=int(i), prompts=[FramePrompt(points=[PromptPoint(int(x), int(y))])]) for i, x, y in points])
        body = {
            "model": self.model,
            "input": [{"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image",
                 "image_url": "data:image/jpeg;base64," + base64.b64encode(image_jpeg).decode("ascii")},
            ]}],
            "metadata": {"include_confidence": "true"},
        }
        started = time.monotonic()
        data = self._post(body)
        text = output_text(data)
        try:
            masks, diagnostics = parse_output(text)
        except Exception as err:  # a reply the official parser can't read
            raise SamError(f"unreadable SAM output ({type(err).__name__}: {err})") from None
        return SamReply(masks, round(time.monotonic() - started, 1), data.get("usage") or {}, text, diagnostics)


_PATH_TOKEN = re.compile(r"[MLZ]|-?\d+(?:\.\d+)?")


def simplify_path(d: str) -> str:
    """Drop the points of a traced outline that lie on a straight line between
    their neighbours (the tracer emits one point per pixel edge)."""
    out, points = [], []

    def flush(closed):
        keep = [p for i, p in enumerate(points)
                if i in (0, len(points) - 1)
                or (points[i - 1][0] - p[0]) * (points[i + 1][1] - p[1])
                != (points[i - 1][1] - p[1]) * (points[i + 1][0] - p[0])]
        if keep:
            out.append("M" + "L".join(f"{x:g} {y:g}" for x, y in keep) + ("Z" if closed else ""))
        points.clear()

    tokens = _PATH_TOKEN.findall(d)
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t == "M":
            if points:
                flush(False)
            points.append((float(tokens[i + 1]), float(tokens[i + 2])))
            i += 3
        elif t == "L":
            points.append((float(tokens[i + 1]), float(tokens[i + 2])))
            i += 3
        elif t == "Z":
            flush(True)
            i += 1
        else:  # implicit L after a coordinate pair
            points.append((float(t), float(tokens[i + 1])))
            i += 2
    if points:
        flush(False)
    return "".join(out)


def outline(mask: SamMask) -> str:
    """The mask's outline as an SVG path, in the mask's own pixels (Meta's
    tracer, with straight runs collapsed)."""
    from meta_sam_parser import decode_mask_to_svg_path
    return simplify_path(decode_mask_to_svg_path(mask.encoded)) if mask.encoded is not None else ""
