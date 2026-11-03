"""Booklet redesign: the drawings must look like the book's models.

The booklet pictures are drawn from the parts' real shapes: the LDraw meshes
of the kit's parts (backend/ldraw_kit.json.gz, built by backend/ldraw_mesh.py
from the LDraw library) placed on the booklet grid and z-buffered by
backend/ldraw_render.py, at the angle the book shows each model. So a wedge
plate is a wedge, a curved slope has its curve, an eye tile has its printed
eye, and a piece pressed onto a stud hides it.

Per build: every booklet build's draft still passes the physical validator
(manual_verify.check_design: the validator plus exactly the book's list) and
renders; the stingray and radar layouts were rebuilt from their pages; the
paintbrush keeps its verified list but has no booklet (the book's brush lies
on its side, which the validator cannot express); the two cakes' pictures
show pieces their lists don't have, so those lists are no longer verified.

No paid call anywhere: the validator and renderer are local.
Standard-library unittest. Run from the repo root:
    python3 -m unittest discover -s tests -v
"""

import base64
import io
import re
import unittest

import numpy as np
from PIL import Image

from backend import booklet as bk
from backend import build_plan as bp
from backend import ldraw_mesh
from backend import ldraw_render as lr
from backend import manual_verify as mv
from backend import wonder_design as wd
from test_full_loop import KIT_ITEMS

OWNED = wd.owned_from_items(KIT_ITEMS)
BOOKLET_IDS = [o["id"] for o in bp.options(KIT_ITEMS) if o.get("has_booklet")]
TOP = {"yaw": 0, "elevation": 89}


def piece(family, shape, size, color, at=(0, 0, 0), **kw):
    return bk.place({"family": family, "shape": shape, "size": size, "color": color}, list(at), **kw)


def pixels(img):
    return np.asarray(img).astype(int)


def solid(img):
    return pixels(img)[..., 3] > 127


class TestRendererShapes(unittest.TestCase):
    def test_every_kit_part_has_its_ldraw_shape(self):
        meshes = lr.meshes()
        for name in ldraw_mesh.PARTS:
            self.assertIn(name, meshes)
        for shape, family, size, color, number in (
                ("plate", "plate", "1x6", "lime", "3666"), ("wedge plate", "plate", "2x4", "white", "41769a"),
                ("round printed tile", "tile", "1x1", "white", "98138p07"),
                ("round tile", "tile", "1x1", "white", "98138"),
                ("curved slope", "slope", "1x2", "black", "11477"),
                ("jumper plate", "plate", "1x2", "white", "3794b"),
                ("round brick", "brick", "1x1", "light_bluish_gray", "3062b"),
                ("plate with clip", "plate", "1x2", "lime", "63868"),
                ("headlight brick", "brick", "1x1", "light_bluish_gray", "4070")):
            with self.subTest(shape):
                number_for = lr.ldraw_number({"family": family, "shape": shape, "size": size, "color": color})
                self.assertEqual(number_for, number)
                self.assertIn(number, meshes)

    def test_wedge_plate_is_a_wedge(self):
        wedge = piece("plate", "wedge plate", "2x4", "white", studs="+y")
        plate = piece("plate", "plate", "2x4", "white")
        frame = lr.bounds([plate], TOP)
        ratio = solid(lr.render([wedge], frame=frame, view=TOP)).sum() / solid(lr.render([plate], frame=frame, view=TOP)).sum()
        self.assertTrue(0.65 < ratio < 0.85, ratio)   # a 2x4 with a 4x1 triangle cut off: 3/4
        self.assertEqual(wedge["down"], "-y", "the surface falls away from the studded edge")

    def test_eye_tile_has_its_printed_eye(self):
        def dark(shape):
            a = pixels(lr.render([piece("tile", shape, "1x1", "white")], view=TOP))
            return ((a[..., :3].max(-1) < 70) & (a[..., 3] > 200)).sum() / (a[..., 3] > 200).sum()
        self.assertGreater(dark("round printed tile"), 0.15)
        self.assertLess(dark("round tile"), 0.01)

    def test_directions_turn_the_part(self):
        side = {"yaw": 0, "elevation": 20}   # screen right is +x
        for kw, other in (({"down": "+x"}, {"down": "-x"}),):
            a = solid(lr.render([piece("slope", "curved slope", "1x2", "black", **kw)], view=side))
            b = solid(lr.render([piece("slope", "curved slope", "1x2", "black", **other)], view=side))
            self.assertEqual(a.shape, b.shape)
            self.assertGreater((a != b).sum(), 0.3 * a.sum(), "a curved slope isn't symmetric")
            self.assertLess((np.fliplr(a) != b).sum(), 0.05 * a.sum(), "falling the other way mirrors it")

    def test_curved_slope_heights(self):
        def height(size, color):
            return piece("slope", "curved slope", size, color)["dims"][2]
        self.assertEqual(height("1x2", "medium_azure"), 4)
        self.assertEqual(height("1x3", "light_bluish_gray"), 3)
        self.assertEqual(height("1x2", "black"), 2)

    def test_picture_is_an_embedded_png(self):
        svg = bk.picture([piece("plate", "plate", "2x4", "lime")])
        self.assertTrue(svg.startswith("<svg"))
        found = re.search(r'href="data:image/png;base64,([^"]+)"', svg)
        img = Image.open(io.BytesIO(base64.b64decode(found.group(1))))
        self.assertEqual(img.format, "PNG")
        self.assertGreater(solid(img.convert("RGBA")).sum(), 1000)


