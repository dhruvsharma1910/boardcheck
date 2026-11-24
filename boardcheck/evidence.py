"""Evidence that one named part is there or gone.

Two questions are asked of each box:
  * does it still look like this part?            (shape, edges, colour)
  * does it now look like the bare board instead? (palette vote)

The second question is what separates "missing" from merely "different":
new batch codes, a shadow, or a redrawn texture change the first answer, but
they do not turn the box into empty board.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .imaging import gradients, to_gray, to_lab

RAW = ("shape", "edges", "core", "core_edges", "colour", "outline", "bare", "floor")
NAMES = ("shape", "edges", "core", "core_edges", "colour", "outline", "bare")


@dataclass
class View:
    """Per-image maps computed once and shared by all parts."""
    lab: np.ndarray
    gray: np.ndarray
    gx: np.ndarray
    gy: np.ndarray

    @classmethod
    def of(cls, bgr):
        soft = cv2.GaussianBlur(bgr, (0, 0), 1.1)
        gray = to_gray(soft).astype(np.float32)
        gx, gy = gradients(gray, .8)
        return cls(to_lab(soft), gray, gx, gy)

    def crop(self, x0, y0, x1, y1):
        s = (slice(y0, y1), slice(x0, x1))
        return View(self.lab[s], self.gray[s], self.gx[s], self.gy[s])


def clip_box(box, shape):
    x, y, w, h = box
    H, W = shape[:2]
    x0, y0 = int(max(0, np.floor(x))), int(max(0, np.floor(y)))
    x1, y1 = int(min(W, np.ceil(x + w))), int(min(H, np.ceil(y + h)))
    return x0, y0, max(x0 + 2, x1), max(y0 + 2, y1)


def board_mask(shape, boxes, margin=.12, pad=4):
    """True where no part was named."""
    m = np.ones(shape[:2], bool)
    for b in boxes:
        x, y, w, h = b
        g = pad + margin * min(w, h)
        x0, y0, x1, y1 = clip_box((x - g, y - g, w + 2 * g, h + 2 * g), shape)
        m[y0:y1, x0:x1] = False
    return m


def palette(lab, mask, k=6, seed=0):
    """The colours a bare board is made of, commonest first."""
    px = lab[mask]
    if len(px) < 60:
        return None
    rng = np.random.default_rng(seed)
    px = px[rng.choice(len(px), min(6000, len(px)), replace=False)].astype(np.float32)
    k = min(k, len(px))
    cv2.setRNGSeed(1)
    _, lbl, c = cv2.kmeans(px, k, None, (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 20, .5), 3, cv2.KMEANS_PP_CENTERS)
    share = np.bincount(lbl.ravel(), minlength=k) / len(px)
    c = c[share > .02]
    return c if len(c) else None


def local_palette(lab, box, others_mask, shape):
    """Bare-board colours near this part, falling back to the whole board."""
    x, y, w, h = box
    g = max(14.0, 1.1 * max(w, h))
    x0, y0, x1, y1 = clip_box((x - g, y - g, w + 2 * g, h + 2 * g), shape)
    m = np.zeros(shape[:2], bool)
    m[y0:y1, x0:x1] = True
    m &= others_mask
    near = palette(lab, m, k=5) if m.sum() > 200 else None
    return near if near is not None else palette(lab, others_mask, k=6)


def _ncc(a, b, k):
    a, b = a - a.mean(), b - b.mean()
    return float((a * b).mean() + k) / float(np.sqrt((a * a).mean() * (b * b).mean()) + k)


def _grad_agreement(r: View, t: View, k):
    num = float((r.gx * t.gx + r.gy * t.gy).mean())
    den = float(np.sqrt((r.gx ** 2 + r.gy ** 2).mean() * (t.gx ** 2 + t.gy ** 2).mean()))
    return (num + k) / (den + k)


def best_shift(ref: View, test: View, x0, y0, x1, y1, reach=4):
    """Nudge the box a few pixels to where the part fits best.

    The reach is deliberately tiny: big enough for a part redrawn slightly out
    of place, too small to slide onto the identical resistor next door.
    """
    H, W = ref.gray.shape
    rx0, ry0 = max(0, x0 - reach), max(0, y0 - reach)
    rx1, ry1 = min(W, x1 + reach), min(H, y1 + reach)
    tmpl = ref.gray[y0:y1, x0:x1]
    area = test.gray[ry0:ry1, rx0:rx1]
    if tmpl.std() < 2 or area.shape[0] < tmpl.shape[0] or area.shape[1] < tmpl.shape[1]:
        return 0, 0
    res = cv2.matchTemplate(area, tmpl, cv2.TM_CCOEFF_NORMED)
    _, top, _, (px, py) = cv2.minMaxLoc(res)
    still = res[min(res.shape[0] - 1, y0 - ry0), min(res.shape[1] - 1, x0 - rx0)]
    if top < still + .02:
        return 0, 0
    return px + rx0 - x0, py + ry0 - y0


def ring_shift(ref: View, test: View, x0, y0, x1, y1, bare):
    """How much the light changed right next to this part (Lab offset).

    Glare or a shadow tints the part and the board beside it alike. Removing a
    part does not. So the change in the ring is the light's share.
    """
    H, W = ref.gray.shape
    g = int(max(6, .35 * min(x1 - x0, y1 - y0)))
    X0, Y0, X1, Y1 = max(0, x0 - g), max(0, y0 - g), min(W, x1 + g), min(H, y1 + g)
    m = bare[Y0:Y1, X0:X1].copy()
    m[y0 - Y0:y1 - Y0, x0 - X0:x1 - X0] = False
    if m.sum() < 60:
        return np.zeros(3, np.float32)
    d = test.lab[Y0:Y1, X0:X1][m] - ref.lab[Y0:Y1, X0:X1][m]
    return np.clip(np.median(d, axis=0), -45, 45).astype(np.float32)


def raw_measures(ref: View, test: View, x0, y0, x1, y1, pal, bare_mask=None, reach=4):
    """Differences for one box, 0 = identical. Order: RAW without the floor."""
    dx, dy = best_shift(ref, test, x0, y0, x1, y1, reach)
    H, W = ref.gray.shape
    dx = int(np.clip(dx, -x0, W - x1))
    dy = int(np.clip(dy, -y0, H - y1))
    r = ref.crop(x0, y0, x1, y1)
    t = test.crop(x0 + dx, y0 + dy, x1 + dx, y1 + dy)

    shape = 1 - _ncc(r.gray, t.gray, 30.0)
    edges = 1 - _grad_agreement(r, t, 2.0)
    # The rim of a box is pads and silkscreen, which stay behind when the part
    # goes. The middle is the part itself.
    my, mx = int(.2 * (y1 - y0)), int(.2 * (x1 - x0))
    rc = r.crop(mx, my, x1 - x0 - mx, y1 - y0 - my)
    tc = t.crop(mx, my, x1 - x0 - mx, y1 - y0 - my)
    core = 1 - _ncc(rc.gray, tc.gray, 30.0)
    core_edges = 1 - _grad_agreement(rc, tc, 2.0)

    tlab = t.lab
    if bare_mask is not None:
        tlab = tlab - ring_shift(ref, test, x0, y0, x1, y1, bare_mask)
    d_part = np.linalg.norm(r.lab - tlab, axis=2)
    colour = float(np.minimum(d_part, 60).mean()) / 25.0

    er = float(np.sqrt(r.gx ** 2 + r.gy ** 2).mean())
    et = float(np.sqrt(t.gx ** 2 + t.gy ** 2).mean())
    outline = float(np.clip((er - et) / (er + 1.0), -1, 1))

    bare, cover = 0.0, 0.0
    if pal is not None:
        dist = lambda lab: np.min(np.linalg.norm(lab[:, :, None, :] - pal[None, None], axis=3), axis=2)
        d_board_ref, d_board_test = dist(r.lab), dist(tlab)
        weight = np.clip((d_board_ref - 7) / 16, 0, 1)  # pixels that can tell part from board
        cover = float(weight.mean())
        if cover > .02:
            gone = np.clip((d_part - d_board_test) / (np.maximum(d_part, d_board_test) + 4) + .5, 0, 1)
            vote = float((weight * gone).sum() / weight.sum())
            bare = (vote - .5) * min(1.0, cover / .25)
    return np.array([shape, edges, core, core_edges, colour, outline, bare]), cover, (dx, dy)


def noise_floor(ref: View, test: View, mask, inside, boxes, seed=0):
    """How different does board that did NOT change look in this photo?

    Boxes the size of typical parts are dropped on unnamed board. Their score
    is what "no change" costs in this particular photo, whether the cause is
    blur, grain, compression or an AI redraw.
    """
    H, W = ref.gray.shape
    if not boxes:
        return 0.0
    rng = np.random.default_rng(seed)
    bw = int(np.clip(np.median([b[2] for b in boxes]), 16, W // 6))
    bh = int(np.clip(np.median([b[3] for b in boxes]), 16, H // 6))
    bw, bh = max(bw, bh), max(bw, bh)
    free = cv2.boxFilter((mask & inside).astype(np.float32), -1, (bw, bh), anchor=(0, 0), borderType=cv2.BORDER_CONSTANT)
    energy = cv2.boxFilter(ref.gx ** 2 + ref.gy ** 2, -1, (bw, bh), anchor=(0, 0), borderType=cv2.BORDER_CONSTANT)
    free[H - bh:], free[:, W - bw:] = 0, 0
    ys, xs = np.where((free > .97) & (energy > 2.0))
    if len(ys) < 5:
        return 0.0
    pick = rng.choice(len(ys), min(40, len(ys)), replace=False)
    scores = []
    for y, x in zip(ys[pick], xs[pick]):
        m, _, _ = raw_measures(ref, test, int(x), int(y), int(x + bw), int(y + bh), None)
        scores.append(.5 * (m[0] + m[1]))
    return float(np.median(scores))


def measure(ref: View, test: View, box, pal, floor: float, bare_mask=None):
    """Raw evidence for one part, in the order of RAW."""
    x, y, w, h = box
    g = max(2.0, .10 * min(w, h))  # a sliver of surroundings keeps the outline in view
    x0, y0, x1, y1 = clip_box((x - g, y - g, w + 2 * g, h + 2 * g), ref.gray.shape)
    m, cover, shift = raw_measures(ref, test, x0, y0, x1, y1, pal, bare_mask)
    return np.append(m, floor), cover, shift


def features(raw):
    """Raw evidence -> what the decision is made on, in the order of NAMES.

    Structural differences become log-ratios against the photo's own noise
    floor: 0.12 is damning in a clean photo and ordinary in a blurred one.
    """
    raw = np.asarray(raw, float)
    floor = raw[..., 7]
    rel = lambda v: np.log((np.maximum(v, 0) + .01) / (floor + .03))
    return np.stack([rel(raw[..., 0]), rel(raw[..., 1]), rel(raw[..., 2]), rel(raw[..., 3]),
                     np.log(raw[..., 4] + .08), raw[..., 5], raw[..., 6]], axis=-1)
