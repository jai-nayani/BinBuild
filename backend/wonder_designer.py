"""Wonder designer: a new model from the pieces in the bin, every kind of them.

Muse Wonder is asked for a design in the extended line format of
backend/wonder_design.py, using only the owned pieces (exact counts, LDraw
geometry). Every proposal goes through the validator; on failure the errors
go back to Wonder in the same conversation and it tries again, at most
MAX_ATTEMPTS times. The result is a design that passed, with its parts list,
placements and a booklet, or an explicit failure naming the shortfall and
the errors of the last attempt, like Path A.

This is a parallel track: nothing in the app calls it, and live generation
stays off elsewhere. From the repo root:
    python -m backend.wonder_designer --target "a simple house"
    python -m backend.wonder_designer --replay tests/fixtures/wonder-house-recorded.json
Output goes to data/wonder/<time>/ (git-ignored): design.txt, report.json,
booklet.html.
"""

import argparse
import json
import re
import sqlite3
import time
from collections import Counter
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import booklet as bk
from . import wonder_design as wd

MAX_ATTEMPTS = 5
REPO = Path(__file__).resolve().parent.parent

TOP = {
    "all": "a stud on every cell",
    "none": "no studs on top: nothing can be held on it",
    "off_grid": "one stud between its two cells, off the grid: nothing may go on it",
}


def piece_lines(owned) -> str:
    lines = []
    for code, color, size, n, part in wd.usable_pieces(owned):
        if part.top == "edge":
            top = ("4 studs along one long edge (the edge studs= names); the other half tapers off and can't "
                   "hold anything, and only the studded half grips studs below") if code == "wedge_plate" else \
                  "2 studs along the edge studs= names; the other half is smooth"
        elif part.top == "low_end":
            top = (f"one end is a flat step {part.low_end_height} plates tall with one stud; over the other end "
                   f"the top curves, highest ({part.height} plates) next to the step and falling away to the far "
                   "end, with no stud; down= names the STUD end (so the curve falls away the opposite way)")
        else:
            top = TOP[part.top]
        need = {"down": "needs down=±x or ±y, the way it slopes down along its length",
                "studs": "needs studs=±x or ±y", "clip": "needs clip=±x or ±y, the end its clip is on (the clip "
                                                          "takes up the next cell at that height)"}.get(part.direction)
        if part.top == "all" and size == "1x1":
            top = "one stud on top"
        tall = "" if part.top == "low_end" else f"{part.height} plate{'s' if part.height != 1 else ''} tall; "
        lines.append(f"- {code} {color} {size} ×{n}: {tall}{top}" + (f"; {need}" if need else ""))
    return "\n".join(lines)


def instructions(owned) -> str:
    return (
        "You design small LEGO models for a child to build from a bin of loose pieces. Use ONLY the pieces "
        "listed below, never more of a kind than its count, and no other pieces. Use whichever kinds suit the "
        "model: plates, slopes, tiles and modified pieces as well as bricks.\n\n"
        "The pieces in the bin (code colour size ×count: what it is like):\n" + piece_lines(owned) + "\n\n"
        "How a design is written, one piece per line:\n"
        "  SIZE (x,y,z) code colour [down=±x|±y, studs=±x|±y or clip=±x|±y]\n"
        "- SIZE is HxW: H studs along x, W studs along y. A 1x2 piece lying along y is 1x2; along x it is 2x1.\n"
        "- (x,y,z) is the piece's minimum corner: x and y in studs (0 to 19), z in PLATES above the table "
        "(a plate or tile is 1 plate tall, a brick 3).\n"
        "- e.g. '2x1 (3,0,1) brick orange' is an orange 1x2 brick along x, standing on a plate (z=1).\n\n"
        "Rules every design must pass (a program checks them exactly):\n"
        "1. Held by studs. A piece is held only where its bottom sits on studs of the piece below it: its z "
        "equals that piece's z plus its height, over a cell where that piece has a stud. Every piece must be "
        "held this way to the rest, one connected model, nothing floating. A piece resting on a surface without "
        "studs (a tile, a slope, a cheese slope, a round tile, the smooth half of the edge-stud tile, the curved "
        "end of the azure curved slope) is NOT held there. Side studs, clips and bars do not count.\n"
        "2. No two pieces in the same space. A piece fills its whole footprint for its full height.\n"
        "3. The lowest pieces stand on the table at z=0; everything stays on the 20x20 grid.\n"
        "4. Counts: never more of a kind (code, colour, size) than the bin has.\n\n"
        "Before answering, check every line against rules 1 to 4.\n"
        "Reply with 'Title: <a short name>' on the first line, then the design in a ```design fenced block, "
        "one piece per line, nothing else inside the block.")


