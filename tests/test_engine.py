"""What could go wrong at the demo, as tests. python -m unittest"""
import io
import unittest

import cv2
import numpy as np
from PIL import Image

from bench import synth
from boardcheck.decide import Model
from boardcheck.imaging import BadPhoto, load_image
from boardcheck.pipeline import Reference, check_photo, visibility
from boardcheck.suggest import suggest_box


def parts_of(board):
    return [dict(id=p.name, name=p.name, x=p.x, y=p.y, w=p.w, h=p.h) for p in board.parts]


class Engine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = Model.load()
        cls.board = synth.make_board(42, mask="green", density=.9)
        cls.good = synth.render(cls.board)
        cls.ref = Reference(cls.good, parts_of(cls.board))
        cls.gone = [cls.board.parts[0].name, cls.board.parts[-1].name]
        cls.bad = synth.render(cls.board, cls.gone)

    def verdict(self, photo, ref=None):
        r = check_photo(ref or self.ref, photo, self.model)
        return r, {p.name for p in r.parts if p.verdict == "missing"}

    def assertOk(self, photo, ref=None):
        r, missing = self.verdict(photo, ref)
        self.assertEqual((r.status, missing), ("ok", set()), (r.method, r.quality))

    def assertGone(self, photo, names=None, ref=None):
        r, missing = self.verdict(photo, ref)
        self.assertEqual(missing, set(names or self.gone), (r.method, r.quality))

    def test_same_photo_is_ok(self):
        self.assertOk(self.good)

    def test_missing_parts_are_named(self):
        self.assertGone(self.bad)

    def test_marked_place_is_where_the_part_was(self):
        photo, H = synth.capture(self.bad, synth.LEVELS["line"], 3)
        r, _ = self.verdict(photo)
        p = self.board.parts[0]
        want = cv2.perspectiveTransform(np.float32([[[p.x, p.y], [p.x + p.w, p.y + p.h]]]), H)[0]
        got = next(q.quad for q in r.parts if q.name == p.name)
        self.assertLess(np.abs(np.array([got[0], got[2]]) - want).max(), 3)

    def test_every_part_missing(self):
        everything = [p.name for p in self.board.parts]
        r, missing = self.verdict(synth.render(self.board, everything))
        self.assertGreaterEqual(len(missing), .85 * len(everything))
        self.assertFalse([p.name for p in r.parts if p.verdict == "present"])

    def test_other_resolutions(self):
        for s in (.5, .75, 1.6):
            self.assertOk(cv2.resize(self.good, None, fx=s, fy=s, interpolation=cv2.INTER_AREA))
            self.assertGone(cv2.resize(self.bad, None, fx=s, fy=s, interpolation=cv2.INTER_AREA))

    def test_turned_photos(self):
        for turn in (cv2.ROTATE_180, cv2.ROTATE_90_CLOCKWISE):
            self.assertOk(cv2.rotate(self.good, turn))
            self.assertGone(cv2.rotate(self.bad, turn))

    def test_cropped_photo(self):
        self.assertOk(self.good[12:-12, 16:-16])

    def test_stretched_photo(self):
        self.assertOk(cv2.resize(self.good, (1280, 1000)))

    def test_darker_and_brighter(self):
        for a, b in ((.6, 0), (1.25, 8)):
            self.assertOk(cv2.convertScaleAbs(self.good, alpha=a, beta=b))
            self.assertGone(cv2.convertScaleAbs(self.bad, alpha=a, beta=b))

    def test_colour_cast(self):
        warm = np.clip(self.bad * np.array([.82, 1, 1.12]), 0, 255).astype(np.uint8)
        self.assertGone(warm)

    def test_changed_chip_markings_are_not_missing(self):
        self.assertOk(synth.render(self.board, text_seed=777))

    def test_board_moved_on_a_patterned_table(self):
        """The table stays still and the board does not. Follow the board."""
        r = np.random.default_rng(1)
        table = cv2.resize(r.integers(0, 255, (120, 160, 3), dtype=np.uint8), (1600, 1200), interpolation=cv2.INTER_NEAREST)
        def scene(img, dx, dy):
            t = table.copy()
            t[130 + dy:130 + dy + 916, 180 + dx:180 + dx + 1236] = img[22:-22, 22:-22]
            return t
        parts = [dict(p, x=p["x"] + 158, y=p["y"] + 108) for p in parts_of(self.board)]
        ref = Reference(scene(self.good, 0, 0), parts)
        self.assertOk(scene(self.good, 34, 21), ref)
        self.assertGone(scene(self.bad, 34, 21), ref=ref)

    def test_plain_board_with_three_parts(self):
        def scene(gone=()):
            img = np.full((800, 1000, 3), (60, 110, 40), np.uint8)
            for n, (x, y, w, h, c) in {"A": (150, 150, 120, 80, (30, 30, 30)), "B": (600, 200, 60, 160, (190, 190, 190)),
                                       "C": (400, 560, 90, 90, (40, 60, 180))}.items():
                if n not in gone:
                    cv2.rectangle(img, (x, y), (x + w, y + h), c, -1)
                    cv2.rectangle(img, (x + 8, y + 8), (x + w - 8, y + h - 8), tuple(v + 25 for v in c), 2)
            return img
        parts = [dict(id=n, name=n, x=x - 3, y=y - 3, w=w + 6, h=h + 6) for n, x, y, w, h in
                 (("A", 150, 150, 120, 80), ("B", 600, 200, 60, 160), ("C", 400, 560, 90, 90))]
        ref = Reference(scene(), parts)
        self.assertOk(scene(), ref)
        self.assertGone(scene(("B",)), ["B"], ref)
        self.assertGone(scene(("A", "C")), ["A", "C"], ref)

    def test_identical_neighbour_does_not_stand_in(self):
        """Two equal resistors side by side: losing one must not be hidden by the other."""
        def scene(gone=()):
            img = synth.render(self.board)
            for i, x in enumerate((300, 326)):
                cv2.rectangle(img, (x - 2, 498), (x + 20, 542), (60, 104, 30), -1)
                if i not in gone:
                    cv2.rectangle(img, (x, 500), (x + 18, 540), (180, 188, 190), -1)
                    cv2.rectangle(img, (x, 508), (x + 18, 532), (34, 34, 34), -1)
            return img
        parts = [dict(id=n, name=n, x=x, y=500, w=18, h=40) for n, x in (("Ra", 300), ("Rb", 326))]
        ref = Reference(scene(), parts)
        self.assertGone(scene((0,)), ["Ra"], ref)
        self.assertGone(scene((1,)), ["Rb"], ref)

    def test_wrong_board_is_refused(self):
        other = synth.render(synth.make_board(4242, mask="green"))
        self.assertEqual(self.verdict(other)[0].status, "unreadable")

    def test_unrelated_photos_are_refused(self):
        r = np.random.default_rng(0)
        for img in (np.zeros((600, 800, 3), np.uint8), np.full((600, 800, 3), 255, np.uint8),
                    r.integers(0, 255, (600, 800, 3), dtype=np.uint8)):
            self.assertEqual(self.verdict(img)[0].status, "unreadable")

    def test_part_out_of_frame_is_not_called_ok(self):
        p = max(self.board.parts, key=lambda q: q.x + q.w)
        r, _ = self.verdict(self.good[:, : p.x - 4])
        got = {q.name: q.verdict for q in r.parts}
        self.assertNotEqual(got.get(p.name), "present")

    def test_invisible_part_is_reported_while_naming(self):
        img = self.good.copy()
        p = self.board.parts[0]
        empty = dict(id="ghost", name="ghost", x=700, y=40, w=30, h=20)
        img[30:70, 690:740] = (62, 104, 28)
        ref = Reference(img, [dict(id="a", name="a", x=p.x, y=p.y, w=p.w, h=p.h), empty])
        self.assertEqual(visibility(ref, self.model)[1], "hard")

    def test_parts_on_the_edge_and_tiny_boxes(self):
        ref = Reference(self.good, [dict(id="e", name="e", x=0, y=0, w=90, h=70), dict(id="t", name="t", x=640, y=480, w=4, h=4)])
        self.assertIn(check_photo(ref, self.good, self.model).status, ("ok", "check"))


