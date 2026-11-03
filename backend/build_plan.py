"""The build step: from the confirmed inventory to a plan, and a booklet.

The build list starts with the manual that came with the kit
(backend/manual/catalog.json): every build in it is a candidate for this kit
and is listed, with its page. Only a build whose piece list has been
verified is checked against the inventory and gets a booklet: a known set
(backend/sets/), or a draft list transcribed from the book
(backend/manual/drafts/) once someone has hand-checked it against the kit
and recorded its steps while building it (python -m backend.manual_check);
those steps make its booklet. The others are shown as manual builds whose
parts are not yet verified, with no fit claim and no booklet. Then come
BrickGPT designs.

Two kinds of build can be planned:

- A known set (backend/sets/*.json, or a hand-checked manual draft with its
  recorded steps): exact pieces (family, shape, size, colour) with written
  steps. It fits when the inventory holds every piece; otherwise the missing
  pieces are named.
- A BrickGPT design through Path A (backend/brickgpt_constraint.py, used
  unchanged). Live generation is off, so plan_build draws the pre-generated
  design for a category. Only the generator-ready layer (plain bricks in the 8
  BrickGPT sizes) can be used: plates, slopes, tiles and modified bricks are
  outside BrickGPT's library. The constraint ignores colour; colours are
  assigned afterwards from the owned bricks of each size. A design that
  doesn't fit comes back as a named shortfall, never as a design.

A plan that fits carries its booklet (backend/booklet.py). One that doesn't
carries `details`: every problem as count, part and grid position
(backend/diagnostics.py). Planning only reads: nothing here touches the
database; storing a plan is the caller's separate, explicit step
(inventory_db.create_build). Standard library only.
"""

import json
import time
from collections import Counter
from pathlib import Path

from . import booklet as bk
from . import brickgpt_constraint as path_a
from . import diagnostics as dx
from . import wonder_design as wd
from .inventory_vocab import GENERATOR_TYPES

SETS_DIR = Path(__file__).resolve().parent / "sets"
MANUAL = Path(__file__).resolve().parent / "manual" / "catalog.json"
DRAFTS_DIR = MANUAL.parent / "drafts"


def _key(part) -> tuple:
    shape = " ".join((part.get("shape") or "").lower().split())
    return part["family"], shape, part.get("size"), part["color"]


def _counts_text(counts) -> str:
    return ", ".join(f"{n}× {t}" for t, n in counts.items() if n)


def generator_counts(items) -> dict:
    """Generator-ready bricks per BrickGPT type, all colours together."""
    counts = dict.fromkeys(GENERATOR_TYPES, 0)
    for item in items:
        if item.get("generator_type"):
            counts[item["generator_type"]] += item["quantity"]
    return counts


def snapshot(summary) -> dict:
    """What a build was planned against: stored with the build."""
    return {"total_pieces": summary["total_pieces"],
            "generator_ready": {t: n for t, n in generator_counts(summary["items"]).items() if n},
            "items": summary["items"]}


# --- known sets -----------------------------------------------------------------

def known_sets() -> dict:
    """The set files, plus every manual draft that is hand-checked with its
    steps recorded (as draft_set builds it)."""
    sets = (json.loads(p.read_text()) for p in sorted(SETS_DIR.glob("*.json")))
    found = {s["id"]: s for s in sets}
    for d in manual_drafts().values():
        if booklet_ready(d) and d["id"] not in found:
            found[d["id"]] = draft_set(d)
    return found


def check_pieces(needed, items) -> dict:
    """needed: [(part, count)]. Each piece against the inventory (exact
    family, shape, size and colour; a different colour is a different piece)."""
    have = Counter()
    for item in items:
        have[_key(item)] += item["quantity"]
    parts = []
    for part, n in needed:
        got = have[_key(part)]
        parts.append({"label": bk.label(part), "need": n, "have": got, "short": max(n - got, 0)})
    return {"fits": all(not p["short"] for p in parts), "parts": parts,
            "missing": [p for p in parts if p["short"]]}


def check_set(spec, items) -> dict:
    need = Counter(p["part"] for step in spec["steps"] for p in step["place"])
    return check_pieces([(spec["parts"][name], n) for name, n in need.items()], items)


