"""Hand-check a draft piece list from the manual against the kit, and record
its steps while building it.

A draft (backend/manual/drafts/<id>.json) is either the "Elements you'll
need" box of a manual build, transcribed from a photo of the book, or (for
builds that print no list) the parts Muse Wonder read from the picture of
the model (backend/manual_transcribe.py; "read_by" says which). It is not a
verified piece list until a person has laid those pieces out from the kit
next to the page and built the model once. While building it, the person
records the steps, one per layer: what to do, and where each piece goes.
Marking it done needs both, a list with no unsure line and steps that place
every piece of it exactly once. From then on it is verified: "What can I
build?" checks a bin against it and makes its booklet from those steps,
like house and tree.

From the repo root:
    python -m backend.manual_check                       # every draft, closest to verified first
    python -m backend.manual_check snappy-crab           # its checklist (lines numbered), steps, what's left
    python -m backend.manual_check snappy-crab --set "lime 1x2 plate with clip=2" --sure "#4"
    python -m backend.manual_check snappy-crab --record  # type the steps as you build, layer by layer
    python -m backend.manual_check snappy-crab --step "Lay the black hinge plate flat. :: #1 @0,0,0"
    python -m backend.manual_check snappy-crab --preview crab.html   # the booklet so far, to compare
    python -m backend.manual_check snappy-crab --done --by Jai --notes "built it, all there"
    python -m backend.manual_check snappy-crab --undo    # back to draft (the steps are kept)

Lines: "<color> <size> <shape>" as the checklist prints them, or "#n" for
line n of the checklist.
--set "LINE=QTY" changes a line's quantity (0 removes it) or adds a line
(give --family for a new line); --sure LINE confirms an unsure line as read.
--step "TEXT :: PIECES" adds a step. PIECES: "LINE @x,y,z" separated by ";",
several positions for one line allowed ("#2 @0,0,1 @3,0,1"). x and y count
studs along the table, z counts plates up (a brick is 3 plates). Add
"along y" for a piece whose long side runs along y, and "down +x" (-x, +y,
-y) for the way a slope falls. --undo-step drops the last step,
--clear-steps all of them.
Standard library only.
"""

import argparse
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

from . import booklet as bk
from .build_plan import (DRAFTS_DIR, checklist_order, draft_set, hand_checked, line_of, manual_drafts,
                         step_problems)
from .inventory_vocab import COLORS, FAMILIES

_line = line_of
DOWN = ("+x", "-x", "+y", "-y")
NUMBER = re.compile(r"-?\d+")


def _save(draft):
    draft["elements_total"] = sum(e["qty"] for e in draft["elements"])
    draft["unsure_elements"] = sum(e["qty"] for e in draft["elements"] if not e["sure"])
    (DRAFTS_DIR / f"{draft['id']}.json").write_text(json.dumps(draft, indent=1, ensure_ascii=False) + "\n")


def _place_text(p) -> str:
    extra = "".join(f" {k} {p[k]}" for k in ("along", "down") if p.get(k))
    return f"{p['line']} @{','.join(map(str, p['at']))}{extra}"


def to_place(draft) -> list:
    """What the steps still lack, as text: '2× lime 1x2 plate with clip', and
    any line placed too often or no longer on the list."""
    found = [p for p in step_problems(draft) if p != "no steps recorded yet"]
    return [p.removesuffix(" not placed yet") for p in found]


def show(draft) -> str:
    state = "HAND-CHECKED" if hand_checked(draft) else "DRAFT (not verified)"
    out = [f"{draft['name']} ({draft['id']}) · pages {', '.join(map(str, draft['pages']))} · {state}",
           f"Read from {draft['read_from']}.",
           f"{draft['elements_total']} elements, {draft['unsure_elements']} unsure.", ""]
    numbered = sorted(enumerate(draft["elements"], 1), key=lambda ne: ne[1]["sure"])
    for n, e in numbered:
        mark = "?" if not e["sure"] else " "
        doubt = f"   <- unsure: {e['doubt']}" if not e["sure"] else ""
        out.append(f" [{mark}] #{n:<2} {e['qty']:>2}× {_line(e)}{doubt}")
    steps = draft.get("steps") or []
    out.append("")
    if steps:
        out.append(f"Steps ({len(steps)}):")
        for k, step in enumerate(steps, 1):
            out.append(f"  {k}. {step['text']}")
            out += [f"       {_place_text(p)}" for p in step["place"]]
        left = to_place(draft)
        out.append("Every piece is placed." if not left else "Still to place: " + "; ".join(left) + ".")
    else:
        out.append("No steps yet: record them while you build it (--record, or --step), one per layer.")
    if hand_checked(draft):
        hc = draft["hand_check"]
        out += ["", f"Hand-checked on {hc['on']} by {hc['by']}." + (f" Notes: {hc['notes']}" if hc["notes"] else "")]
        out.append("Verified: What can I build? checks a bin for it and makes its booklet." if not step_problems(draft)
                   else "Not verified until its steps place every piece.")
    return "\n".join(out)


