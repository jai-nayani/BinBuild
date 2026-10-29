"""Segmenter: finds the regions of a photo that the classifier should look at.

Given an upright photo, return regions (a box, and with SAM a mask). The stub
returns the whole photo as one region and the classifier does all the
counting. SamSegmenter (SAM 3.1 through the Meta Model API) returns one
region per piece, prompted with a point on each piece: Spark's centre points
from the whole-photo pass.

Only the top view is segmented and counted. The four side views go to the
classifier as context for height and shape, never as extra pieces.
"""

import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from io import BytesIO
from typing import Protocol

COUNT_VIEW = "top"


@dataclass(frozen=True)
class Region:
    bbox: tuple                 # (x0, y0, x1, y1) in the upright photo's pixels
    whole_photo: bool = False
    score: float = None         # segmenter confidence, when it has one
    mask: object = field(default=None, compare=False)  # PieceMask from SAM
    point: tuple = None         # the point prompt (x, y) this region came from, if any


@dataclass(frozen=True)
class PieceMask:
    """SAM's mask for one piece. sam: the SamMask, in the frame SAM was sent;
    scale: (sx, sy) from the upright photo to that frame."""

    sam: object = field(repr=False)
    scale: tuple


class Segmenter(Protocol):
    name: str

    def segment(self, image) -> list:
        """Regions for an upright photo (a PIL image)."""


class WholePhotoSegmenter:
    """Stub: one region covering the whole photo."""

    name = "stub-whole-photo"

    def segment(self, image):
        width, height = image.size
        return [Region((0, 0, width, height), whole_photo=True)]


class FixedRegionSegmenter:
    """Regions chosen by hand, e.g. a crop of about 15 pieces for a test run."""

    name = "fixed-regions"

    def __init__(self, boxes):
        self.boxes = [tuple(int(v) for v in box) for box in boxes]

    def segment(self, image):
        width, height = image.size
        regions = []
        for x0, y0, x1, y1 in self.boxes:
            box = (max(0, x0), max(0, y0), min(width, x1), min(height, y1))
            if box[2] <= box[0] or box[3] <= box[1]:
                raise ValueError(f"region {box} is outside the {width}x{height} photo")
            regions.append(Region(box))
        return regions


class SamSegmenter:
    """SAM 3.1: one region per point prompt, with SAM's box and mask for the
    piece under that point. A point SAM finds nothing at still gets a region
    (a small box round the point, no mask, score 0), so nothing silently
    disappears from the count. The photo goes to SAM scaled to max_side;
    boxes come back in the upright photo's pixels."""

    name = "sam-3.1-points"
    per_piece = True

    def __init__(self, client, points, max_side=2048):
        self.client = client
        self.points = [(float(x), float(y)) for x, y in points]
        self.max_side = max_side
        self.calls = []  # one entry per Model API request, for the run report

    def segment(self, image):
        from .sam_client import MAX_OBJECTS
        width, height = image.size
        scale = min(1.0, self.max_side / max(width, height))
        sent = image if scale == 1 else image.resize((round(width * scale), round(height * scale)))
        sx, sy = sent.size[0] / width, sent.size[1] / height
        out = BytesIO()
        sent.convert("RGB").save(out, "JPEG", quality=90)
        jpeg = out.getvalue()
        chunks = [[(i, min(sent.size[0] - 1, int(x * sx)), min(sent.size[1] - 1, int(y * sy)))
                   for i, (x, y) in enumerate(self.points[start:start + MAX_OBJECTS], start)]
                  for start in range(0, len(self.points), MAX_OBJECTS)]
        found = {}
        if chunks:  # at most 16 points per request; the requests are independent, so they go at once
            with ThreadPoolExecutor(max_workers=len(chunks)) as pool:
                replies = list(pool.map(lambda chunk: self.client.segment_points(jpeg, sent.size, chunk), chunks))
            for chunk, reply in zip(chunks, replies):
                found.update(reply.masks)
                self.calls.append({"points": chunk, "size": sent.size, "masks": len(reply.masks),
                                   "seconds": reply.seconds, "usage": reply.usage,
                                   "diagnostics": reply.diagnostics, "raw_output": reply.raw_output})
        regions = []
        for i, (x, y) in enumerate(self.points):
            m = found.get(i)
            if m is None:
                r = 12
                box = (max(0, int(x) - r), max(0, int(y) - r), min(width, int(x) + r), min(height, int(y) + r))
                regions.append(Region(box, score=0.0, point=(x, y)))
                continue
            x0, y0, x1, y1 = m.box
            box = (max(0, math.floor(x0 / sx)), max(0, math.floor(y0 / sy)),
                   min(width, math.ceil(x1 / sx)), min(height, math.ceil(y1 / sy)))
            regions.append(Region(box, score=m.confidence, mask=PieceMask(m, (sx, sy)), point=(x, y)))
        return regions