def plan_set(set_id, items, with_booklet=True) -> dict:
    sets = known_sets()
    if set_id not in sets:
        raise KeyError(f"no known set {set_id!r}; sets are {', '.join(sets)}")
    return plan_spec(sets[set_id], items, with_booklet)


def set_details(spec, items) -> list:
    """Each piece the set needs beyond the inventory, with where its steps
    place every one: '1 over-count: Brick 1x2 (orange) @ Position(..), ... — needs 2, owns 1'."""
    have = Counter()
    for item in items:
        have[_key(item)] += item["quantity"]
    spots = {}
    for step in spec["steps"]:
        for p in step["place"]:
            spots.setdefault(p["part"], []).append(tuple(p["at"]))
    out = []
    for name, where in spots.items():
        part = spec["parts"][name]
        got = have[_key(part)]
        if len(where) > got:
            out.append(dx.line(len(where) - got, "over-count", dx.many(wd.part_name(_key(part)), where),
                               f"needs {len(where)}, owns {got}"))
    return out


def set_booklet(spec, notes=()) -> dict:
    """A known set's booklet (backend/booklet.py), whether or not it fits:
    the finished-model picture (booklet.picture) is the carousel card's cover."""
    placements, steps = [], []
    for step in spec["steps"]:
        add = []
        for p in step["place"]:
            add.append(len(placements))
            placements.append(bk.place(spec["parts"][p["part"]], p["at"], p.get("along", "x"), p.get("down")))
        steps.append((step["text"], add))
    manual = spec.get("manual")
    where = f"the manual, {_pages(manual.get('pages') or [manual['page']])}" if manual else f"known set: {spec['id']}"
    return bk.booklet(
        spec["title"], spec["subtitle"], placements, steps,
        source=f"the pieces in your bin ({where})",
        notes=list(notes) + spec.get("notes", []))


def plan_spec(spec, items, with_booklet=True) -> dict:
    set_id = spec["id"]
    check = check_set(spec, items)
    pieces = sum(p["need"] for p in check["parts"])
    result = {"kind": "set", "id": set_id, "title": spec["title"],
              "status": "fit" if check["fits"] else "short", "pieces": pieces,
              "parts": check["parts"], "missing": check["missing"],
              "details": [] if check["fits"] else set_details(spec, items)}
    if check["fits"]:
        result["message"] = f"You have all {pieces} pieces."
    else:
        result["message"] = "Missing " + ", ".join(f"{p['short']}× {p['label']}" for p in check["missing"]) + "."
    if check["fits"] and with_booklet:
        result["booklet"] = set_booklet(
            spec, notes=[f"Every piece checked against your confirmed inventory: {result['message']}"])
    return result


# --- BrickGPT designs through Path A -------------------------------------------------

def designs() -> list:
    """Categories that have a pre-generated design (live generation is off)."""
    return sorted(p.stem for p in path_a.DESIGNS_DIR.glob("*.txt"))


def assign_colors(design, items) -> list:
    """A colour for each brick from the owned bricks of its size. Bricks of a
    size take colours from the biggest pool first, bottom layer up, so colours
    come in bands. Path A guarantees enough bricks of each size."""
    pools = {}
    for item in items:
        if item.get("generator_type"):
            pools.setdefault(item["generator_type"], Counter())[item["color"]] += item["quantity"]
    colors = [None] * len(design)
    for kind in {b.kind for b in design}:
        order = sorted((i for i, b in enumerate(design) if b.kind == kind),
                       key=lambda i: (design[i].z, design[i].x, design[i].y))
        queue = [c for c, n in pools.get(kind, Counter()).most_common() for _ in range(n)]
        if len(queue) < len(order):
            raise ValueError(f"not enough {kind} bricks to colour the design")
        for i, color in zip(order, queue):
            colors[i] = color
    return colors


