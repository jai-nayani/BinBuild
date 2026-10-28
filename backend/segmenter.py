"""Segmenter: finds the regions of a photo that the classifier should look at.

The interface is what SAM 3.1 will implement: given an upright photo, return
regions (a box, later also a mask). Until SAM access is settled the stub
returns the whole photo as one region, so classify -> review -> confirm ->
inventory runs end to end now and the classifier does all the counting.

Only the top view is segmented and counted. The four side views go to the
classifier as context for height and shape, never as extra pieces.
"""

from dataclasses import dataclass, field
from typing import Protocol

COUNT_VIEW = "top"


@dataclass(frozen=True)
class Region:
    bbox: tuple                 # (x0, y0, x1, y1) in the upright photo's pixels
    whole_photo: bool = False
    score: float = None         # segmenter confidence, when it has one
    mask: object = field(default=None, compare=False)  # reserved for SAM masks


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