class Click(unittest.TestCase):
    def test_one_click_finds_the_box(self):
        hits, total, ious = 0, 0, []
        for seed in (801, 802, 803, 804, 805, 806):
            b = synth.make_board(seed)
            img = synth.render(b)
            for p in b.parts:
                got = suggest_box(img, p.x + p.w / 2, p.y + p.h / 2)
                total += 1
                if got is None:
                    continue
                x, y, w, h = got
                ix = max(0, min(x + w, p.x + p.w) - max(x, p.x)) * max(0, min(y + h, p.y + p.h) - max(y, p.y))
                iou = ix / (w * h + p.w * p.h - ix)
                ious.append(iou)
                hits += iou > .6
        print(f"\n  click-to-box: {hits}/{total} boxes with IoU > 0.6, median IoU {np.median(ious):.2f}")
        self.assertGreater(hits / total, .85)


class Files(unittest.TestCase):
    def png(self, mode, size=(200, 150)):
        f = io.BytesIO()
        Image.new(mode, size, 120).save(f, "PNG")
        return f.getvalue()

    def test_formats(self):
        for mode in ("L", "P", "RGB", "RGBA", "LA", "1", "I;16"):
            self.assertEqual(load_image(self.png(mode)).shape, (150, 200, 3), mode)

    def test_phone_rotation_tag_is_applied(self):
        im = Image.new("RGB", (300, 200), "red")
        ex = im.getexif()
        ex[0x0112] = 6
        f = io.BytesIO()
        im.save(f, "JPEG", exif=ex)
        self.assertEqual(load_image(f.getvalue()).shape[:2], (300, 200))

    def test_heic(self):
        f = io.BytesIO()
        Image.new("RGB", (200, 150), "green").save(f, "HEIF")
        self.assertEqual(load_image(f.getvalue()).shape, (150, 200, 3))

    def test_bad_files_are_explained(self):
        for data in (b"", b"not a photo", self.png("RGB")[:60], self.png("RGB", (20, 20)), b"<svg/>"):
            with self.assertRaises(BadPhoto):
                load_image(data)


if __name__ == "__main__":
    unittest.main()