def resolve(name, draft) -> str:
    """A line's name from "#n" or the name itself."""
    name = " ".join(name.split())
    if re.fullmatch(r"#\d+", name):
        n = int(name[1:])
        if not 1 <= n <= len(draft["elements"]):
            raise ValueError(f"no line {name}: the list has lines #1 to #{len(draft['elements'])}")
        return _line(draft["elements"][n - 1])
    if name not in {_line(e) for e in draft["elements"]}:
        raise ValueError(f"no line {name!r} in {draft['id']}; use #n or a name the checklist prints")
    return name


def parse_pieces(text, draft) -> list:
    """'#2 @0,0,1 @3,0,1; black 1x2 curved slope @2,0,7 down -x' -> placements."""
    out = []
    for chunk in filter(None, (c.strip() for c in text.split(";"))):
        head, at_sign, tail = chunk.partition("@")
        if not at_sign:
            raise ValueError(f"{chunk!r}: say where it goes, e.g. {chunk} @0,0,0")
        line = resolve(head, draft)
        tokens = ("@" + tail).split()
        ats, opts, i = [], {}, 0
        while i < len(tokens):
            t = tokens[i]
            if t.startswith("@"):
                xyz = t[1:].split(",")
                if len(xyz) != 3 or not all(NUMBER.fullmatch(n) for n in xyz):
                    raise ValueError(f"{t!r}: a position is @x,y,z in whole studs and plates, e.g. @0,0,3")
                if int(xyz[2]) < 0:
                    raise ValueError(f"{t!r}: z counts plates up from the table, so it can't be below 0")
                ats.append([int(n) for n in xyz])
            elif t in ("along", "down") and i + 1 < len(tokens):
                opts[t] = tokens[i + 1]
                i += 1
            else:
                raise ValueError(f"{chunk!r}: don't know {t!r} (after the positions: 'along y', 'down -x')")
            i += 1
        if opts.get("along", "x") not in ("x", "y"):
            raise ValueError(f"{chunk!r}: along is x or y")
        if "down" in opts and opts["down"] not in DOWN:
            raise ValueError(f"{chunk!r}: down is one of {', '.join(DOWN)}")
        out += [{"line": line, "at": at, **opts} for at in ats]
    return out


def parse_step(spec, draft) -> dict:
    text, sep, pieces = spec.partition("::")
    if not sep or not text.strip() or not pieces.strip():
        raise ValueError(f"{spec!r}: a step is \"what to do :: LINE @x,y,z; ...\"")
    return {"text": " ".join(text.split()), "place": parse_pieces(pieces, draft)}


def add_step(draft, step) -> list:
    """Add a step unless it places a piece more often than the list holds;
    returns the problems (empty when added)."""
    want = {_line(e): e["qty"] for e in draft["elements"]}
    placed = Counter(p["line"] for s in (draft.get("steps") or []) + [step] for p in s["place"])
    over = [f"{line}: this would place {placed[line]}, the list has {want[line]}"
            for line in dict.fromkeys(p["line"] for p in step["place"]) if placed[line] > want[line]]
    if not over:
        draft.setdefault("steps", []).append(step)
        warn = overlaps(draft)
        if warn:
            print("check the positions: " + "; ".join(warn), file=sys.stderr)
    return over


