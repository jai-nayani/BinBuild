"""Classify one batch: segment the top view, ask Spark what is in each region,
and store the answers as proposed detections for review.

With SAM 3.1 (refine_with_sam), after the whole-photo pass: Spark's centre
point on each piece prompts SAM for that piece's mask; each piece is cut out
(everything outside its mask darkened), the close-ups go to Spark on numbered
contact sheets, and Spark names one piece per tile. The count is the number
of points SAM was given, one detection per point; SAM can flag two points on
the same piece (overlapping masks) and points with no piece under them, but
it can't add a piece the whole-photo pass missed.

Photos are turned upright (phone JPEGs carry an EXIF rotation the model
ignores), cropped to the region and downscaled before they are sent.

Guardrails: nothing is sent while any photo is failed or unchecked by the
photo gate. Spark must first answer "yes" for every image to "is this real,
physical LEGO on a table?"; any "no" or "uncertain" fails that photo and
nothing is stored. Spark's words are mapped onto the fixed vocabulary, each
entry counts as exactly one piece, and an implausible number of pieces is
treated as an error. Classifying never adds to the inventory: that still
needs review and confirm.
"""

import math
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from . import inventory_db as db
from . import inventory_vocab as vocab
from .segmenter import COUNT_VIEW, SamSegmenter
from .spark_client import SparkError, image_checks, tiles_by_number

SIDE_VIEWS = ("front", "right", "back", "left")
REGION_MAX_SIDE = 2048   # the counted region
CONTEXT_MAX_SIDE = 1024  # side views, for shape and height only
MAX_PIECES_PER_REGION = 300  # one flat layer in one photo; more means a broken or steered reply
TILE = 320             # pixels per close-up on a contact sheet
TILE_COLUMNS = 4
TILES_PER_SHEET = 16   # one Spark call per sheet
TILE_PAD = 0.35        # context round a piece, as a fraction of its box
OUTSIDE_MASK = 0.3     # brightness kept outside a piece's mask
DUPLICATE_IOU = 0.5    # two masks overlapping this much are the same piece


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
    return {
        "photo_view": COUNT_VIEW,
        "region": {"bbox": list(region.bbox), "point": point},
        "family": vocab.normalize_family(item.get("family")),
        "shape": "".join(ch for ch in str(item.get("shape") or "") if ch.isprintable())[:80],
        "size": vocab.normalize_size(item.get("size")),
        "color": vocab.normalize_color(item.get("color")),
        "plain": item.get("plain") is True,
        "count": 1,  # one entry per physical piece; a "count" in the reply is ignored
        "confidence": confidence,
        "raw": item,
    }


def classify_batch(conn, batch_id, batch_dir, segmenter, spark, context=True) -> dict:
    """Run segmenter + Spark over a registered batch and store the proposals.
    Returns a run report: per-region call stats and anything skipped.
    Raises db.PhotosNotReady, before any Spark call, if a photo needs a
    retake, and after the call if Spark failed a photo."""
    db.require_photos_passed(conn, batch_id)
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
            if len(data["pieces"]) > MAX_PIECES_PER_REGION:
                raise SparkError(f"{len(data['pieces'])} pieces in one region is not plausible; nothing stored")
        except SparkError as err:
            db.record_classify_error(conn, batch_id, f"region {list(region.bbox)}: {err}")
            raise
        views = [COUNT_VIEW] + [view for view, _ in side]
        checks = {views[n - 1]: v for n, v in image_checks(data, len(views)).items()}
        verdicts = {view: v for view, v in checks.items() if v["answer"] != "yes"}
        if verdicts:
            db.reject_photos(conn, batch_id, verdicts, f"Spark check failed: {sorted(verdicts)}")
            raise db.PhotosNotReady(batch_id, db.photos_needing_retake(conn, batch_id))
        kept = [item for item in data["pieces"] if isinstance(item, dict)]
        detections += [to_detection(item, region) for item in kept]
        calls.append({
            "region": list(region.bbox), "checks": checks, "pieces": len(kept),
            "skipped": len(data["pieces"]) - len(kept), "model_total": data.get("total"),
            "seconds": reply.seconds, "finish_reason": reply.finish_reason, "usage": reply.usage,
        })
    classifier = f"spark:{spark.model} + {segmenter.name}" + ("" if context else " (no side views)")
    db.replace_detections(conn, batch_id, detections, classifier)
    return {"classifier": classifier, "pieces": sum(d["count"] for d in detections), "calls": calls}


