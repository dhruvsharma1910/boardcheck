"""Pin layouts and the boards that come with the app."""
import tempfile
import unittest
from pathlib import Path

from boardcheck import pinouts


def conn(layout, n):
    return dict(id="J", layout=layout, pins=[[f"P{i + 1}", ""] for i in range(n)])


def centre(p):
    return p["x"] + p["w"] / 2, p["y"] + p["h"] / 2


class Built_in(unittest.TestCase):
    def test_every_board_loads_and_names_each_pin_once(self):
        boards = pinouts.all_pinouts(Path(tempfile.mkdtemp()))
        self.assertGreaterEqual(len(boards), 2)
        for b in boards:
            with self.subTest(board=b["name"]):
                self.assertTrue(b["sources"], "every built-in board names where its pins came from")
                names = [p[0].lower() for c in b["connectors"] for p in c["pins"]]
                self.assertEqual(len(names), len(set(names)), "labelling every connector must not clash")
                for c in b["connectors"]:
                    for name, meaning in c["pins"]:
                        self.assertLessEqual(len(pinouts.label(name, meaning)), 40)


class Split(unittest.TestCase):
    def test_pin_1_is_in_the_chosen_corner(self):
        box = (100, 50, 200, 40)
        for corner in pinouts.CORNERS:
            first = centre(pinouts.split(box, conn("pmod", 12), corner)[0])
            self.assertEqual(first[0] < 200, corner.endswith("left"), corner)
            self.assertEqual(first[1] < 70, corner.startswith("top"), corner)

    def test_pmod_rows_run_the_same_way(self):
        pins = pinouts.split((0, 0, 120, 40), conn("pmod", 12))
        self.assertAlmostEqual(centre(pins[0])[0], centre(pins[6])[0])   # 1 above 7
        self.assertLess(centre(pins[0])[1], centre(pins[6])[1])
        self.assertLess(centre(pins[0])[0], centre(pins[5])[0])          # 1 .. 6 left to right

    def test_ribbon_header_alternates_rows(self):
        pins = pinouts.split((0, 0, 100, 20), conn("dual", 10))
        self.assertAlmostEqual(centre(pins[0])[0], centre(pins[1])[0])   # 1 and 2 share a column
        self.assertLess(centre(pins[1])[0], centre(pins[2])[0])

    def test_chip_goes_down_one_side_and_up_the_other(self):
        pins = pinouts.split((0, 0, 60, 200), conn("dip", 40))           # standing up, notch at the top
        self.assertLess(centre(pins[0])[1], centre(pins[19])[1])         # 1 at the top, 20 at the bottom
        self.assertLess(centre(pins[0])[0], centre(pins[20])[0])         # 21 on the other side
        self.assertGreater(centre(pins[20])[1], centre(pins[39])[1])     # 21 at the bottom, 40 at the top

    def test_pins_stay_inside_the_box_and_apart(self):
        for layout, n in (("row", 7), ("pmod", 12), ("dual", 40), ("dip", 28)):
            for box in ((10, 20, 300, 30), (10, 20, 30, 300)):
                pins = pinouts.split(box, conn(layout, n), "bottom-right")
                for p in pins:
                    self.assertGreaterEqual(p["x"], box[0])
                    self.assertLessEqual(p["x"] + p["w"], box[0] + box[2] + 1e-6)
                for a in pins:
                    for b in pins:
                        if a is not b:
                            self.assertFalse(abs(centre(a)[0] - centre(b)[0]) < 1e-6 and abs(centre(a)[1] - centre(b)[1]) < 1e-6)

    def test_pin_names_carry_their_meaning(self):
        c = dict(id="J", layout="row", pins=[["D13", "SPI SCK, built-in LED"], ["GND", "GND"]])
        self.assertEqual([p["name"] for p in pinouts.split((0, 0, 40, 10), c)], ["D13 = SPI SCK, built-in LED", "GND"])


class Teach(unittest.TestCase):
    def test_teach_and_forget(self):
        d = Path(tempfile.mkdtemp())
        spec = pinouts.PinoutIn(name="Lab kit", connectors=[dict(id="J1", layout="row", pins=[dict(name="J1-1", meaning="GND")])])
        b = pinouts.teach(d, spec)
        self.assertIn(b["id"], [x["id"] for x in pinouts.all_pinouts(d)])
        self.assertFalse(pinouts.forget(d, "arduino-uno-r3"), "built-in boards stay")
        self.assertFalse(pinouts.forget(d, "../../etc"))
        self.assertTrue(pinouts.forget(d, b["id"]))
        self.assertNotIn(b["id"], [x["id"] for x in pinouts.all_pinouts(d)])

    def test_bad_descriptions_are_refused(self):
        with self.assertRaises(ValueError):   # two rows need an even count
            pinouts.PinoutIn(name="x", connectors=[dict(id="J", layout="pmod", pins=[dict(name=f"{i}") for i in range(5)])])
        with self.assertRaises(ValueError):   # the same connector twice
            pinouts.PinoutIn(name="x", connectors=[dict(id="J", layout="row", pins=[dict(name="1")])] * 2)