def design_booklet(category, build, items) -> dict:
    """One step per layer, bottom up."""
    colors = assign_colors(build.design, items)
    placements, layers = [], {}
    for brick, color in zip(build.design, colors):
        part = {"family": "brick", "shape": "brick", "size": brick.kind, "color": color}
        layers.setdefault(brick.z, []).append(len(placements))
        placements.append(bk.place(part, [brick.x, brick.y, brick.z * 3], along="x" if brick.h >= brick.w else "y"))
    steps = []
    for n, z in enumerate(sorted(layers), 1):
        bricks = len(layers[z])
        text = (f"Lay these {bricks} bricks flat on the table, studs up. This is the bottom layer." if n == 1
                else f"Layer {n}: press these {bricks} bricks onto the layer below.")
        steps.append((text, layers[z]))
    notes = [f"A pre-generated BrickGPT design for '{category}', checked against your bricks with Path A."]
    if build.status == "patched":
        notes.append(f"Patched to fit: {len(build.swaps)} bricks you don't have enough of were swapped "
                     "for smaller ones you do have, in the same place.")
    notes.append("Every brick touches the bricks above or below it, but nobody has built this yet: "
                 "it may wobble.")
    return bk.booklet(category.capitalize(), f"{len(build.design)} bricks, {len(steps)} layers.",
                      placements, steps, source="the bricks in your bin (BrickGPT design, Path A)", notes=notes)


def plan_design(category, items, samples=path_a.DEFAULT_SAMPLES, with_booklet=True) -> dict:
    if category not in designs():
        raise KeyError(f"no pre-generated design for {category!r} (live generation is off); "
                       f"designs are {', '.join(designs())}")
    have = generator_counts(items)
    other = sum(i["quantity"] for i in items if not i.get("generator_type"))
    started = time.perf_counter()
    result = path_a.plan_build(category, path_a.load_inventory(have), samples=samples)
    ms = round((time.perf_counter() - started) * 1000, 1)
    base = {"kind": "brickgpt", "id": category, "title": category.capitalize(),
            "generator_ready": {t: n for t, n in have.items() if n}, "other_pieces": other,
            "samples": samples, "ms": ms}
    if isinstance(result, path_a.Build):
        out = {**base, "status": result.status, "pieces": len(result.design), "attempts": result.attempts,
               "counts_before": result.counts_before, "counts_after": result.counts_after, "swaps": result.swaps,
               "details": [], "message": f"You have the bricks for this: {_counts_text(result.counts_after)}."}
        if with_booklet:
            out["booklet"] = design_booklet(category, result, items)
        return out
    disconnected = result.problem == "floating"
    out = {**base, "status": "not_connected" if disconnected else "short", "reason": result.reason,
           "details": result.details, "shortfall": result.shortfall, "still_short": result.still_short,
           "attempts": result.attempts, "short_bricks": sum(result.shortfall.values()),
           "short_studs": path_a.short_studs(result.shortfall)}
    owned = _counts_text(base["generator_ready"]) or "none"
    if disconnected:
        loose = "; ".join(d for d in result.details if " floating: " in d)
        out["message"] = f"This design has a loose part ({loose}), so it can't be built from any bin."
    else:
        out["message"] = (f"Short of {out['short_bricks']} bricks: {_counts_text(result.shortfall)}. "
                          f"Bricks BrickGPT can use in your bin: {owned}.")
    if other:
        out["message"] += (f" Your other {other} pieces (plates, slopes, tiles, bricks with studs on the side, "
                           "round bricks) are outside BrickGPT's 8 brick types.")
    return out


# --- the manual ------------------------------------------------------------------------

def manual_catalog() -> dict:
    return json.loads(MANUAL.read_text())


def manual_drafts() -> dict:
    """Draft piece lists transcribed from the book, by build id."""
    drafts = (json.loads(p.read_text()) for p in sorted(DRAFTS_DIR.glob("*.json")))
    return {d["id"]: d for d in drafts}


def hand_checked(draft) -> bool:
    return bool(draft and (draft.get("hand_check") or {}).get("done"))


def reads_agree(draft) -> bool:
    """Two independent Muse Wonder reads of the page agree on every line
    (backend/manual_verify.py)."""
    return bool(draft and (draft.get("second_read") or {}).get("agrees") is True)


def verified(draft) -> bool:
    """A draft whose list is verified: hand-checked against the kit, or two
    independent reads of the page agree on it."""
    return hand_checked(draft) or reads_agree(draft)


def line_of(e) -> str:
    """A draft line as the hand-check tool and the recorded steps name it:
    'orange 1x2 brick'."""
    return f"{e['color']} {e['size']} {e['shape']}"