# --- SAM 3.1: one close-up per piece ----------------------------------------------

def _mask_image(region, crop_box):
    """The region's SAM mask as an "L" image over crop_box (upright photo pixels)."""
    m = region.mask.sam
    sx, sy = region.mask.scale
    raster = Image.frombytes("L", (m.width, m.height), bytes(255 if v else 0 for v in m.raster))
    left, top = m.box[0] / sx, m.box[1] / sy
    size = (max(1, round((m.box[2] - m.box[0]) / sx)), max(1, round((m.box[3] - m.box[1]) / sy)))
    canvas = Image.new("L", (crop_box[2] - crop_box[0], crop_box[3] - crop_box[1]), 0)
    canvas.paste(raster.resize(size, Image.BILINEAR), (round(left) - crop_box[0], round(top) - crop_box[1]))
    return canvas.filter(ImageFilter.MaxFilter(5))  # a few pixels' margin so edges aren't cut off


def piece_crop(image, region):
    """A piece's close-up from the upright photo: its box plus some context,
    everything outside SAM's mask darkened. Without a mask, the plain crop."""
    x0, y0, x1, y1 = region.bbox
    pad = max(16, round(TILE_PAD * max(x1 - x0, y1 - y0)))
    box = (max(0, x0 - pad), max(0, y0 - pad), min(image.width, x1 + pad), min(image.height, y1 + pad))
    crop = image.crop(box)
    if region.mask is None:
        return crop
    dark = ImageEnhance.Brightness(crop).enhance(OUTSIDE_MASK)
    return Image.composite(crop, dark, _mask_image(region, box))


def _font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow without FreeType sizes
        return ImageFont.load_default()


