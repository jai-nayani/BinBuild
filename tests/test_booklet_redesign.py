"""Booklet redesign: the drawings must look like the book's models.

The renderer (backend/booklet.py) used to draw every piece as a studded
box, so a stingray was a rectangle and its eyes were cans. Fixed at the
function level, for every build at once:

- wedge plates: only the studded edge carries studs, and the surface falls
  away from it (the `studs=` direction now travels design -> steps ->
  booklet.place instead of being dropped);
- round tiles: flat discs with no stud, and a printed tile gets its pupil,
  so eye tiles read as eyes;
- jumper plates: the one centre stud, drawn between the two cells;
- curved slopes keep their real heights (azure 1x2: 4 plates with its stud
  on the flat end; 1x3: 3; the rest: 2).

And per build: every booklet build's draft still passes the physical
validator (manual_verify.check_design: the validator plus exactly the
book's list) and renders; the stingray's layout was rebuilt from page 20
(the wedges span the wingspan, the eyes sit on the wing roots, the tail
runs from the centre); the paintbrush keeps its verified list but has no
booklet — the book's brush lies on its side, which the validator cannot
express, so it is not booklet-ized.

No paid call anywhere: the validator and renderer are local.
Standard-library unittest. Run from the repo root:
    python3 -m unittest discover -s tests -v
"""

import unittest

from backend import booklet as bk
from backend import build_plan as bp
from backend import manual_verify as mv
from backend import wonder_design as wd
from test_full_loop import KIT_ITEMS

OWNED = wd.owned_from_items(KIT_ITEMS)
BOOKLET_IDS = [o["id"] for o in bp.options(KIT_ITEMS) if o.get("has_booklet")]


def ellipses(svg):
    return svg.count("<ellipse")


class TestRendererShapes(unittest.TestCase):
    def test_wedge_studs_only_on_the_studded_edge(self):
        wedge = bk.place({"family": "plate", "shape": "wedge plate", "size": "2x4", "color": "white"},
                         [0, 0, 0], studs="+y")
        plate = bk.place({"family": "plate", "shape": "plate", "size": "2x4", "color": "white"}, [0, 0, 0])
        # 4 studs on one long edge, not 8 all over: 2 ellipses per stud
        self.assertEqual(ellipses(bk.picture([wedge])), 8)
        self.assertEqual(ellipses(bk.picture([plate])), 16)
        self.assertEqual(wedge["down"], "-y", "the surface falls away from the studded edge")

    def test_round_tile_is_a_flat_disc_with_a_pupil(self):
        tile = bk.place({"family": "tile", "shape": "round printed tile", "size": "1x1", "color": "white"}, [0, 0, 0])
        plate = bk.place({"family": "plate", "shape": "round plate", "size": "1x1", "color": "white"}, [0, 0, 0])
        brick = bk.place({"family": "brick", "shape": "round brick", "size": "1x1", "color": "white"}, [0, 0, 0])
        self.assertEqual(ellipses(bk.picture([tile])), 3)    # the disc's 2, plus the pupil: no stud on top
        self.assertIn('fill="#26221f"', bk.picture([tile]))  # the printed eye
        self.assertEqual(ellipses(bk.picture([plate])), 4)   # disc + its stud
        self.assertEqual(ellipses(bk.picture([brick])), 4)

    def test_jumper_plate_has_one_centre_stud(self):
        jumper = bk.place({"family": "plate", "shape": "jumper plate", "size": "1x2", "color": "white"}, [0, 0, 0])
        plate = bk.place({"family": "plate", "shape": "plate", "size": "1x2", "color": "white"}, [0, 0, 0])
        self.assertEqual(ellipses(bk.picture([jumper])), 2)
        self.assertEqual(ellipses(bk.picture([plate])), 4)

    def test_curved_slope_heights(self):
        def height(size, color):
            return bk.place({"family": "slope", "shape": "curved slope", "size": size, "color": color},
                            [0, 0, 0])["dims"][2]
        self.assertEqual(height("1x2", "medium_azure"), 4)
        self.assertEqual(height("1x3", "light_bluish_gray"), 3)
        self.assertEqual(height("1x2", "black"), 2)

    def test_edge_stud_tile_studs_on_one_edge_only(self):
        tile = bk.place({"family": "tile", "shape": "tile with 2 studs on edge", "size": "2x2", "color": "white"},
                        [0, 0, 0], studs="+y")
        self.assertEqual(ellipses(bk.picture([tile])), 4)  # its 2 edge studs


class TestBookletBuilds(unittest.TestCase):
    def test_every_booklet_build_validates_and_renders(self):
        self.assertEqual(len(BOOKLET_IDS), 11)
        for bid in BOOKLET_IDS:
            with self.subTest(bid):
                book = bp.plan_set(bid, KIT_ITEMS)["booklet"]
                svg = bk.picture(book["placements"])
                self.assertTrue(svg.startswith("<svg"), bid)
                self.assertEqual(len(book["placements"]),
                                 sum(p["qty"] for p in book["parts"]), bid)
                if bid == "house-and-tree":
                    continue  # the hand-checked set, not a Wonder draft
                draft = bp.manual_drafts()[bid]
                check = mv.check_design("\n".join(draft["auto_steps"]["design"]), OWNED,
                                        mv.counts(draft["elements"]))
                self.assertTrue(check.ok, (bid, check.errors))
                # the steps place exactly the validated design, directions included
                placed = [p for step in draft["steps"] for p in step["place"]]
                self.assertEqual(len(placed), draft["elements_total"], bid)

    def test_stingray_wings_span_the_wingspan(self):
        draft = bp.manual_drafts()["stingray"]
        pieces, errors = wd.parse("\n".join(draft["auto_steps"]["design"]))
        self.assertEqual(errors, [])
        wedges = [p for p in pieces if p.code == "wedge_plate"]
        self.assertEqual([(p.w, p.direction) for p in wedges], [(4, "-x"), (4, "-x")],
                         "each wedge runs 4 long across the wingspan, studs on the head edge")
        eyes = [p for p in pieces if p.code == "round_tile"]
        self.assertEqual([(p.x, p.y, p.z) for p in eyes], [(3, 3, 3), (3, 4, 3)],
                         "the eyes sit side by side on the wing roots, at the centre")
        tail = next(p for p in pieces if p.code == "plate" and p.color == "lime")
        self.assertEqual((tail.x, tail.y), (3, 3), "the tail runs from the centre")

    def test_paintbrush_has_a_list_but_no_booklet(self):
        draft = bp.manual_drafts()["paintbrush"]
        self.assertFalse(bp.booklet_ready(draft))
        self.assertNotIn("paintbrush", BOOKLET_IDS)
        self.assertFalse(draft["auto_steps"]["ok"])
        self.assertIn("lies on its side", draft["auto_steps"]["reason"])
        option = next(o for o in bp.manual_options(KIT_ITEMS) if o["id"] == "paintbrush")
        self.assertEqual(option["piece_status"], "verified")  # the list stands
        self.assertIn("No step-by-step booklet", option["message"])


if __name__ == "__main__":
    unittest.main()
