"""Ask Muse Spark for words for a checked Wonder booklet.

The model receives the finished picture and the pieces for each layer. It
can change only the title and step text: the checked design, part lists and
drawings remain BinBuild's. A malformed answer or a failed call leaves the
original instructions available.
"""

import copy
import json
import re

from . import booklet as bk
from . import inventory_vocab as vocab
from .spark_client import SparkError, parse_json_reply


SUCCESS_NOTE = ("Step words written by Muse Spark from the checked design; the pieces and pictures come "
                "from BinBuild's checker.")
FALLBACK_NOTE = "Step words are BinBuild's own (Muse Spark couldn't write them this time)."
_WORDS = re.compile(r"[a-z]+(?:_[a-z]+)*", re.IGNORECASE)
_PNG = re.compile(r'data:image/png;base64,([A-Za-z0-9+/=]+)')


def _colors_in(text):
    """Recognised colour words, taking the longest colour name first.

    Trying a multi-word colour before its individual words stops 'dark blue'
    from being counted as both dark blue and blue. Three-word vocabulary
    names are included as well as the one- and two-word names.
    """
    words = _WORDS.findall(text.lower().replace("_", " "))
    colors, pos = set(), 0
    while pos < len(words):
        for width in (3, 2, 1):
            if pos + width > len(words):
                continue
            color = vocab.normalize_color(" ".join(words[pos:pos + width]))
            if color != "unknown":
                colors.add(color)
                pos += width
                break
        else:
            pos += 1
    return colors


def _step_colors(book, step):
    return {vocab.normalize_color(book["placements"][i]["part"].get("color"))
            for i in step["add"]}


def _request(book, target):
    """Give Spark the checked part list, layer heights and finished picture."""
    layers = []
    for step in book["steps"]:
        heights = sorted({book["placements"][i]["at"][2] for i in step["add"]})
        layers.append({"n": step["n"], "layer_heights_in_plates": heights, "parts": step["parts"]})
    prompt = (
        "Write short, friendly building instructions for a child. The picture shows the finished "
        "model. Use only the pieces listed for each numbered step, and describe where they go "
        "only when the picture supports it. Never add, remove or change pieces. The layer heights "
        "are in plates above the table. Keep every step under 240 characters. "
        "Return JSON only: {\"title\": \"short title\", \"steps\": [{\"n\": 1, \"text\": \"...\"}]}. "
        "Return exactly one step for each supplied number, in order.\n"
        + json.dumps({"target": target, "title": book["title"], "steps": layers}, ensure_ascii=False)
    )
    # cover() returns an SVG wrapping a PNG. Send the actual PNG, since the
    # vision API expects an image rather than an SVG document.
    cover = _PNG.search(bk.cover(book))
    if not cover:
        raise ValueError("the booklet cover has no PNG picture")
    return [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + cover.group(1)}},
    ]}]


def write_steps(book, target, spark):
    """Return a copy of book with safe Spark words, or the original words.

    The caller supplies the Spark client so tests can use a fake. The copied
    booklet preserves placements, all part lists, step additions and notes.
    """
    result = copy.deepcopy(book)
    try:
        reply = spark.chat(_request(book, target))
        if reply.finish_reason == "length":
            raise SparkError("Spark's step reply was cut off")
        data = parse_json_reply(reply.content)
        steps = data.get("steps")
        if not isinstance(steps, list) or len(steps) != len(book["steps"]):
            raise SparkError("Spark returned the wrong number of steps")
        if any(not isinstance(item, dict) or item.get("n") != source["n"]
               for source, item in zip(book["steps"], steps)):
            raise SparkError("Spark returned incorrect step numbers")
    except Exception:
        # A missing key, a rendering problem or a model error must not block
        # the validated build. No exception or key is exposed in the booklet.
        result.setdefault("notes", []).append(FALLBACK_NOTE)
        return result

    title = data.get("title")
    if isinstance(title, str) and 3 <= len(title.strip()) <= 40:
        result["title"] = title.strip()
    for source, updated, item in zip(book["steps"], result["steps"], steps):
        text = item.get("text")
        if not isinstance(text, str):
            continue
        text = text.strip()
        if 1 <= len(text) <= 240 and _colors_in(text) <= _step_colors(book, source):
            updated["text"] = text
    result.setdefault("notes", []).append(SUCCESS_NOTE)
    return result