def overlaps(draft) -> list:
    """Pieces whose boxes share space (usually a typo in a position). Only a
    warning: sideways pieces (clips, side studs) can't sit exactly on a grid."""
    parts = draft_set(dict(draft, hand_check={"by": "", "on": ""}))["parts"]
    seen, out = {}, []
    for k, step in enumerate(draft.get("steps") or [], 1):
        for p in (p for p in step["place"] if p["line"] in parts):  # a removed line is a step problem
            pl = bk.place(parts[p["line"]], p["at"], p.get("along", "x"), p.get("down"))
            (x, y, z), (lx, ly, h) = pl["at"], pl["dims"]
            for cell in ((i, j, m) for i in range(x, x + lx) for j in range(y, y + ly) for m in range(z, z + h)):
                if cell in seen and seen[cell] != (k, p["line"]):
                    out.append(f"step {k}: {p['line']} @{','.join(map(str, p['at']))} overlaps {seen[cell][1]} "
                               f"from step {seen[cell][0]}")
                    break
                seen[cell] = (k, p["line"])
    return list(dict.fromkeys(out))


def record(draft, ask=input) -> int:
    """Type the steps at the table: what to do, then each piece and where."""
    print(show(draft))
    print("\nOne step per layer. Pieces: \"#n @x,y,z\" (x, y studs along the table, z plates up; a brick is 3),"
          " add 'along y' or 'down -x' where needed. A blank line ends a step; a blank step stops.")
    added = 0
    while True:
        try:
            text = ask(f"\nStep {len(draft.get('steps') or []) + 1}, what to do: ").strip()
        except EOFError:
            break
        if not text:
            break
        step = {"text": " ".join(text.split()), "place": []}
        while True:
            try:
                line = ask("  piece @x,y,z: ").strip()
            except EOFError:
                line = ""
            if not line:
                break
            try:
                step["place"] += parse_pieces(line, draft)
            except ValueError as err:
                print(f"  {err}")
        if not step["place"]:
            print("  no pieces, so no step.")
            continue
        over = add_step(draft, step)
        if over:
            print("  not added: " + "; ".join(over))
            continue
        _save(draft)
        added += 1
        left = to_place(draft)
        print("  saved. " + ("Every piece is placed." if not left else "Still to place: " + "; ".join(left) + "."))
    print(f"\n{added} step{'s' * (added != 1)} added.")
    return 0


def preview(draft, path) -> Path:
    """The booklet the steps make so far, as an HTML page."""
    spec = draft_set(dict(draft, hand_check={"by": "(not yet)", "on": "(not yet)"}))
    placements, steps = [], []
    for step in spec["steps"]:
        add = []
        for p in (p for p in step["place"] if p["part"] in spec["parts"]):
            add.append(len(placements))
            placements.append(bk.place(spec["parts"][p["part"]], p["at"], p.get("along", "x"), p.get("down")))
        steps.append((step["text"], add))
    left = to_place(draft)
    book = bk.booklet(f"{draft['name']} (preview)", spec["subtitle"], placements, steps,
                      source=f"the steps recorded for {draft['id']} so far",
                      notes=["Preview from the recorded steps: compare each picture with the model."]
                      + (["Still to place: " + "; ".join(left) + "."] if left else []))
    path = Path(path)
    path.write_text(bk.render_html(book))
    return path


