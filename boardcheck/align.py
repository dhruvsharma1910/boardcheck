"""Lay a test photo exactly over the reference photo.

"Fixed camera" still means a pixel or ten of shift when a board is put down,
and a photo redrawn by an AI editor bends slightly in places. So:

  1. propose several global alignments (none, feature match, fine-tuned),
  2. keep whichever one actually makes the board line up best,
  3. remove the small local bends that remain,
  4. report a quality number so a wrong board is refused, not judged.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .imaging import gradients, to_gray

TILE = 80


@dataclass
class Alignment:
    H: np.ndarray          # reference px -> test px (both at working size)
    warped: np.ndarray     # the test photo redrawn in the reference frame
    inside: np.ndarray     # where the reference frame is covered by the photo
    quality: float         # 0..1, how well unchanged board lines up
    coverage: float        # fraction of reference tiles that could be compared
    method: str


def _warp(img, H, size):
    w, h = size
    flags = cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP
    return cv2.warpPerspective(img, H, (w, h), flags=flags, borderMode=cv2.BORDER_REPLICATE)


def _inside(shape, H, size):
    m = np.full(shape[:2], 255, np.uint8)
    return cv2.warpPerspective(m, H, size, flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP, borderValue=0) > 0


def _tile_scores(ref_g, test_g, inside):
    """Gradient agreement of each textured tile. Immune to brightness changes."""
    rx, ry = ref_g
    tx, ty = test_g
    num = rx * tx + ry * ty
    rr, tt = rx * rx + ry * ry, tx * tx + ty * ty
    h, w = num.shape
    out, total = [], 0
    for y in range(0, h - TILE // 2, TILE):
        for x in range(0, w - TILE // 2, TILE):
            sl = (slice(y, min(h, y + TILE)), slice(x, min(w, x + TILE)))
            energy = float(rr[sl].sum())
            if energy < 1.2 * rr[sl].size:  # plain surface, nothing to line up
                continue
            total += 1
            if inside[sl].mean() < .9:
                continue
            out.append(float(num[sl].sum()) / (np.sqrt(energy * float(tt[sl].sum())) + 1e-6))
    return np.array(out), total


def _quality(ref_g, test_bgr, H, size):
    warped = _warp(test_bgr, H, size)
    inside = _inside(test_bgr.shape, H, size)
    scores, total = _tile_scores(ref_g, gradients(to_gray(warped), 1.6), inside)
    if total == 0 or len(scores) < max(3, .35 * total):
        return 0.0, len(scores) / max(1, total)
    # Upper-middle of the tiles: parts really missing must not count as misalignment.
    return float(np.percentile(scores, 60)), len(scores) / total


def _sane(H, ref_size, test_size):
    """Reject folded, mirrored or wildly scaled solutions."""
    if H is None or not np.isfinite(H).all():
        return False
    w, h = ref_size
    quad = cv2.perspectiveTransform(np.float32([[[0, 0], [w, 0], [w, h], [0, h]]]), H)[0]
    if not cv2.isContourConvex(quad.astype(np.float32).reshape(-1, 1, 2)):
        return False
    area = cv2.contourArea(quad.astype(np.float32), oriented=True)
    ratio = area / (test_size[0] * test_size[1])
    return .15 < ratio < 6.0


def _features(ref_gray, test_gray):
    sift = cv2.SIFT_create(nfeatures=3500, contrastThreshold=.02)
    k1, d1 = sift.detectAndCompute(ref_gray, None)
    k2, d2 = sift.detectAndCompute(test_gray, None)
    if d1 is None or d2 is None or len(k1) < 12 or len(k2) < 12:
        return None
    pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(d1, d2, k=2)
    good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < .78 * p[1].distance]
    if len(good) < 12:
        return None
    a = np.float32([k1[m.queryIdx].pt for m in good])
    b = np.float32([k2[m.trainIdx].pt for m in good])
    H, inl = cv2.findHomography(a, b, cv2.USAC_MAGSAC, 3.0, maxIters=5000, confidence=.999)
    if H is None or int(inl.sum()) < 12:
        return None
    return H


def _refine(ref_gray, test_gray, H, size):
    """ECC on edge maps at half size: sub-pixel, ignores lighting."""
    s = .5
    S = np.diag([s, s, 1.0])
    def prep(g):
        gx, gy = gradients(cv2.resize(g, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), 1.5)
        return np.sqrt(gx * gx + gy * gy).astype(np.float32)
    W = (S @ H @ np.linalg.inv(S))
    W = (W / W[2, 2]).astype(np.float32)
    try:
        _, W = cv2.findTransformECC(prep(ref_gray), prep(test_gray), W, cv2.MOTION_HOMOGRAPHY,
                                    (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 40, 1e-5), None, 5)
    except cv2.error:
        return None
    return np.linalg.inv(S) @ W.astype(np.float64) @ S


def align(ref: np.ndarray, test: np.ndarray) -> Alignment:
    """Align `test` (BGR, working size) to `ref` (BGR, working size)."""
    h, w = ref.shape[:2]
    th, tw = test.shape[:2]
    size = (w, h)
    ref_gray, test_gray = to_gray(ref), to_gray(test)
    ref_g = gradients(ref_gray, 1.6)

    identity = np.diag([tw / w, th / h, 1.0])
    best = ("as taken", identity, *_quality(ref_g, test, identity, size))

    def consider(name, H):
        nonlocal best
        if H is None or not _sane(H, size, (tw, th)):
            return
        q, c = _quality(ref_g, test, H, size)
        if q > best[2] + .004:
            best = (name, H, q, c)

    consider("feature match", _features(ref_gray, test_gray))
    consider("fine-tuned", _refine(ref_gray, test_gray, best[1], size))

    name, H, q, c = best
    warped, inside = _warp(test, H, size), _inside(test.shape, H, size)
    flow = _residual_flow(ref_gray, to_gray(warped), inside)
    if flow is not None:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        bent = cv2.remap(warped, xx + flow[..., 0], yy + flow[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        s2, t2 = _tile_scores(ref_g, gradients(to_gray(bent), 1.6), inside)
        if len(s2) and float(np.percentile(s2, 60)) > q + .01:
            warped, q, name = bent, float(np.percentile(s2, 60)), name + " + local"
    return Alignment(H, warped, inside, max(0.0, q), c, name)


def _residual_flow(ref_gray, test_gray, inside, tile=96, step=48, reach=9):
    """Small smooth bends left after the global fit, one vote per tile.

    Each tile votes for a shift of at most `reach` px. Votes are then median
    filtered, so one tile that lost its part cannot drag its surroundings.
    """
    h, w = ref_gray.shape
    if h < tile + 2 * reach or w < tile + 2 * reach:
        return None
    def edge(g):
        gx, gy = gradients(g, 1.2)
        return np.sqrt(gx * gx + gy * gy).astype(np.float32)
    R, T = edge(ref_gray), edge(test_gray)
    ys = list(range(reach, h - tile - reach + 1, step))
    xs = list(range(reach, w - tile - reach + 1, step))
    if len(ys) < 2 or len(xs) < 2:
        return None
    U = np.full((len(ys), len(xs), 2), np.nan, np.float32)
    for i, y in enumerate(ys):
        for j, x in enumerate(xs):
            t = R[y:y + tile, x:x + tile]
            if t.std() < 1.6 or inside[y:y + tile, x:x + tile].mean() < .95:
                continue
            res = cv2.matchTemplate(T[y - reach:y + tile + reach, x - reach:x + tile + reach], t, cv2.TM_CCOEFF_NORMED)
            _, score, _, (px, py) = cv2.minMaxLoc(res)
            if score > .45 and 0 < px < 2 * reach and 0 < py < 2 * reach:
                U[i, j] = (px - reach, py - reach)
    known = ~np.isnan(U[..., 0])
    if known.mean() < .15:
        return None
    smooth = np.zeros_like(U)
    for i in range(len(ys)):
        for j in range(len(xs)):
            for rad in (1, 2, 4, 99):
                sl = (slice(max(0, i - rad), i + rad + 1), slice(max(0, j - rad), j + rad + 1))
                k = known[sl]
                if k.sum() >= 4:
                    smooth[i, j] = np.median(U[sl][k], axis=0)
                    break
    if np.abs(smooth).max() < 1:
        return None
    # sample the coarse grid at every pixel
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    gx = np.clip((xx - xs[0] - tile / 2) / step, 0, len(xs) - 1)
    gy = np.clip((yy - ys[0] - tile / 2) / step, 0, len(ys) - 1)
    flow = cv2.remap(smooth, gx, gy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return cv2.GaussianBlur(flow, (0, 0), step / 3)
