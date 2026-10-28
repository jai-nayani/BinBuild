"""Photo gate: cheap local checks on every batch photo, run before any Spark call.

A photo fails when it is unreadable, does not look like a photo straight from
a phone camera, is too dark, too bright, shows no LEGO pieces, or is blurry.
Failed photos block classification and confirmation until they are retaken,
so a bad or doctored image can't spend Baseten tokens or add pieces.

Pillow only. Thresholds were tuned on the real kit batch 20261028-192429-119901
(a dark table, 12 MP 4:3 phone photos) and on blurred, darkened, brightened,
empty-table and non-LEGO images; see IMAGE-GUARDRAILS.md for the measurements.
They are heuristics: they stop clearly bad photos, not a determined forger.
"""

from dataclasses import dataclass, field

from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat

THRESHOLDS = {
    "min_megapixels": 3.0,          # phone cameras give 12 MP; screenshots and downloads are often smaller
    "camera_aspects": (1.0, 4 / 3, 3 / 2, 16 / 9),
    "aspect_tolerance": 0.03,
    "max_flat_fraction": 0.15,      # share of 16x16 blocks with no camera noise at all (std < 0.5)
    "min_mean": 35,                 # mean brightness 0-255; the good photos are 86-115
    "min_p99": 40,                  # the brightest 1% of pixels
    "max_mean": 220,
    "max_clipped": 0.25,            # share of pixels at 250-255; the good photos are under 0.01
    "min_sharpness": 300,           # Laplacian variance, mean of the 5 sharpest tiles; good photos 514-960
    "min_colour_pieces": 2,         # colourful piece-sized blobs; good photos 12-20
    "min_piece_blobs": 10,          # or this many piece-sized blobs of any colour
}
CAMERA_FORMATS = {"JPEG", "MPO", "HEIF", "WEBP"}

# Reason codes, most important first. Each has a plain sentence and a tip.
REASONS = {
    "unreadable": ("We couldn't open it as a photo.", "Take it again with the camera button."),
    "not_camera_photo": ("It doesn't look like a photo straight from the camera: it looks like a "
                         "screenshot, a saved picture or an edited image.",
                         "Take it with the camera button, not from screenshots or downloads."),
    "duplicate": ("It's the same photo as one already sent.", "Take a new photo of this view."),
    "too_dark": ("It's too dark.", "Turn on a light or move nearer a window."),
    "too_bright": ("It's too bright or washed out.", "Move out of direct sunlight and turn the flash off."),
    "no_pieces": ("We can't see any LEGO pieces in it.", "Make sure the pieces are in the middle of the frame."),
    "blurry": ("It's blurry.", "Hold the phone steady and tap on the pieces to focus."),
    "not_real_lego": ("It doesn't look like real LEGO pieces on a table.",
                      "Photograph the real pieces on the table, not a screen or a printed picture."),
}
ORDER = tuple(REASONS)

_LAPLACE = ImageFilter.Kernel((3, 3), (0, 1, 0, 1, -4, 1, 0, 1, 0), scale=1, offset=128)


@dataclass
class GateResult:
    passed: bool
    reasons: list = field(default_factory=list)  # codes, most important first
    metrics: dict = field(default_factory=dict)


def explain(reasons) -> dict:
    """The first reason as a plain sentence plus a tip, for the retake pop-up."""
    code = sorted(reasons, key=ORDER.index)[0] if reasons else None
    text, tip = REASONS.get(code, ("", ""))
    return {"reason": code, "reason_text": text, "tip": tip}


def retake_notice(view, reasons) -> dict:
    """What the retake pop-up says about one photo that needs retaking."""
    info = explain(reasons)
    if info["reason"] is None:
        message = f"The {view} photo hasn't been checked yet."
    else:
        message = f"The {view} photo is unclear. {info['reason_text']} {info['tip']} Please retake just this photo."
    return {"view": view, "reasons": list(reasons), **info, "message": message}


def _percentile(hist, q):
    total, seen = sum(hist), 0
    for value, n in enumerate(hist):
        seen += n
        if seen >= q * total:
            return value
    return 255


def _flat_fraction(gray) -> float:
    """Share of 16x16 blocks with essentially no variation. Camera sensors
    always leave some noise; screenshots, drawings and renders have big
    perfectly flat areas."""
    width, height = gray.size
    blocks = flat = 0
    for y in range(0, height - 15, 16):
        for x in range(0, width - 15, 16):
            blocks += 1
            if ImageStat.Stat(gray.crop((x, y, x + 16, y + 16))).stddev[0] < 0.5:
                flat += 1
    return flat / blocks if blocks else 0.0