def main(argv=None, ask=input):
    parser = argparse.ArgumentParser(description="Hand-check a manual build's draft piece list and record its steps.")
    parser.add_argument("build", nargs="?", help="a draft's id, e.g. snappy-crab")
    parser.add_argument("--set", action="append", default=[], metavar="LINE=QTY",
                        help='e.g. "lime 1x1 round plate=2" or "#3=2" (0 removes the line)')
    parser.add_argument("--family", choices=FAMILIES, help="family for a line --set adds")
    parser.add_argument("--sure", action="append", default=[], metavar="LINE",
                        help="confirm an unsure line as read, e.g. \"medium_azure 1x2 curved slope\" or \"#4\"")
    parser.add_argument("--step", action="append", default=[], metavar="TEXT :: PIECES",
                        help='add a step, e.g. "Put the roof on. :: #3 @2,0,7 down -x; #3 @4,0,7 down +x"')
    parser.add_argument("--record", action="store_true", help="type the steps one by one as you build")
    parser.add_argument("--undo-step", action="store_true", help="drop the last step")
    parser.add_argument("--clear-steps", action="store_true", help="drop every step")
    parser.add_argument("--preview", metavar="FILE.html", help="write the booklet the steps make so far")
    parser.add_argument("--done", action="store_true", help="mark it hand-checked (needs every piece placed)")
    parser.add_argument("--by", help="who checked it (with --done)")
    parser.add_argument("--notes", default="", help="what the check found (with --done)")
    parser.add_argument("--undo", action="store_true", help="mark it a draft again (keeps the steps)")
    args = parser.parse_args(argv)

    drafts = manual_drafts()
    if not args.build:
        for d, why in checklist_order(drafts):
            steps = len(d.get("steps") or [])
            if hand_checked(d):
                state = "verified, booklet ready" if not step_problems(d) else "hand-checked, steps not complete"
            else:
                state = f"draft, {d['unsure_elements']} unsure" + (f", {steps} steps" if steps else "")
            print(f"{'*' if why else ' '} {d['id']:24} {d['elements_total']:>3} elements  {state}"
                  + (f"  (start here: {why})" if why else ""))
        return 0
    draft = drafts.get(args.build)
    if draft is None:
        print(f"no draft {args.build!r}; drafts: {', '.join(drafts)}", file=sys.stderr)
        return 2
    lines = {_line(e): e for e in draft["elements"]}
    changed = False
    for spec in args.set:
        name, _, qty = spec.rpartition("=")
        name = " ".join(name.split())
        if re.fullmatch(r"#\d+", name):
            try:
                name = resolve(name, draft)
            except ValueError as err:
                print(err, file=sys.stderr)
                return 2
        if not name or not qty.isdigit():
            print(f"--set needs LINE=QTY, got {spec!r}", file=sys.stderr)
            return 2
        if name in lines:
            if int(qty) == 0:
                draft["elements"].remove(lines.pop(name))
            else:
                lines[name].update(qty=int(qty), sure=True, doubt=None)
        else:
            color, size, *shape = name.split(" ")
            if color not in COLORS or "x" not in size or not shape or not args.family:
                print(f"new line {name!r} needs '<color> <size> <shape>' (colour from the vocabulary) and --family",
                      file=sys.stderr)
                return 2
            line = {"qty": int(qty), "family": args.family, "shape": " ".join(shape), "size": size, "color": color,
                    "sure": True, "doubt": None, "as_read": "added in the hand-check"}
            draft["elements"].append(line)
            lines[name] = line
        changed = True
    for name in args.sure:
        try:
            name = resolve(name, draft)
        except ValueError as err:
            print(err, file=sys.stderr)
            return 2
        lines[name].update(sure=True, doubt=None)
        changed = True
    if args.clear_steps or args.undo_step:
        steps = draft.get("steps") or []
        draft["steps"] = [] if args.clear_steps else steps[:-1]
        changed = True
    for spec in args.step:
        try:
            step = parse_step(spec, draft)
        except ValueError as err:
            print(err, file=sys.stderr)
            return 2
        over = add_step(draft, step)
        if over:
            print("step not added: " + "; ".join(over), file=sys.stderr)
            return 2
        changed = True
    if args.undo:
        draft["status"] = "draft"
        draft["hand_check"] = {"done": False, "on": None, "by": None, "notes": ""}
        changed = True
    if changed:
        _save(draft)
    if args.record:
        return record(draft, ask)
    if args.done:
        unsure = [_line(e) for e in draft["elements"] if not e["sure"]]
        if unsure:
            print("still unsure, confirm with --sure or fix with --set first: " + "; ".join(unsure), file=sys.stderr)
            return 1
        problems = step_problems(draft)
        if problems:
            print("the steps don't build it yet (record them with --record or --step): " + "; ".join(problems),
                  file=sys.stderr)
            return 1
        if not args.by:
            print("--done needs --by (who checked it)", file=sys.stderr)
            return 2
        draft["status"] = "hand-checked"
        draft["hand_check"] = {"done": True, "on": date.today().isoformat(), "by": args.by, "notes": args.notes}
        _save(draft)
    if args.preview:
        print(f"booklet preview: {preview(draft, args.preview)}")
    print(show(draft))
    return 0


if __name__ == "__main__":
    sys.exit(main())
