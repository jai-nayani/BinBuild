"""Classify one batch: segment the top view, ask Spark what is in each region,
and store the answers as proposed detections for review.

Photos are turned upright (phone JPEGs carry an EXIF rotation the model
ignores), cropped to the region and downscaled before they are sent.
"""

from io import BytesIO

from PIL import Image, ImageOps

from . import inventory_db as db
from . import inventory_vocab as vocab
from .segmenter import COUNT_VIEW
from .spark_client import SparkError

SIDE_VIEWS = ("front", "right", "back", "left")
REGION_MAX_SIDE = 2048   # the counted region
CONTEXT_MAX_SIDE = 1024  # side views, for shape and height only


def load_upright(path) -> Image.Image:
    with Image.open(path) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def jpeg_bytes(image, max_side, quality=85) -> bytes:
    copy = image.copy()
    copy.thumbnail((max_side, max_side), Image.LANCZOS)
    out = BytesIO()
    copy.save(out, "JPEG", quality=quality)
    return out.getvalue()


def to_detection(item, region) -> dict:
    """One piece from Spark's reply -> a detection in the inventory vocabulary.
    The model's own words stay in 'raw' for the review screen."""
    point = None
    at = item.get("at")
    if isinstance(at, (list, tuple)) and len(at) == 2 and all(isinstance(v, (int, float)) for v in at):
        x0, y0, x1, y1 = region.bbox
        fx, fy = (min(max(float(v), 0.0), 1.0) for v in at)
        point = [round(x0 + fx * (x1 - x0)), round(y0 + fy * (y1 - y0))]
    try:
        confidence = min(max(float(item.get("confidence")), 0.0), 1.0)
    except (TypeError, ValueError):
        confidence = None
    try:
        count = max(int(item.get("count", 1)), 1)
    except (TypeError, ValueError):
        count = 1
    return {
        "photo_view": COUNT_VIEW,
        "region": {"bbox": list(region.bbox), "point": point},
        "family": vocab.normalize_family(item.get("family")),
        "shape": str(item.get("shape") or "")[:80],
        "size": vocab.normalize_size(item.get("size")),
        "color": vocab.normalize_color(item.get("color")),
        "plain": item.get("plain") is True,
        "count": count,
        "confidence": confidence,
        "raw": item,
    }


def classify_batch(conn, batch_id, batch_dir, segmenter, spark, context=True) -> dict:
    """Run segmenter + Spark over a registered batch and store the proposals.
    Returns a run report: per-region call stats and anything skipped."""
    photos = {p["view"]: p for p in db.batch_photos(conn, batch_id)}
    if COUNT_VIEW not in photos:
        raise ValueError(f"batch {batch_id} has no {COUNT_VIEW} photo")
    top = load_upright(batch_dir / photos[COUNT_VIEW]["file"])
    side = []
    if context:
        side = [(view, jpeg_bytes(load_upright(batch_dir / photos[view]["file"]), CONTEXT_MAX_SIDE))
                for view in SIDE_VIEWS if view in photos]
    detections, calls = [], []
    for region in segmenter.segment(top):
        try:
            data, reply = spark.identify_pieces(jpeg_bytes(top.crop(region.bbox), REGION_MAX_SIDE), side)
        except SparkError as err:
            db.record_classify_error(conn, batch_id, f"region {list(region.bbox)}: {err}")
            raise
        kept = [item for item in data["pieces"] if isinstance(item, dict)]
        detections += [to_detection(item, region) for item in kept]
        calls.append({
            "region": list(region.bbox), "pieces": len(kept),
            "skipped": len(data["pieces"]) - len(kept), "model_total": data.get("total"),
            "seconds": reply.seconds, "finish_reason": reply.finish_reason, "usage": reply.usage,
        })
    classifier = f"spark:{spark.model} + {segmenter.name}" + ("" if context else " (no side views)")
    db.replace_detections(conn, batch_id, detections, classifier)
    return {"classifier": classifier, "pieces": sum(d["count"] for d in detections), "calls": calls}
