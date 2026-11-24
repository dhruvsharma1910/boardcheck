"""Reference + named parts + one photo -> a verdict."""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from . import evidence as ev
from .align import align
from .decide import CHECK, MISSING, PRESENT, Model, explain
from .imaging import WORK_LONG, fit_long
from .light import match_light

MIN_QUALITY = .30   # below this the photo is not this board, or not this view
MIN_INSIDE = .80    # a part must be mostly in frame to be judged


@dataclass
class PartResult:
    id: str
    name: str
    verdict: str
    score: float          # 0 = surely there, 1 = surely gone
    reason: str
    quad: list            # four corners on the test photo, in its own pixels
    features: list


@dataclass
class PhotoResult:
    status: str           # "ok" | "missing" | "check" | "unreadable"
    parts: list
    quality: float
    method: str
    note: str = ""
    warped: np.ndarray | None = None   # the photo in the reference frame, for side-by-side


class Reference:
    """A good board, prepared once and reused for every photo."""

    def __init__(self, bgr: np.ndarray, parts: list[dict]):
        self.work = fit_long(bgr, WORK_LONG)
        self.scale = self.work.shape[1] / bgr.shape[1]
        self.parts = parts
        self.boxes = [tuple(v * self.scale for v in (p["x"], p["y"], p["w"], p["h"])) for p in parts]
        self.view = ev.View.of(self.work)
        self.bare = ev.board_mask(self.work.shape, self.boxes)
        self.palettes = [ev.local_palette(self.view.lab, b, self.bare, self.work.shape) for b in self.boxes]


def features_for(ref: Reference, test_bgr: np.ndarray):
    """Align, re-light, measure. Shared by the app and the benchmark."""
    test = fit_long(test_bgr, WORK_LONG)
    a = align(ref.work, test)
    lit = match_light(ref.work, a.warped, ref.bare & a.inside)
    view = ev.View.of(lit)
    floor = ev.noise_floor(ref.view, view, ref.bare, a.inside, ref.boxes)
    feats = [ev.measure(ref.view, view, b, pal, floor, ref.bare)[0] for b, pal in zip(ref.boxes, ref.palettes)]
    return a, lit, feats, test.shape[1] / test_bgr.shape[1]


def check_photo(ref: Reference, test_bgr: np.ndarray, model: Model) -> PhotoResult:
    a, lit, feats, test_scale = features_for(ref, test_bgr)
    if a.quality < MIN_QUALITY:
        return PhotoResult("unreadable", [], a.quality, a.method,
                           "This photo does not line up with the good board. Check that it shows the "
                           "same board from the same camera position, then try again.", lit)
    out = []
    for p, box, f in zip(ref.parts, ref.boxes, feats):
        x, y, w, h = box
        corners = np.float32([[[x, y], [x + w, y], [x + w, y + h], [x, y + h]]])
        quad = cv2.perspectiveTransform(corners, a.H)[0] / test_scale
        x0, y0, x1, y1 = ev.clip_box(box, a.inside.shape)
        if a.inside[y0:y1, x0:x1].mean() < MIN_INSIDE:
            verdict, prob, why = CHECK, .5, "This part is outside the photo."
        else:
            prob = model.probability(f)
            verdict = model.verdict(prob)
            why = explain(f, verdict)
        out.append(PartResult(p["id"], p["name"], verdict, prob, why, quad.tolist(), [float(v) for v in f]))
    status = "missing" if any(r.verdict == MISSING for r in out) else \
        "check" if any(r.verdict == CHECK for r in out) else "ok"
    return PhotoResult(status, out, a.quality, a.method, "", lit)


def visibility(ref: Reference, model: Model) -> list[str]:
    """For each part: if it vanished, would this app notice?

    The part is painted out of the reference and the result is judged like any
    photo. "hard" means the part blends into the board, and the user is told
    while they are still naming parts instead of finding out on the line.
    """
    out = []
    for box, pal in zip(ref.boxes, ref.palettes):
        x0, y0, x1, y1 = ev.clip_box(box, ref.work.shape)
        m = 12
        X0, Y0 = max(0, x0 - m), max(0, y0 - m)
        X1, Y1 = min(ref.work.shape[1], x1 + m), min(ref.work.shape[0], y1 + m)
        crop = ref.work[Y0:Y1, X0:X1].copy()
        hole = np.zeros(crop.shape[:2], np.uint8)
        hole[y0 - Y0:y1 - Y0, x0 - X0:x1 - X0] = 255
        gone = ref.work.copy()
        gone[Y0:Y1, X0:X1] = cv2.inpaint(crop, hole, 3, cv2.INPAINT_TELEA)
        f, _, _ = ev.measure(ref.view, ev.View.of(gone), box, pal, 0.0, ref.bare)
        p = model.probability(f)
        out.append("clear" if p >= model.high else "fair" if p >= model.low else "hard")
    return out