def _sharpness(gray) -> float:
    """Mean Laplacian variance of the 5 sharpest of 8x6 tiles. Taking the
    sharpest tiles ignores bare table and a blurred background."""
    lap = gray.filter(_LAPLACE)
    width, height = lap.size
    tiles = sorted(
        ImageStat.Stat(lap.crop((tx * width // 8, ty * height // 6,
                                 (tx + 1) * width // 8, (ty + 1) * height // 6))).var[0]
        for ty in range(6) for tx in range(8)
    )
    return sum(tiles[-5:]) / 5


def _piece_blobs(image) -> tuple:
    """Count piece-sized blobs on a 320 px copy: pixels that are colourful
    plastic or stand out from the background brightness, cleaned up and
    grouped. Returns (piece-sized blobs, colourful ones)."""
    small = image.copy()
    small.thumbnail((320, 320))
    _, sat, val = small.convert("HSV").split()
    gray = small.convert("L")
    median = _percentile(gray.histogram(), 0.5)
    colourful = ImageChops.multiply(sat.point(lambda s: 255 if s >= 100 else 0),
                                    val.point(lambda v: 255 if v >= 60 else 0))
    contrast = gray.point(lambda g: 255 if abs(g - median) >= 70 else 0)
    mask = ImageChops.lighter(colourful, contrast).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    width, height = mask.size
    on = mask.load()
    sp = sat.load()
    seen = bytearray(width * height)
    total = width * height
    pieces = colour = 0
    for y0 in range(height):
        for x0 in range(width):
            if not on[x0, y0] or seen[y0 * width + x0]:
                continue
            seen[y0 * width + x0] = 1
            stack = [(x0, y0)]
            area = sat_sum = 0
            left, right, top, bottom = x0, x0, y0, y0
            while stack:
                x, y = stack.pop()
                area += 1
                sat_sum += sp[x, y]
                left, right = min(left, x), max(right, x)
                top, bottom = min(top, y), max(bottom, y)
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < width and 0 <= ny < height and on[nx, ny] and not seen[ny * width + nx]:
                        seen[ny * width + nx] = 1
                        stack.append((nx, ny))
            box_w, box_h = right - left + 1, bottom - top + 1
            if (0.0004 <= area / total <= 0.03 and max(box_w, box_h) / min(box_w, box_h) <= 6
                    and area / (box_w * box_h) >= 0.3):
                pieces += 1
                if sat_sum / area >= 90:
                    colour += 1
    return pieces, colour


def check_image(image, fmt, original_size) -> GateResult:
    """Run the checks on an upright RGB image. fmt and original_size describe
    the file as uploaded (format name, (width, height) before any downscale)."""
    t = THRESHOLDS
    width, height = original_size
    megapixels = width * height / 1e6
    aspect = max(width, height) / min(width, height)
    work = image.copy()
    work.thumbnail((1024, 1024))
    gray = work.convert("L")
    hist = gray.histogram()
    pixels = sum(hist)
    m = {
        "format": fmt, "width": width, "height": height, "megapixels": round(megapixels, 1),
        "aspect": round(aspect, 3),
        "mean": round(ImageStat.Stat(gray).mean[0], 1),
        "p99": _percentile(hist, 0.99),
        "clipped": round(sum(hist[250:]) / pixels, 3),
    }
    reasons = []
    too_dark = m["mean"] < t["min_mean"] or m["p99"] < t["min_p99"]
    too_bright = m["mean"] > t["max_mean"] or m["clipped"] > t["max_clipped"]
    camera_shape = any(abs(aspect - a) <= t["aspect_tolerance"] * a for a in t["camera_aspects"])
    m["flat_fraction"] = round(_flat_fraction(gray), 3)
    not_camera = (fmt not in CAMERA_FORMATS or megapixels < t["min_megapixels"] or not camera_shape
                  # clipped or crushed areas are flat too; judge flatness only on usable exposure
                  or (not too_dark and not too_bright and m["flat_fraction"] > t["max_flat_fraction"]))
    if not_camera:
        reasons.append("not_camera_photo")
    if too_dark:
        reasons.append("too_dark")
    if too_bright:
        reasons.append("too_bright")
    m["piece_blobs"], m["colour_pieces"] = _piece_blobs(image)
    has_pieces = m["colour_pieces"] >= t["min_colour_pieces"] or m["piece_blobs"] >= t["min_piece_blobs"]
    if not has_pieces:
        reasons.append("no_pieces")
    m["sharpness"] = round(_sharpness(gray), 1)
    # Sharpness only means something with pieces to focus on and a usable exposure.
    if has_pieces and not too_dark and not too_bright and m["sharpness"] < t["min_sharpness"]:
        reasons.append("blurry")
    return GateResult(not reasons, reasons, m)


def check_photo(path) -> GateResult:
    """Open a photo file, turn it upright and run check_image."""
    try:
        with Image.open(path) as im:
            fmt = im.format
            original_size = im.size
            im.draft("RGB", (1600, 1600))  # JPEG: decode at reduced size, much faster
            image = ImageOps.exif_transpose(im).convert("RGB")
    except Exception as err:  # Pillow raises many types for broken or unsupported files
        return GateResult(False, ["unreadable"], {"error": type(err).__name__})
    return check_image(image, fmt, original_size)
