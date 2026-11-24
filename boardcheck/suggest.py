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
