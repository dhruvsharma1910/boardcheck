"""Turn evidence into present / check by eye / missing.

A logistic regression over six readable measurements. Its weights live in
model.json, written by bench/fit.py. It never saw the user's board: the
measurements are comparisons, so the same weights work on any board.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .evidence import NAMES

PRESENT, CHECK, MISSING = "present", "check", "missing"
_FILE = Path(__file__).with_name("model.json")


class Model:
    def __init__(self, weights, bias, mean, scale, low, high):
        self.w, self.b = np.array(weights, float), float(bias)
        self.mean, self.scale = np.array(mean, float), np.array(scale, float)
        self.low, self.high = float(low), float(high)

    @classmethod
    def load(cls, path: Path = _FILE):
        d = json.loads(path.read_text())
        if tuple(d["features"]) != NAMES:
            raise ValueError("model.json was fitted for different measurements; run bench/fit.py")
        return cls(d["weights"], d["bias"], d["mean"], d["scale"], d["low"], d["high"])

    def probability(self, features) -> float:
        z = (np.asarray(features, float) - self.mean) / self.scale
        return float(1 / (1 + np.exp(-np.clip(z @ self.w + self.b, -40, 40))))

    def verdict(self, p: float) -> str:
        return MISSING if p >= self.high else CHECK if p >= self.low else PRESENT


def explain(features, verdict: str) -> str:
    """One plain sentence for the operator."""
    shape, edges, colour, outline, bare, _ = features
    if verdict == PRESENT:
        return "Looks the same as the good board."
    if bare > .12:
        why = "The colours here match bare board."
    elif outline > .35:
        why = "The outline of the part is gone."
    elif shape > .5 or edges > .6:
        why = "The shape here does not match the part."
    elif colour > .6:
        why = "The colour here has changed."
    else:
        why = "Small differences from the good board."
    return why if verdict == MISSING else why + " Not certain."
