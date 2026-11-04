"""Inventory-specific design proposals, checked before the phone shows them."""

import hashlib
import json
import re

from . import wonder_design as wd, wonder_designer as designer
from .spark_client import SparkError, parse_json_reply

# Wheel and axle connections are not represented by the current geometry.
UNSUPPORTED = re.compile(r"\b(car|cars|truck|trucks|vehicle|vehicles|wheel|wheels|axle|axles|rolling|"
                         r"bus|buses|train|trains|tractor|bicycle|bike|motorcycle|skateboard|scooter|cart)\b", re.I)


def inventory_key(summary, source=None):
    rows = sorted((i["family"], i["shape"], i.get("size") or "", i["color"], i["quantity"])
                  for i in summary["items"])
    return hashlib.sha256(json.dumps([source, rows], separators=(",", ":")).encode()).hexdigest()


def signature(pieces):
    x, y = min(p.x for p in pieces), min(p.y for p in pieces)
    return tuple(sorted((p.code, p.h, p.w, p.x - x, p.y - y, p.z, p.color, p.direction or "")
                        for p in pieces))


def propose(client, owned, max_attempts=3, on_attempt=None):
    """Return up to three different, checked designs; never invent a fallback."""
    available = sum(n for *_, n, part in wd.usable_pieces(owned))
    instructions = designer.instructions(owned).split("Reply with 'Title:")[0] + (
        "\nChoose the objects yourself from these pieces. Propose three recognisable, distinct objects, "
        "with different silhouettes, uses and names. Base the choices on the actual shapes, colours and "
        "quantities above, not a fixed menu. Each design uses its own subset of this same inventory; "
        "the three designs are alternatives. Make small, clear models with at most " + str(min(30, available)) +
        " pieces each. Do not suggest cars, trucks, vehicles, wheels, axles or rolling models: their "
        "connections are unsupported. Do not claim that a model floats, moves or performs a function "
        "the parts cannot provide. Do not pretend round bricks are wheels. Describe decorative models "
        "as decorative. Do not use the manual or any saved design.\n"
        'Return JSON only: {"ideas":[{"title":"short object name","description":"why these pieces suit it",'
        '"design":"one placement per line, in the format above"}]}. No Markdown fences in design strings.'
    )
    accepted, shapes, names = [], set(), set()
    previous, text = None, "Find three different things this exact inventory can build."
    for n in range(1, max_attempts + 1):
        reply = client.respond(text, instructions=instructions if previous is None else None, previous_id=previous)
        problems = []
        try:
            data = parse_json_reply(reply.text)
            if not isinstance(data.get("ideas"), list):
                raise SparkError("the reply needs an ideas list")
            candidates = data["ideas"][:3]
        except (SparkError, ValueError, TypeError) as err:
            candidates, problems = [], [str(err)]
        for idea in candidates:
            if not isinstance(idea, dict):
                problems.append("each idea needs a title, description and design")
                continue
            title, description, design = (idea.get(k) for k in ("title", "description", "design"))
            if not (isinstance(title, str) and 3 <= len(title.strip()) <= 60 and
                    isinstance(description, str) and 1 <= len(description.strip()) <= 240 and
                    isinstance(design, str) and len(design) <= 50000):
                problems.append("use a short title, description and readable design")
                continue
            if UNSUPPORTED.search(title + " " + description):
                problems.append(f"{title}: wheel and axle models are unsupported; choose a different object")
                continue
            check = wd.validate(design, owned)
            if not check.ok:
                problems.extend(f"{title}: {err}" for err in check.errors[:10])
                continue
            shape = signature(check.pieces)
            name = title.strip().casefold()
            if shape in shapes or name in names:
                problems.append(f"{title}: this repeats an accepted idea; choose a different object and layout")
                continue
            accepted.append({"title": title.strip(), "description": description.strip(), "design": design,
                             "pieces": check.parts})
            shapes.add(shape)
            names.add(name)
            if len(accepted) == 3:
                break
        if on_attempt:
            on_attempt(n, len(accepted), len(problems))
        if len(accepted) == 3:
            break
        previous = reply.id
        text = (f"{len(accepted)} ideas have passed. Return {3 - len(accepted)} new alternatives. "
                "Keep the same JSON format and use only the supplied inventory. Accepted names: "
                + ", ".join(i["title"] for i in accepted) + ".\n" + "\n".join(problems[:20]))
    return accepted