def design_request(target) -> str:
    return (f"Design {target}. A child should recognise it at once. Keep it small: 10 to 30 pieces. It must "
            "stand on its own on the table.")


def feedback(check) -> str:
    errors = "\n".join(f"- {e}" for e in check.errors[:40])
    more = f"\n- ... and {len(check.errors) - 40} more" if len(check.errors) > 40 else ""
    return ("The checker rejected that design:\n" + errors + more +
            "\n\nFix every error and reply with the whole corrected design, in the same format "
            "('Title: ...' then a ```design block).")


def extract(text):
    """(title, design text) from a reply."""
    title = re.search(r"^\s*Title:\s*(.+)$", text, re.M)
    block = re.search(r"```design\s*\n(.*?)```", text, re.S) or re.search(r"```[a-z]*\s*\n(.*?)```", text, re.S)
    body = block.group(1) if block else "\n".join(l for l in text.splitlines() if wd.LINE.match(l.strip()))
    return (title.group(1).strip() if title else "Wonder design"), body.strip()


@dataclass
class Attempt:
    n: int
    reply_id: str
    title: str
    design: str
    errors: list
    shortfall: dict
    seconds: float
    usage: dict
    usd: float


@dataclass
class Result:
    ok: bool
    target: str
    attempts: list = field(default_factory=list)
    title: str = ""
    design: str = ""
    check: object = None
    reason: str = ""
    shortfall: dict = field(default_factory=dict)

    @property
    def usd(self):
        return round(sum(a.usd for a in self.attempts), 4)

    @property
    def seconds(self):
        return round(sum(a.seconds for a in self.attempts), 1)


def design(client, owned, target="a simple house", max_attempts=MAX_ATTEMPTS, log=print) -> Result:
    """Ask, check, feed the errors back, at most max_attempts times."""
    result = Result(False, target)
    previous, text = None, design_request(target)
    for n in range(1, max_attempts + 1):
        reply = client.respond(text, instructions=instructions(owned) if previous is None else None,
                               previous_id=previous)
        title, body = extract(reply.text)
        check = wd.validate(body, owned)
        usd = getattr(reply, "usd", 0.0)
        result.attempts.append(Attempt(n, reply.id, title, body, check.errors, check.shortfall,
                                       reply.seconds, reply.usage, usd))
        log(f"attempt {n}: {check.parts} pieces, {len(check.errors)} errors, {reply.seconds} s, ${usd}")
        if check.ok:
            result.ok, result.title, result.design, result.check = True, title, body, check
            return result
        previous, text = reply.id, feedback(check)
    last = result.attempts[-1]
    result.title, result.design = last.title, last.design
    result.shortfall = last.shortfall
    result.reason = (f"no valid design in {max_attempts} attempts; "
                     + (f"short of {', '.join(f'{n}× {k}' for k, n in last.shortfall.items())}; "
                        if last.shortfall else "")
                     + f"{len(last.errors)} errors left in the last attempt")
    return result


def parts_list(pieces) -> list:
    counts = Counter(p.key for p in pieces)
    return [{"label": wd.label(k), "qty": n, "ldraw": wd.part_for(*_code_size_color(k)).ldraw} for k, n in
            sorted(counts.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][3]))]


def _code_size_color(key):
    family, shape, size, color = key
    code = {v: c for c, v in wd.CODES.items()}[(family, shape)]
    return code, size, color


def make_booklet(title, pieces, target, turn=False):
    places = wd.placements(pieces, turn=turn)
    layers = {}
    for i, p in enumerate(pieces):
        layers.setdefault(p.z, []).append(i)
    steps = []
    for n, z in enumerate(sorted(layers), 1):
        count = len(layers[z])
        text = (f"Start here: lay {'this piece' if count == 1 else f'these {count} pieces'} on the table."
                if z == 0 else f"Add {'this piece' if count == 1 else f'these {count} pieces'} "
                               f"({z} plate{'s' if z != 1 else ''} up), pressing "
                               f"{'it' if count == 1 else 'them'} onto the studs below.")
        steps.append((text, layers[z]))
    notes = [f"Designed by Muse Wonder for “{target}” from the pieces in your bin, then checked by BinBuild: "
             "only pieces you own, every piece held by studs, nothing floating.",
             "Nobody has built it yet: if something doesn't hold, tell us."]
    return bk.booklet(title, f"{len(pieces)} pieces, {len(steps)} steps.", places, steps,
                      source="the pieces in your bin (Muse Wonder design)", notes=notes)


