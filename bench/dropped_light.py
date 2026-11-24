"""TRIED AND DROPPED. Kept only so the benchmark can show why.

Undo lighting differences, using only board we know should not have changed.

The user told us where every part is. Everything outside those boxes is bare
board, so any colour difference out there is the light, not a fault. We learn
the correction there and carry it across the boxes. A big missing chip
therefore cannot teach us that "the light got greener".
"""
from __future__ import annotations

import cv2
import numpy as np

OFFSET_PENALTY = .05


def match_light(ref: np.ndarray, test: np.ndarray, usable: np.ndarray) -> np.ndarray:
    """Return `test` re-lit to look like `ref`. Both BGR uint8, same size.

    usable: bool mask of pixels that are bare board and inside both photos.
    """
    R, T = ref.astype(np.float32), test.astype(np.float32)
    ok = usable & (T.max(2) < 250) & (T.min(2) > 3) & (R.max(2) < 250)
    if ok.mean() < .02:  # parts cover almost everything: use the whole frame
        ok = (T.max(2) < 250) & (R.max(2) < 250)
        if ok.mean() < .02:
            return test.copy()

    # 1. one contrast and one brightness per colour channel, refitted without outliers
    out = np.empty_like(T)
    for c in range(3):
        t, r = T[..., c][ok], R[..., c][ok]
        if t.size > 40000:
            pick = np.random.default_rng(0).choice(t.size, 40000, replace=False)
            t, r = t[pick], r[pick]
        keep = np.ones(t.size, bool)
        a, b = 1.0, 0.0
        for _ in range(4):
            tt, rr = t[keep], r[keep]
            # Light scales colours, it does not add to them. On a one-colour board
            # gain and offset cannot be told apart, so the offset is held near zero.
            A = np.array([[float((tt * tt).mean()), float(tt.mean())], [float(tt.mean()), 1.0 + OFFSET_PENALTY]])
            a, b = np.linalg.solve(A, np.array([float((tt * rr).mean()), float(rr.mean())]))
            a = float(np.clip(a, .4, 2.5))
            b = float(np.clip(rr.mean() - a * tt.mean(), -40, 40))
            res = np.abs(a * t + b - r)
            keep = res < max(6.0, 2.5 * float(np.median(res)))
        out[..., c] = a * T[..., c] + b

    # 2. what is left changes slowly across the frame (shadow, gradient)
    long_side = max(ref.shape[:2])
    m = ok.astype(np.float32)
    bad = np.abs(out - R).max(2) > 70  # scratches, dust, stray objects
    m[bad] = 0
    # The field is smooth by definition, so it is worked out small and scaled up.
    k = 8
    h, w = m.shape
    small = (max(8, w // k), max(8, h // k))
    shrink = lambda im: cv2.resize(im, small, interpolation=cv2.INTER_AREA)
    sm, sr, st = shrink(m), shrink((R + 12) * m[..., None]), shrink((out + 12) * m[..., None])
    gain = np.ones_like(sr)
    weight_total = np.zeros(sm.shape, np.float32)
    for frac in (.035, .10):
        s = frac * long_side / k
        num, den = cv2.GaussianBlur(sr, (0, 0), s), cv2.GaussianBlur(st, (0, 0), s)
        g = np.clip(num / np.maximum(den, 1e-3), .45, 2.2)
        wgt = np.clip(cv2.GaussianBlur(sm, (0, 0), s) / .25, 0, 1) * (1 - weight_total)
        gain = gain * (1 - wgt[..., None]) + g * wgt[..., None]
        weight_total = weight_total + wgt
    gain = cv2.resize(gain, (w, h), interpolation=cv2.INTER_LINEAR)
    return np.clip((out + 12) * gain - 12, 0, 255).astype(np.uint8)