def step_problems(draft) -> list:
    """Why a draft's recorded steps can't make its booklet yet: no steps, a
    step naming a line the list doesn't have, or a piece placed fewer or more
    times than the list holds. Empty once every piece is placed exactly once."""
    if not draft.get("steps"):
        return ["no steps recorded yet"]
    want = {line_of(e): e["qty"] for e in draft["elements"]}
    placed = Counter(p["line"] for step in draft["steps"] for p in step["place"])
    problems = [f"{line} is placed but isn't on the list" for line in placed if line not in want]
    for line, n in want.items():
        if placed[line] < n:
            problems.append(f"{n - placed[line]}× {line} not placed yet")
        elif placed[line] > n:
            problems.append(f"{line} placed {placed[line]} times, the list has {n}")
    return problems


def booklet_ready(draft) -> bool:
    """Verified, with steps that place every piece of its list once (recorded
    in a hand-check, or a design of the picture that passed the validator)."""
    return verified(draft) and not step_problems(draft)


def draft_set(draft) -> dict:
    """A draft as a known set (the shape of backend/sets/house-and-tree.json):
    its checked list is the parts, its recorded steps the steps."""
    hc = draft["hand_check"]
    if hand_checked(draft):
        how = [f"Piece list and steps hand-checked against the kit by {hc['by']} on {hc['on']}, "
               "building the model from the book; the drawings are BinBuild's own."]
    else:
        how = ["Piece list verified by two independent Muse Wonder reads of the page that agree on every line. "
               "Steps worked out by Muse Wonder from the book's picture and checked by BinBuild: every piece held "
               "by studs, nothing floating, no two pieces in the same space, exactly the pieces on the list; then "
               "a second, separate Wonder look compared the finished drawing with the book's picture. The "
               "drawings are BinBuild's own.",
               "Nobody has built it from these steps yet: if a step doesn't match the book, follow the book."]
    parts = {line_of(e): {k: e[k] for k in ("family", "shape", "size", "color")} for e in draft["elements"]}
    steps = [{"text": step["text"],
              "place": [{"part": p["line"], "at": p["at"], **{k: p[k] for k in ("along", "down") if p.get(k)}}
                        for p in step["place"]]}
             for step in draft["steps"]]
    pieces = sum(e["qty"] for e in draft["elements"])
    return {"id": draft["id"], "title": draft["name"],
            "subtitle": f"From the manual, {_pages(draft['pages'])}. {pieces} pieces, {len(steps)} steps.",
            "manual": {"page": draft["pages"][0], "pages": draft["pages"]},
            "notes": how, "parts": parts, "steps": steps}


CLOSEST = {"total": "its list matches the total the page prints", "sure": "no unsure lines"}


def checklist_order(drafts) -> list:
    """The drafts still waiting for a person, in the order to hand-check them,
    as [(draft, why first or None)]. Verified drafts (two reads agree, or
    hand-checked with steps) aren't in it. The closest first (Wonder's lists
    that match the element total the page prints, then the lists transcribed
    from the book with no unsure line), then the rest in book order;
    hand-checked ones still waiting for steps last."""
    def why(d):
        if (d.get("count_check") or {}).get("matches"):
            return "total"
        if not d.get("read_by") and not d["unsure_elements"]:
            return "sure"
        return None
    rank = {"total": 0, "sure": 1, None: 2}
    book = {b["id"]: n for n, b in enumerate(manual_catalog()["builds"])}
    waiting = [d for d in drafts.values() if not reads_agree(d) and not booklet_ready(d)]
    ordered = sorted(waiting, key=lambda d: (hand_checked(d), rank[why(d)], book.get(d["id"], len(book))))
    return [(d, None if hand_checked(d) else CLOSEST.get(why(d))) for d in ordered]


VERIFIED_BY = {True: "hand-checked against the kit", False: "two independent reads agree"}


def _pages(pages) -> str:
    pages = sorted(set(pages))
    return f"page {pages[0]}" if len(pages) == 1 else "pages " + ", ".join(str(p) for p in pages)