def tile_sheet(crops):
    """Numbered close-ups (1, 2, ...) on one contact sheet."""
    rows = math.ceil(len(crops) / TILE_COLUMNS)
    sheet = Image.new("RGB", (TILE_COLUMNS * TILE, rows * TILE), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    font = _font(26)
    for n, crop in enumerate(crops):
        col, row = n % TILE_COLUMNS, n // TILE_COLUMNS
        thumb = ImageOps.contain(crop.convert("RGB"), (TILE - 10, TILE - 10), Image.LANCZOS)
        x, y = col * TILE, row * TILE
        sheet.paste(thumb, (x + (TILE - thumb.width) // 2, y + (TILE - thumb.height) // 2))
        draw.rectangle((x, y, x + TILE - 1, y + TILE - 1), outline=(110, 110, 110), width=2)
        draw.rectangle((x + 4, y + 4, x + 50, y + 38), fill=(255, 213, 0))
        draw.text((x + 10, y + 7), str(n + 1), fill=(0, 0, 0), font=font)
    return sheet


def _pixels(region):
    """The set of SAM-frame pixels a region's mask covers (for overlap checks)."""
    m = region.mask.sam
    x0, y0 = m.box[0], m.box[1]
    return {(x0 + i % m.width, y0 + i // m.width) for i, v in enumerate(m.raster) if v}


def overlaps(regions) -> dict:
    """{i: j} for masks that overlap an earlier one by more than DUPLICATE_IOU:
    two points on the same piece."""
    pixels = {}
    found = {}
    for i, r in enumerate(regions):
        if r.mask is None:
            continue
        pixels[i] = _pixels(r)
        for j in range(i):
            if j not in pixels or j in found:
                continue
            a, b = r.mask.sam.box, regions[j].mask.sam.box
            if a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]:
                continue
            union = len(pixels[i] | pixels[j])
            if union and len(pixels[i] & pixels[j]) / union > DUPLICATE_IOU:
                found[i] = j
                break
    return found


def mask_overlay(image, regions, max_side=2048):
    """The photo with every mask tinted and numbered, for checking SAM by eye."""
    scale = min(1.0, max_side / max(image.size))
    base = image.resize((round(image.width * scale), round(image.height * scale))).convert("RGB")
    tint = Image.new("RGB", base.size, (255, 0, 160))
    font = _font(max(14, base.width // 90))
    for n, r in enumerate(regions, 1):
        if r.mask is not None:
            full = _mask_image(r, (0, 0, image.width, image.height)).resize(base.size)
            base = Image.composite(Image.blend(base, tint, 0.45), base, full)
        draw = ImageDraw.Draw(base)
        x, y = (r.point[0] * scale, r.point[1] * scale) if r.point else (r.bbox[0] * scale, r.bbox[1] * scale)
        draw.text((x + 6, y - 6), str(n), fill=(255, 255, 0) if r.mask is not None else (255, 60, 60), font=font,
                  stroke_width=2, stroke_fill=(0, 0, 0))
    return base


def _tile_detection(item, region, outline_path):
    try:
        confidence = min(max(float(item.get("confidence")), 0.0), 1.0)
    except (TypeError, ValueError):
        confidence = None
    m = region.mask.sam
    sx, sy = region.mask.scale
    return {
        "photo_view": COUNT_VIEW,
        "region": {"bbox": list(region.bbox), "point": [round(v) for v in region.point],
                   "mask": {"box": [round(m.box[0] / sx, 1), round(m.box[1] / sy, 1),
                                    round(m.box[2] / sx, 1), round(m.box[3] / sy, 1)],
                            "size": [m.width, m.height], "path": outline_path}},
        "family": vocab.normalize_family(item.get("family")),
        "shape": "".join(ch for ch in str(item.get("shape") or "") if ch.isprintable())[:80],
        "size": vocab.normalize_size(item.get("size")),
        "color": vocab.normalize_color(item.get("color")),
        "plain": item.get("plain") is True,
        "count": 1,
        "confidence": confidence,
    }


def _hint(d) -> str:
    """A whole-photo label as the tile prompt states it."""
    plain = ", plain" if d["plain"] else ", not plain"
    return f"{d['color']} {d['size'] or '?'} {d['family']} ({d['shape'] or d['family']}{plain})"


def refine_with_sam(conn, batch_id, batch_dir, sam, spark, context=True, hints=True, out_dir=None) -> dict:
    """The SAM pass, on a batch the whole-photo pass has classified and nobody
    has reviewed yet: Spark's centre points prompt SAM 3.1 for one mask per
    piece, the close-ups go to Spark on contact sheets, and the proposals are
    replaced by one per point, named from its close-up. A point SAM finds no
    piece under keeps its whole-photo label; overlapping masks (two points on
    one piece) are flagged for review, not removed. Nothing is confirmed.
    hints: give Spark the whole-photo label of each tile to check, rather
    than naming each close-up from scratch (see SAM-3-1.md for why).
    out_dir: also save the contact sheets and a mask overlay there."""
    from .sam_client import USD_PER_IMAGE, outline
    db.require_photos_passed(conn, batch_id)
    batch = db.get_batch(conn, batch_id)
    if batch["status"] != "classified":
        raise db.Conflict(f"batch {batch_id} is {batch['status']}; the SAM pass needs a classified batch "
                          "that is not confirmed")
    current = db.batch_review(conn, batch_id)["detections"]
    if any(d["status"] != "proposed" or d["source"] != "spark" for d in current):
        raise db.Conflict(f"batch {batch_id} already has review changes; run the SAM pass before reviewing")
    prompted = [d for d in current if d["region"] and d["region"].get("point")]
    if not prompted:
        raise db.Conflict(f"batch {batch_id} has no centre points to prompt SAM with")
    photos = {p["view"]: p for p in db.batch_photos(conn, batch_id)}
    top = load_upright(batch_dir / photos[COUNT_VIEW]["file"])
    side = [(view, jpeg_bytes(load_upright(batch_dir / photos[view]["file"]), CONTEXT_MAX_SIDE))
            for view in SIDE_VIEWS if view in photos] if context else []

    segmenter = SamSegmenter(sam, [d["region"]["point"] for d in prompted])
    started = time.monotonic()
    regions = segmenter.segment(top)
    sam_seconds = round(time.monotonic() - started, 1)
    crops = [piece_crop(top, r) for r in regions]
    starts = list(range(0, len(regions), TILES_PER_SHEET))
    jobs = []
    for start in starts:
        sheet = tile_sheet(crops[start:start + TILES_PER_SHEET])
        if out_dir is not None:
            sheet.save(out_dir / f"sheet-{start // TILES_PER_SHEET + 1}.jpg", quality=90)
        jobs.append(jpeg_bytes(sheet, TILE * TILE_COLUMNS, quality=90))
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:  # the sheets are independent: one call each, at once
        futures = [pool.submit(spark.name_tiles, job, min(TILES_PER_SHEET, len(regions) - start), side,
                               [_hint(d) for d in prompted[start:start + TILES_PER_SHEET]] if hints else None)
                   for job, start in zip(jobs, starts)]
        try:
            replies = [f.result() for f in futures]
        except SparkError as err:
            db.record_classify_error(conn, batch_id, f"tile sheets: {err}")
            raise
    named, sheets = {}, []
    for start, (data, reply) in zip(starts, replies):
        count = min(TILES_PER_SHEET, len(regions) - start)
        for number, item in tiles_by_number(data, count).items():
            named[start + number - 1] = item
        sheets.append({"tiles": count, "named": len(tiles_by_number(data, count)), "seconds": reply.seconds,
                       "finish_reason": reply.finish_reason, "usage": reply.usage, "reply": data})
    tiles_seconds = round(time.monotonic() - started, 1)
    if out_dir is not None:
        mask_overlay(top, regions).save(out_dir / "masks.jpg", quality=88)

    duplicates = overlaps(regions)
    detections, kept_whole = [], []
    for i, (d, region) in enumerate(zip(prompted, regions)):
        sam_info = {"mask": region.mask is not None, "confidence": region.score,
                    "area": region.mask.sam.area if region.mask else 0}
        if i in duplicates:
            sam_info["same_piece_as"] = duplicates[i] + 1  # 1-based, in point order
        item = named.get(i)
        if region.mask is None or not isinstance(item, dict):
            kept_whole.append(i + 1)
            det = {k: d[k] for k in ("family", "shape", "size", "color", "plain", "count", "confidence")}
            det.update(photo_view=COUNT_VIEW, region={"bbox": list(region.bbox), "point": d["region"]["point"]})
        else:
            det = _tile_detection(item, region, outline(region.mask.sam))
        det["raw"] = {"tile": item, "whole_photo": d["raw"], "sam": sam_info}
        detections.append(det)
    for d in current:
        if d not in prompted:  # a whole-photo piece without a point: kept as it was
            detections.append({**{k: d[k] for k in ("family", "shape", "size", "color", "plain", "count",
                                                    "confidence", "region", "raw")}, "photo_view": COUNT_VIEW})
    classifier = (f"spark:{spark.model} tiles{' checking the whole-photo labels' if hints else ''} + "
                  f"{segmenter.name}" + ("" if context else " (no side views)"))
    db.replace_detections(conn, batch_id, detections, classifier)
    sam_calls = [{**{k: v for k, v in c.items() if k not in ("raw_output", "points")}, "objects": len(c["points"])}
                 for c in segmenter.calls]
    return {
        "classifier": classifier, "pieces": sum(d["count"] for d in detections), "points": len(prompted),
        "masks": sum(r.mask is not None for r in regions), "no_mask": [i + 1 for i, r in enumerate(regions) if r.mask is None],
        "same_piece": {i + 1: j + 1 for i, j in duplicates.items()}, "kept_whole_photo_label": kept_whole,
        "sam": {"requests": len(sam_calls), "seconds": sam_seconds,
                "request_seconds": round(sum(c["seconds"] for c in sam_calls), 1),
                "usd": round(len(sam_calls) * USD_PER_IMAGE, 4), "calls": sam_calls,
                "recorded": [{"size": list(c["size"]), "points": c["points"], "output": c["raw_output"]}
                             for c in segmenter.calls]},
        "spark_tiles": {"calls": len(sheets), "seconds": tiles_seconds, "sheets": sheets},
    }
