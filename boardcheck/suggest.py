"""One click on a part -> a box around it.

Several simple segmentations each propose a box; the one whose four sides sit
on the strongest edges wins. The user can always drag the box afterwards, so
this only has to be a good first guess.
"""
from __future__ import annotations

import cv2
import numpy as np

from .imaging import fit_long, gradients, to_gray, to_lab

LONG = 1000


def _component_box(mask, x, y, reach=4):
    """Bounding box of the blob under (x, y), or within `reach` px of it."""
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    h, w = mask.shape
    x0, x1, y0, y1 = max(0, x - reach), min(w, x + reach + 1), max(0, y - reach), min(h, y + reach + 1)
    near = lbl[y0:y1, x0:x1]
    near = near[near > 0]
    if near.size == 0:
        return None
    i = int(np.bincount(near).argmax())
    bx, by, bw, bh, area = stats[i]
    return int(bx), int(by), int(bw), int(bh), area / max(1, bw * bh)


def _edge_support(mag, box):
    """Weakest-side-aware average edge strength along the rectangle."""
    H, W = mag.shape
    x, y, w, h = box
    t = 2
    def strip(y0, y1, x0, x1):
        s = mag[max(0, y0):min(H, y1), max(0, x0):min(W, x1)]
        return s if s.size else np.zeros((1, 1), np.float32)
    sides = [strip(y - t, y + t + 1, x, x + w).max(0).mean(), strip(y + h - t - 1, y + h + t, x, x + w).max(0).mean(),
             strip(y, y + h, x - t, x + t + 1).max(1).mean(), strip(y, y + h, x + w - t - 1, x + w + t).max(1).mean()]
    return .6 * float(np.mean(sides)) + .4 * float(np.min(sides))