def owned_inventory(source="db") -> dict:
    """The confirmed inventory, read-only from binbuild.db."""
    from . import inventory_db
    path = inventory_db.DB_PATH
    with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        return wd.owned_from_items(inventory_db.inventory_summary(conn)["items"])


class ReplayWonder:
    """Stands in for WonderClient: plays back a recorded run's replies in order."""

    model = "replay:muse-wonder-1.0"

    def __init__(self, recorded):
        self.replies = list(recorded["replies"])
        self.requests = 0

    def respond(self, text, instructions=None, previous_id=None):
        from .wonder_client import WonderReply
        if self.requests >= len(self.replies):
            raise RuntimeError("the recording has no more replies")
        r = self.replies[self.requests]
        self.requests += 1
        return WonderReply(r["id"], r["text"], "completed", r.get("usage", {}), 0.0)


def write_outputs(result, owned, out_dir) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "target": result.target, "ok": result.ok, "title": result.title, "reason": result.reason,
        "shortfall": result.shortfall, "usd": result.usd, "seconds": result.seconds,
        "attempts": [{"n": a.n, "pieces": len(wd.parse(a.design)[0]), "errors": a.errors, "seconds": a.seconds,
                      "usd": a.usd, "usage": a.usage} for a in result.attempts],
    }
    (out_dir / "design.txt").write_text(result.design + "\n")
    if result.ok:
        pieces = result.check.pieces
        report["parts"] = parts_list(pieces)
        report["placements"] = [p.text() for p in pieces]
        report["pieces"] = len(pieces)
        book = make_booklet(result.title, pieces, result.target)
        (out_dir / "booklet.html").write_text(bk.render_html(book))
    (out_dir / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    return report


def main():
    parser = argparse.ArgumentParser(description="Design a new model from the bin with Muse Wonder.")
    parser.add_argument("--target", default="a simple house")
    parser.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--attempts", type=int, default=MAX_ATTEMPTS)
    parser.add_argument("--replay", type=Path, help="a recorded run to play back instead of calling Wonder")
    parser.add_argument("--record", type=Path, help="also save Wonder's replies here (for --replay)")
    parser.add_argument("--booklet", type=Path, help="just check a design file and make its booklet")
    parser.add_argument("--turn", action="store_true", help="draw the booklet's pictures turned 180 degrees")
    parser.add_argument("--out", type=Path,
                        default=REPO / "data" / "wonder" / f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}")
    args = parser.parse_args()
    owned = owned_inventory()
    if args.booklet:
        check = wd.validate(args.booklet.read_text(), owned)
        if not check.ok:
            print("not valid:\n" + "\n".join(check.errors))
            return
        title = next((l[1:].split(":")[0].strip() for l in args.booklet.read_text().splitlines()
                      if l.startswith("#")), "Wonder design")
        args.out.mkdir(parents=True, exist_ok=True)
        book = make_booklet(title, check.pieces, args.target, turn=args.turn)
        (args.out / "booklet.html").write_text(bk.render_html(book))
        print(f"valid, {check.parts} pieces; booklet: {args.out / 'booklet.html'}")
        return
    if args.replay:
        recorded = json.loads(args.replay.read_text())
        client = ReplayWonder(recorded)
        args.target = recorded.get("target", args.target)
    else:
        from .wonder_client import WonderClient
        client = WonderClient.from_env(effort=args.effort)
    started = time.monotonic()
    replies = []
    respond = client.respond

    def recording(text, instructions=None, previous_id=None):
        r = respond(text, instructions=instructions, previous_id=previous_id)
        replies.append({"id": r.id, "text": r.text, "usage": r.usage, "seconds": r.seconds})
        return r
    client.respond = recording
    result = design(client, owned, args.target, args.attempts)
    report = write_outputs(result, owned, args.out)
    if args.record:
        args.record.write_text(json.dumps({"target": args.target, "model": "muse-wonder-1.0",
                                           "effort": args.effort, "replies": replies}, indent=1) + "\n")
    print(json.dumps({k: report[k] for k in ("ok", "title", "reason", "usd", "seconds")}))
    print(f"wall time {round(time.monotonic() - started, 1)} s; outputs in {args.out}")
    if result.ok:
        print("\n".join(report["placements"]))


if __name__ == "__main__":
    main()
