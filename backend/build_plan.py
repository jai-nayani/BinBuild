"""The build step: from the confirmed inventory to a plan, and a booklet.

The build list starts with the manual that came with the kit
(backend/manual/catalog.json): every build in it is a candidate for this kit
and is listed, with its page. Only a build whose piece list has been
verified is checked against the inventory: a known set (with steps, so it
also gets a booklet), or a draft list transcribed from the book
(backend/manual/drafts/) once someone has hand-checked it against the kit
(no booklet: it is built from the book). The others are shown as manual
builds whose parts are not yet verified, with no fit claim and no booklet.
Then come BrickGPT designs.

Two kinds of build can be planned:

- A known set (backend/sets/*.json): exact pieces (family, shape, size,
  colour) with written steps. It fits when the inventory holds every piece;
  otherwise the missing pieces are named.
- A BrickGPT design through Path A (backend/brickgpt_constraint.py, used
  unchanged). Live generation is off, so plan_build draws the pre-generated
  design for a category. Only the generator-ready layer (plain bricks in the 8
  BrickGPT sizes) can be used: plates, slopes, tiles and modified bricks are
  outside BrickGPT's library. The constraint ignores colour; colours are
  assigned afterwards from the owned bricks of each size. A design that
  doesn't fit comes back as a named shortfall, never as a design.

A plan that fits carries its booklet (backend/booklet.py). Standard library
only.
"""

import json
import time
from collections import Counter
from pathlib import Path

from . import booklet as bk
from . import brickgpt_constraint as path_a
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
    sets = (json.loads(p.read_text()) for p in sorted(SETS_DIR.glob("*.json")))
    return {s["id"]: s for s in sets}


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
    spec = sets[set_id]
    check = check_set(spec, items)
    pieces = sum(p["need"] for p in check["parts"])
    result = {"kind": "set", "id": set_id, "title": spec["title"],
              "status": "fit" if check["fits"] else "short", "pieces": pieces,
              "parts": check["parts"], "missing": check["missing"]}
    if check["fits"]:
        result["message"] = f"You have all {pieces} pieces."
    else:
        result["message"] = "Missing " + ", ".join(f"{p['short']}× {p['label']}" for p in check["missing"]) + "."
    if check["fits"] and with_booklet:
        placements, steps = [], []
        for step in spec["steps"]:
            add = []
            for p in step["place"]:
                add.append(len(placements))
                placements.append(bk.place(spec["parts"][p["part"]], p["at"], p.get("along", "x"), p.get("down")))
            steps.append((step["text"], add))
        where = f"the manual, page {spec['manual']['page']}" if spec.get("manual") else f"known set: {set_id}"
        result["booklet"] = bk.booklet(
            spec["title"], spec["subtitle"], placements, steps,
            source=f"the pieces in your bin ({where})",
            notes=[f"Every piece checked against your confirmed inventory: {result['message']}"])
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
               "message": f"You have the bricks for this: {_counts_text(result.counts_after)}."}
        if with_booklet:
            out["booklet"] = design_booklet(category, result, items)
        return out
    disconnected = result.reason.startswith("not connected")
    out = {**base, "status": "not_connected" if disconnected else "short", "reason": result.reason,
           "shortfall": result.shortfall, "still_short": result.still_short, "attempts": result.attempts,
           "short_bricks": sum(result.shortfall.values()), "short_studs": path_a.short_studs(result.shortfall)}
    owned = _counts_text(base["generator_ready"]) or "none"
    if disconnected:
        out["message"] = f"This design has a loose part ({result.reason}), so it can't be built from any bin."
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


def _fit_message(check, pieces) -> str:
    if check["fits"]:
        return f"You have all {pieces} pieces."
    return "Missing " + ", ".join(f"{p['short']}× {p['label']}" for p in check["missing"]) + "."


def _pages(pages) -> str:
    pages = sorted(set(pages))
    return f"page {pages[0]}" if len(pages) == 1 else "pages " + ", ".join(str(p) for p in pages)


def manual_options(items) -> list:
    """Every build in the manual, in book order with verified builds first.
    A verified build (one with a known set) is planned against the inventory
    like any known set; every other build is listed as it is, with its piece
    list marked not yet verified: no fit claim, no booklet."""
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
                         pieces=plan["pieces"], has_booklet=True, verified_by="known set with steps")
        elif hand_checked(draft):
            needed = [({k: e[k] for k in ("family", "shape", "size", "color")}, e["qty"]) for e in draft["elements"]]
            check = check_pieces(needed, items)
            pieces = sum(n for _, n in needed)
            entry.update(piece_status="verified", status="fit" if check["fits"] else "short",
                         missing=check["missing"], pieces=pieces, verified_by="hand-checked against the kit",
                         message=_fit_message(check, pieces) + f" Build it from the book: {_pages(b['pages'])}.")
        else:
            entry["status"] = "unverified"
            told = (f" The page says it uses {b['stated_elements']} elements; which ones isn't listed."
                    if "stated_elements" in b else "")
            how = (" A draft list read from the book is waiting for a hand-check against the kit."
                   if draft else " The page shows the elements it needs; checking them against your kit would "
                                 "verify it." if b["status"] == "diagram-readable" else "")
            if draft:
                entry["draft"] = "waiting for a hand-check"
            entry["message"] = ("A build from the manual that came with your kit. Its parts aren't verified yet, so "
                                "BinBuild can't check your bin for it or make a booklet: build it from the book."
                                + told + how)
        out.append(entry)
    return sorted(out, key=lambda e: e["piece_status"] != "verified")  # stable: book order otherwise


# --- everything you could build ---------------------------------------------------------

RANK = {"fit": 0, "patched": 0, "short": 1, "not_connected": 2}


def plan(request, items) -> dict:
    """request: {"set": id} or {"design": category}."""
    if request.get("set"):
        return plan_set(request["set"], items)
    if request.get("design"):
        return plan_design(request["design"], items, samples=request.get("samples", path_a.DEFAULT_SAMPLES))
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