def suggest_box(img: np.ndarray, px: float, py: float, taken=()):
    """img: BGR. (px, py) and the result are in img pixels: (x, y, w, h) or None."""
    H0, W0 = img.shape[:2]
    small = fit_long(img, LONG) if max(H0, W0) > LONG else img
    s = small.shape[1] / W0
    h, w = small.shape[:2]
    x, y = int(np.clip(px * s, 0, w - 1)), int(np.clip(py * s, 0, h - 1))

    soft = cv2.bilateralFilter(small, 7, 30, 5)
    lab = to_lab(soft)
    gx, gy = gradients(to_gray(soft), 1.0)
    mag = np.sqrt(gx * gx + gy * gy)

    # Work in a window: a part is never most of the board.
    R = int(.30 * max(h, w))
    wx0, wy0, wx1, wy1 = max(0, x - R), max(0, y - R), min(w, x + R), min(h, y + R)
    L, M = lab[wy0:wy1, wx0:wx1], mag[wy0:wy1, wx0:wx1]
    cx, cy = x - wx0, y - wy0
    proposals = []

    # a) whatever is not board-coloured
    px_all = L.reshape(-1, 3)
    pick = np.random.default_rng(0).choice(len(px_all), min(8000, len(px_all)), replace=False)
    cv2.setRNGSeed(1)
    _, lbl, centres = cv2.kmeans(px_all[pick].astype(np.float32), 5, None,
                                 (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 20, .5), 3, cv2.KMEANS_PP_CENTERS)
    main = centres[np.bincount(lbl.ravel(), minlength=5).argmax()]
    d = np.linalg.norm(L - main, axis=2)
    for thr in (8, 12, 18, 26, 36):
        m = (d > thr).astype(np.uint8)
        for close in (0, 3, 7):
            mm = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((close, close), np.uint8)) if close else m
            for opn in (0, 5):  # opening cuts thin silkscreen lines and traces off the blob
                b = _component_box(cv2.morphologyEx(mm, cv2.MORPH_OPEN, np.ones((opn, opn), np.uint8)) if opn else mm, cx, cy)
                if b:
                    proposals.append(b)
    # b) grow outwards from the clicked colour
    src = (np.clip(np.dstack([L[..., 0] * 2.55, L[..., 1] + 128, L[..., 2] + 128]), 0, 255)).astype(np.uint8)
    for tol in (5, 9, 14, 20):
        mask = np.zeros((src.shape[0] + 2, src.shape[1] + 2), np.uint8)
        cv2.floodFill(src.copy(), mask, (cx, cy), 0, (tol,) * 3, (tol,) * 3, 4 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY | cv2.FLOODFILL_FIXED_RANGE)
        m = cv2.morphologyEx((mask[1:-1, 1:-1] > 0).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
        b = _component_box(m, cx, cy)
        if b:
            proposals.append(b)
    # c) regions enclosed by edges
    for thr in (6, 10, 16):
        for close in (3, 7):
            e = cv2.morphologyEx((M > thr).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((close, close), np.uint8))
            filled = e.copy()
            cs, _ = cv2.findContours(e, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(filled, cs, -1, 1, -1)
            b = _component_box(cv2.morphologyEx(filled, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)), cx, cy)
            if b:
                proposals.append(b)

    best, best_score = None, -1.0
    H, W = M.shape
    for (bx, by, bw, bh, fill) in proposals:
        if bw < 8 or bh < 8 or bw * bh > .16 * w * h or max(bw / bh, bh / bw) > 14:
            continue
        if bx <= 0 or by <= 0 or bx + bw >= W or by + bh >= H:
            continue  # leaked out of the window
        cxn, cyn = (cx - bx) / bw, (cy - by) / bh
        if not (-.05 <= cxn <= 1.05 and -.05 <= cyn <= 1.05):
            continue
        centred = 1 - .35 * max(abs(cxn - .5), abs(cyn - .5)) * 2
        size = min(1.0, (min(bw, bh) / 14) ** .5)
        score = (_edge_support(M, (bx, by, bw, bh)) + 2) * (.45 + .55 * fill) * centred * size
        for (tx, ty, tw_, th_) in taken:  # do not swallow a part already named
            ax0, ay0 = max(bx + wx0, tx * s), max(by + wy0, ty * s)
            ax1, ay1 = min(bx + bw + wx0, (tx + tw_) * s), min(by + bh + wy0, (ty + th_) * s)
            if ax1 > ax0 and ay1 > ay0 and (ax1 - ax0) * (ay1 - ay0) > .5 * tw_ * th_ * s * s:
                score *= .3
        if score > best_score:
            best, best_score = (bx, by, bw, bh), score
    if best is None:
        return None
    bx, by, bw, bh = best
    pad = 1
    X0, Y0 = max(0, bx + wx0 - pad), max(0, by + wy0 - pad)
    X1, Y1 = min(w, bx + bw + wx0 + pad), min(h, by + bh + wy0 + pad)
    return X0 / s, Y0 / s, (X1 - X0) / s, (Y1 - Y0) / s


def _overlaps(a, b, share=.3):
    """True if a and b share more than `share` of the smaller one."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = min(ax + aw, bx + bw) - max(ax, bx)
    iy = min(ay + ah, by + bh) - max(ay, by)
    return ix > 0 and iy > 0 and ix * iy > share * min(aw * ah, bw * bh)


def _find_board(lab):
    """(board colour, board area) in a photo that may show a lot besides the board.

    Each of the photo's main colours is tried as the board's. Its biggest region
    is filled in, and the holes left inside it are counted: a board is the one
    thing in the photo with many part-sized things sitting inside it. A paper
    bag, a hand or a tiled floor has few.
    """
    h, w = lab.shape[:2]
    px = lab.reshape(-1, 3)
    pick = np.random.default_rng(0).choice(len(px), min(12000, len(px)), replace=False)
    cv2.setRNGSeed(1)
    _, lbl, centres = cv2.kmeans(px[pick].astype(np.float32), 6, None,
                                 (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 20, .5), 3, cv2.KMEANS_PP_CENTERS)
    share = np.bincount(lbl.ravel(), minlength=6) / len(pick)
    best = (-1.0, centres[share.argmax()], np.ones((h, w), np.uint8))
    for c, sh in zip(centres, share):
        if sh < .04:
            continue
        m = cv2.morphologyEx((np.linalg.norm(lab - c, axis=2) < 16).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        n, comp, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        if n < 2:
            continue
        i = 1 + int(stats[1:, cv2.CC_STAT_AREA].argmax())
        region = (comp == i).astype(np.uint8)
        # Cut off thin things joined to it, such as a cable plugged into the board.
        # The core survives an opening; the cable does not. The board's own thin
        # margins, right next to the core, are kept.
        solid = np.zeros((h, w), np.uint8)
        cs, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(solid, cs, -1, 1, -1)
        k = max(9, int(.04 * min(h, w))) | 1
        core = cv2.morphologyEx(solid, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
        n2, comp2, stats2, _ = cv2.connectedComponentsWithStats(core, connectivity=8)
        if n2 < 2:
            continue
        core = (comp2 == 1 + int(stats2[1:, cv2.CC_STAT_AREA].argmax())).astype(np.uint8)
        solid &= cv2.dilate(core, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
        region &= solid
        cs, _ = cv2.findContours(solid, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        hull = np.zeros((h, w), np.uint8)
        cv2.drawContours(hull, [cv2.convexHull(np.vstack(cs))], -1, 1, -1)
        size = int(hull.sum())
        if size < .03 * h * w:
            continue
        holes = cv2.morphologyEx(hull & (1 - region), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        k, _, hs, _ = cv2.connectedComponentsWithStats(holes, connectivity=8)
        a = hs[1:, cv2.CC_STAT_AREA]
        parts = int(((a >= 40) & (a <= .05 * size)).sum())
        # A board is mostly board, and its parts sit close together. A floor's
        # outline takes in half the photo, so its few gaps are far apart.
        score = parts * (region.sum() / size) / np.sqrt(size / (h * w))
        if score > best[0]:
            best = (score, c, hull)
    return best[1], best[2]


def find_parts(img: np.ndarray, taken=()):
    """Boxes around every part on a good board, in reading order, in img pixels.

    First the board is found (see _find_board), and cut out of the full-size
    photo so that a board held small in a busy picture still shows its parts.
    On the cut-out, a part is a solid patch that is not board coloured: a ring
    of pins is filled in, so a dark chip on a dark board still counts; thin lines
    (printed labels, outlines, traces) are cut away; round things in the board's
    corners are taken for mounting holes. Parts already named in `taken` are
    skipped. Measured by bench/find_eval.py.
    """
    H0, W0 = img.shape[:2]
    small = fit_long(img, LONG) if max(H0, W0) > LONG else img
    s = small.shape[1] / W0
    main, area = _find_board(to_lab(cv2.bilateralFilter(small, 7, 30, 5)))

    ys, xs = np.nonzero(area)
    sx0, sy0, sx1, sy1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    X0, Y0 = int(sx0 / s), int(sy0 / s)
    X1, Y1 = min(W0, int(np.ceil(sx1 / s))), min(H0, int(np.ceil(sy1 / s)))
    crop = img[Y0:Y1, X0:X1]
    view = fit_long(crop, LONG) if max(crop.shape[:2]) > LONG else crop
    c = view.shape[1] / crop.shape[1]
    h, w = view.shape[:2]
    area = cv2.resize(area[sy0:sy1, sx0:sx1], (w, h), interpolation=cv2.INTER_NEAREST)
    lab = to_lab(cv2.bilateralFilter(view, 7, 30, 5))
    d = np.linalg.norm(lab - main, axis=2)
    board_px = max(1, int(area.sum()))

    mask = ((d > 22) & (area > 0)).astype(np.uint8)
    # Rows of pins around a dark chip on a dark board: join them, fill the middle.
    ring = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((13, 13), np.uint8))
    cs, hier = cv2.findContours(ring, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    for cnt, hh in zip(cs, hier[0] if hier is not None else []):
        if hh[3] >= 0:
            x, y, bw, bh = cv2.boundingRect(cnt)
            if min(bw, bh) >= 14 and .5 * bw * bh < cv2.contourArea(cnt) < .05 * board_px:
                cv2.drawContours(mask, [cnt], -1, 1, -1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    named = [((tx - X0) * c, (ty - Y0) * c, tw * c, th * c) for tx, ty, tw, th in taken]
    ys, xs = np.nonzero(area)
    bx0, by0, bx1, by1 = xs.min(), ys.min(), xs.max(), ys.max()
    near = .07 * min(bx1 - bx0, by1 - by0)
    found = []
    for x, y, bw, bh, a in stats[1:]:
        if bw < 7 or bh < 7 or a < 80 or bw * bh > .16 * board_px:
            continue
        if max(bw / bh, bh / bw) > 14 or a < .35 * bw * bh:
            continue  # a line or an outline, not a part
        cx, cy = x + bw / 2, y + bh / 2
        if max(bw / bh, bh / bw) < 1.25 and min(abs(cx - bx0), abs(cx - bx1)) < near and min(abs(cy - by0), abs(cy - by1)) < near:
            continue  # a round thing in a corner of the board: a mounting hole
        box = (int(x) - 1, int(y) - 1, int(bw) + 2, int(bh) + 2)
        if any(_overlaps(box, q) for q in named):
            continue
        found.append(box)

    # Reading order: rows of roughly one part's height, then left to right.
    row = max(8.0, float(np.median([b[3] for b in found]))) if found else 1.0
    found.sort(key=lambda b: (int((b[1] + b[3] / 2) // (2 * row)), b[0]))
    return [(X0 + max(0, x) / c, Y0 + max(0, y) / c, bw / c, bh / c) for x, y, bw, bh in found]
