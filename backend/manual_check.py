"""Hand-check a draft piece list from the manual against the kit.

A draft (backend/manual/drafts/<id>.json) is the "Elements you'll need" box
of a manual build, transcribed from a photo of the book. It is not a
verified piece list until a person has laid those pieces out from the kit
next to the page and built the model once. This tool shows the checklist,
records corrections, and marks the draft hand-checked; from then on "What
can I build?" checks a bin against it (still no booklet: the build is made
from the book).

From the repo root:
    python -m backend.manual_check                       # every draft and its state
    python -m backend.manual_check dozy-dolphin          # its checklist, doubts first
    python -m backend.manual_check dozy-dolphin --set "medium_blue 1x1 1x1 slope (cheese)=1" ...
    python -m backend.manual_check dozy-dolphin --done --by Jai --notes "built it, all there"
    python -m backend.manual_check dozy-dolphin --undo   # back to draft

--set "<color> <size> <shape>=<qty>" changes a line's quantity (0 removes
it) or adds a line; give --family for a new line. A draft can only be marked
done when no line is still marked unsure: confirm each one with --sure, or
fix it with --set.
Standard library only.
"""

import argparse
import json
import sys
from datetime import date

from .build_plan import DRAFTS_DIR, manual_drafts
from .inventory_vocab import COLORS, FAMILIES


def _line(e) -> str:
    return f"{e['color']} {e['size']} {e['shape']}"


def _save(draft):
    draft["elements_total"] = sum(e["qty"] for e in draft["elements"])
    draft["unsure_elements"] = sum(e["qty"] for e in draft["elements"] if not e["sure"])
    (DRAFTS_DIR / f"{draft['id']}.json").write_text(json.dumps(draft, indent=1, ensure_ascii=False) + "\n")


def show(draft) -> str:
    state = "HAND-CHECKED" if draft["hand_check"]["done"] else "DRAFT (not verified)"
    out = [f"{draft['name']} ({draft['id']}) · pages {', '.join(map(str, draft['pages']))} · {state}",
           f"Read from {draft['read_from']}.",
           f"{draft['elements_total']} elements, {draft['unsure_elements']} unsure.", ""]
    for e in sorted(draft["elements"], key=lambda e: e["sure"]):
        mark = "?" if not e["sure"] else " "
        doubt = f"   <- unsure: {e['doubt']}" if not e["sure"] else ""
        out.append(f" [{mark}] {e['qty']:>2}× {_line(e)}{doubt}")
    if draft["hand_check"]["done"]:
        hc = draft["hand_check"]
        out += ["", f"Hand-checked on {hc['on']} by {hc['by']}." + (f" Notes: {hc['notes']}" if hc["notes"] else "")]
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Hand-check a manual build's draft piece list.")
    parser.add_argument("build", nargs="?", help="a draft's id, e.g. dozy-dolphin")
    parser.add_argument("--set", action="append", default=[], metavar="LINE=QTY",
                        help='e.g. "lime 1x1 round plate=2" (0 removes the line)')
    parser.add_argument("--family", choices=FAMILIES, help="family for a line --set adds")
    parser.add_argument("--sure", action="append", default=[], metavar="LINE",
                        help="confirm an unsure line as read, e.g. \"medium_azure 1x2 curved slope\"")
    parser.add_argument("--done", action="store_true", help="mark the draft hand-checked")
    parser.add_argument("--by", help="who checked it (with --done)")
    parser.add_argument("--notes", default="", help="what the check found (with --done)")
    parser.add_argument("--undo", action="store_true", help="mark it a draft again")
    args = parser.parse_args(argv)

    drafts = manual_drafts()
    if not args.build:
        for d in drafts.values():
            state = "hand-checked" if d["hand_check"]["done"] else f"draft, {d['unsure_elements']} unsure"
            print(f"{d['id']:22} {d['elements_total']:>3} elements  {state}")
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
        name = " ".join(name.split())
        if name not in lines:
            print(f"no line {name!r} in {args.build}", file=sys.stderr)
            return 2
        lines[name].update(sure=True, doubt=None)
        changed = True
    if args.undo:
        draft["status"] = "draft"
        draft["hand_check"] = {"done": False, "on": None, "by": None, "notes": ""}
        changed = True
    if args.done:
        unsure = [_line(e) for e in draft["elements"] if not e["sure"]]
        if unsure:
            print("still unsure, confirm with --sure or fix with --set first: " + "; ".join(unsure), file=sys.stderr)
            return 1
        if not args.by:
            print("--done needs --by (who checked it)", file=sys.stderr)
            return 2
        draft["status"] = "hand-checked"
        draft["hand_check"] = {"done": True, "on": date.today().isoformat(), "by": args.by, "notes": args.notes}
        changed = True
    if changed:
        _save(draft)
    print(show(draft))
    return 0


if __name__ == "__main__":
    sys.exit(main())