def manual_options(items) -> list:
    """Every build in the manual, in book order with verified builds first.
    A verified build with steps (a set file, or a verified draft whose steps
    place its whole list) is planned against the inventory like any known set,
    so it can get a booklet. A verified draft without steps (two reads agree,
    but no design of its picture passed the validator) gets the bin check and
    says why there is no booklet. Every other build is listed as it is, with
    its piece list marked not yet verified: no fit claim, no booklet."""
    catalog = manual_catalog()
    drafts = manual_drafts()
    chapters = {c["n"]: c["title"] for c in catalog["chapters"]}
    out = []
    for b in catalog["builds"]:
        entry = {"kind": "manual", "id": b["id"], "title": b["name"], "chapter": b["chapter"],
                 "chapter_title": chapters[b["chapter"]], "pages": b["pages"], "where": _pages(b["pages"]),
                 "piece_status": b["status"], "manual_kind": b["kind"], "has_booklet": False}
        for key in ("stated_elements", "activity", "note"):
            if key in b:
                entry[key] = b[key]
        draft = drafts.get(b["id"])
        if b["status"] == "verified" and b.get("set"):
            plan = plan_set(b["set"], items, with_booklet=False)
            entry.update(set=b["set"], status=plan["status"], message=plan["message"], missing=plan["missing"],
                         pieces=plan["pieces"], has_booklet=True, verified_by="known set with steps",
                         cover=bk.picture(set_booklet(known_sets()[b["set"]])["placements"]))
        elif booklet_ready(draft):
            spec = draft_set(draft)
            plan = plan_spec(spec, items, with_booklet=False)
            entry.update(set=b["id"], piece_status="verified", status=plan["status"], message=plan["message"],
                         missing=plan["missing"], pieces=plan["pieces"], has_booklet=True,
                         verified_by=VERIFIED_BY[hand_checked(draft)],
                         cover=bk.picture(set_booklet(spec)["placements"]))
        elif reads_agree(draft):
            check = check_pieces([({k: e[k] for k in ("family", "shape", "size", "color")}, e["qty"])
                                  for e in draft["elements"]], items)
            pieces = sum(p["need"] for p in check["parts"])
            fit = (f"You have all {pieces} pieces." if check["fits"] else
                   "Missing " + ", ".join(f"{p['short']}× {p['label']}" for p in check["missing"]) + ".")
            why = (draft.get("auto_steps") or {}).get("reason") or "its steps haven't been worked out yet"
            entry.update(piece_status="verified", status="fit" if check["fits"] else "short", missing=check["missing"],
                         pieces=pieces, verified_by=VERIFIED_BY[False], no_booklet=why,
                         message=f"{fit} No step-by-step booklet: {why}. Build it from the book, {_pages(b['pages'])}.")
        else:
            entry["status"] = "unverified"
            told = (f" The page says it uses {b['stated_elements']} elements; which ones isn't listed."
                    if "stated_elements" in b else "")
            how = (" Its draft list is hand-checked; its steps aren't recorded yet." if hand_checked(draft)
                   else " A draft list read from the book is waiting for a hand-check against the kit."
                   if draft else " The page shows the elements it needs; checking them against your kit would "
                                 "verify it." if b["status"] == "diagram-readable" else "")
            if draft:
                entry["draft"] = "hand-checked, waiting for its steps" if hand_checked(draft) else "waiting for a hand-check"
            entry["message"] = ("A build from the manual that came with your kit. Its parts aren't verified yet, so "
                                "BinBuild can't check your bin for it or make a booklet: build it from the book."
                                + told + how)
        out.append(entry)
    return sorted(out, key=lambda e: e["piece_status"] != "verified")  # stable: book order otherwise


# --- everything you could build ---------------------------------------------------------

RANK = {"fit": 0, "patched": 0, "short": 1, "not_connected": 2}


def plan(request, items, with_booklet=True) -> dict:
    """request: {"set": id} or {"design": category}. Reads only: storing the
    plan is a separate call (inventory_db.create_build)."""
    if request.get("set"):
        return plan_set(request["set"], items, with_booklet)
    if request.get("design"):
        return plan_design(request["design"], items, samples=request.get("samples", path_a.DEFAULT_SAMPLES),
                           with_booklet=with_booklet)
    raise KeyError("ask for a known set ('set') or a BrickGPT design ('design')")


def options(items) -> list:
    """Manual builds first (verified first, then the rest in book order),
    then known sets the manual doesn't list, then the pre-generated BrickGPT
    designs: buildable first, then the closest shortfalls, designs with a
    loose part last."""
    manual = manual_options(items)
    in_manual = {e.get("set") for e in manual}
    extra = [plan_set(s, items, with_booklet=False) for s in known_sets() if s not in in_manual]
    designs_ = [plan_design(d, items, with_booklet=False) for d in designs()]
    return manual + extra + sorted(designs_, key=lambda f: (RANK[f["status"]], f.get("short_studs", 0)))