class TestBookletBuilds(unittest.TestCase):
    def test_every_booklet_build_validates_and_renders(self):
        self.assertEqual(len(BOOKLET_IDS), 9)
        for bid in BOOKLET_IDS:
            with self.subTest(bid):
                book = bp.plan_set(bid, KIT_ITEMS)["booklet"]
                svg = bk.cover(book)
                self.assertTrue(svg.startswith("<svg") and "data:image/png;base64," in svg, bid)
                self.assertEqual(len(book["placements"]),
                                 sum(p["qty"] for p in book["parts"]), bid)
                if bid == "house-and-tree":
                    continue  # the hand-checked set, not a Wonder draft
                draft = bp.manual_drafts()[bid]
                check = mv.check_design("\n".join(draft["auto_steps"]["design"]), OWNED,
                                        mv.counts(draft["elements"]))
                self.assertTrue(check.ok, (bid, check.errors))
                # the steps place exactly the validated design, directions included
                self.assertEqual(draft["steps"], mv.layer_steps(check.pieces), bid)

    def test_each_build_is_drawn_at_the_books_angle(self):
        for bid in BOOKLET_IDS:
            with self.subTest(bid):
                book = bp.plan_set(bid, KIT_ITEMS)["booklet"]
                self.assertIn("view", book, "the angle the book shows the model at")
                self.assertTrue(0 <= book["view"]["yaw"] < 360 and 0 < book["view"]["elevation"] < 90)

    def test_stingray_wings_span_the_wingspan(self):
        draft = bp.manual_drafts()["stingray"]
        pieces, errors = wd.parse("\n".join(draft["auto_steps"]["design"]))
        self.assertEqual(errors, [])
        wedges = [p for p in pieces if p.code == "wedge_plate"]
        self.assertEqual([(p.w, p.direction) for p in wedges], [(4, "-x"), (4, "-x")],
                         "each wedge runs 4 long across the wingspan, studs on the head edge")
        self.assertEqual(sorted(p.y for p in wedges), [0, 4], "one wing each side of the body")
        eyes = [p for p in pieces if p.code == "round_tile"]
        self.assertEqual([(p.x, p.y, p.z) for p in eyes], [(1, 3, 2), (1, 4, 2)],
                         "the eyes sit side by side on the body, at the head end")
        tail = next(p for p in pieces if p.code == "plate" and p.color == "lime")
        self.assertEqual((tail.x, tail.y), (3, 3), "the tail runs from the centre")

    def test_radar_dish_covers_the_mast_end(self):
        draft = bp.manual_drafts()["radar-dish-station"]
        pieces, errors = wd.parse("\n".join(draft["auto_steps"]["design"]))
        self.assertEqual(errors, [])
        mast = next(p for p in pieces if p.color == "lime")
        above = {c[:2] for p in pieces if p.z == mast.z + 1 for c in p.cells()}
        shown = [c for c in mast.cells() if c[:2] not in above]
        self.assertEqual(len(shown), 4, "4 of the mast's studs show between the dish and the base, as on page 78")

    def test_paintbrush_has_a_list_but_no_booklet(self):
        draft = bp.manual_drafts()["paintbrush"]
        self.assertFalse(bp.booklet_ready(draft))
        self.assertNotIn("paintbrush", BOOKLET_IDS)
        self.assertFalse(draft["auto_steps"]["ok"])
        self.assertIn("lies on its side", draft["auto_steps"]["reason"])
        option = next(o for o in bp.manual_options(KIT_ITEMS) if o["id"] == "paintbrush")
        self.assertEqual(option["piece_status"], "verified")  # the list stands
        self.assertIn("No step-by-step booklet", option["message"])

    def test_cakes_whose_pictures_dispute_their_lists_have_no_booklet(self):
        for bid in ("birthday-cake-message", "blueberry-cake"):
            with self.subTest(bid):
                draft = bp.manual_drafts()[bid]
                self.assertIs(draft["picture_check"]["agrees"], False)
                self.assertFalse(bp.booklet_ready(draft))
                self.assertNotIn(bid, BOOKLET_IDS)
                page = bk.render_checklist([draft])
                self.assertIn("The page's picture disagrees with this list", page)


if __name__ == "__main__":
    unittest.main()
