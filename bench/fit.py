"""Fits boardcheck/model.json on the training boards and scores every method on
boards it has never seen. Writes bench/RESULTS.md. Run bench.dataset first."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from boardcheck.evidence import NAMES, features

HERE = Path(__file__).parent


def logistic(X, y, l2=1.0, rounds=60):
    """Newton's method. Classes are weighted equally: missing parts are rare."""
    w = np.where(y, .5 / y.mean(), .5 / (1 - y.mean()))
    A = np.c_[X, np.ones(len(X))]
    beta = np.zeros(A.shape[1])
    reg = np.diag([l2] * X.shape[1] + [0.0])
    for _ in range(rounds):
        p = 1 / (1 + np.exp(-np.clip(A @ beta, -40, 40)))
        g = A.T @ (w * (p - y)) + reg @ beta
        H = (A * (w * p * (1 - p))[:, None]).T @ A + reg + 1e-6 * np.eye(len(beta))
        step = np.linalg.solve(H, g)
        beta -= step
        if np.abs(step).max() < 1e-7:
            break
    return beta[:-1], beta[-1]


def auc(s, y):
    order = np.argsort(np.argsort(s, kind="stable"), kind="stable") + 1
    n1, n0 = y.sum(), (~y).sum()
    return (order[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def best_cut(s, y):
    """Threshold with the fewest balanced errors on the training boards."""
    cuts = np.unique(np.quantile(s, np.linspace(0, 1, 801)))
    err = [(s[y] < c).mean() + (s[~y] >= c).mean() for c in cuts]
    return cuts[int(np.argmin(err))]


def load(split):
    d = np.load(HERE / "out" / f"{split}.npz")
    out = {k: d[k] for k in d.files}
    for k in ("feat", "no_light", "no_align"):
        out[k] = features(out[k])
    return out


def main(split="dev"):
    tr, te = load("train"), load(split)
    y, yt = tr["gone"].astype(bool), te["gone"].astype(bool)
    mean, scale = tr["feat"].mean(0), tr["feat"].std(0) + 1e-6
    w, b = logistic((tr["feat"] - mean) / scale, y)
    prob = lambda f: 1 / (1 + np.exp(-np.clip((f - mean) / scale @ w + b, -40, 40)))

    ptr = prob(tr["feat"])
    cut = best_cut(ptr, y)
    # "check by eye" is the band around the cut, capped at 2% of training parts
    logit = lambda p: np.log(p / (1 - p))
    sig = lambda z: 1 / (1 + np.exp(-z))
    c = float(np.clip(logit(np.clip(cut, 1e-6, 1 - 1e-6)), -3, 3))
    band = .2
    while band < 3 and ((ptr > sig(c - band - .1)) & (ptr < sig(c + band + .1))).mean() < .02:
        band += .1
    low, high = float(sig(c - band)), float(sig(c + band))
    (HERE.parent / "boardcheck" / "model.json").write_text(json.dumps(dict(
        features=list(NAMES), weights=[round(float(v), 5) for v in w], bias=round(float(b), 5),
        mean=[round(float(v), 5) for v in mean], scale=[round(float(v), 5) for v in scale],
        low=round(low, 4), high=round(high, 4)), indent=1) + "\n")
    print("weights", dict(zip(NAMES, np.round(w, 2))), "bias", round(b, 2), "band", round(low, 3), round(high, 3))

    methods = {}
    for i, name in enumerate(("Pixel difference, as taken", "Pixel difference, aligned", "SSIM, aligned",
                              "Template match (NCC), aligned")):
        methods[name] = (tr["base"][:, i], te["base"][:, i])
    for key, name in (("no_align", "This app without alignment"), ("no_light", "This app without light matching")):
        m, s = tr[key].mean(0), tr[key].std(0) + 1e-6
        ww, bb = logistic((tr[key] - m) / s, y)
        methods[name] = ((tr[key] - m) / s @ ww + bb, (te[key] - m) / s @ ww + bb)
    drop = [i for i, n in enumerate(NAMES) if n != "bare"]
    m, s = mean[drop], scale[drop]
    ww, bb = logistic((tr["feat"][:, drop] - m) / s, y)
    methods["This app without the bare-board vote"] = ((tr["feat"][:, drop] - m) / s @ ww + bb, (te["feat"][:, drop] - m) / s @ ww + bb)
    methods["This app"] = (ptr, prob(te["feat"]))

    levels = ["easy", "line", "redraw", "harsh"]
    lines = ["| Method | AUC | Missed | False alarms | Photos fully right | " + " | ".join(f"{l}" for l in levels) + " |",
             "|---|---|---|---|---|" + "---|" * len(levels)]
    photos = te["photo"]
    uniq, inv = np.unique(photos, return_inverse=True)
    plevel = np.array([u.split("-")[1] for u in uniq])
    for name, (a, t) in methods.items():
        k = best_cut(a, y)
        pred = t >= k
        wrong = np.bincount(inv, weights=(pred != yt).astype(float)) > 0
        cells = [f"{100 * (1 - wrong[plevel == l].mean()):.0f}%" for l in levels]
        lines.append(f"| {name} | {auc(t, yt):.4f} | {(~pred & yt).sum()} of {yt.sum()} | {(pred & ~yt).sum()} of {(~yt).sum()} | "
                     f"{100 * (1 - wrong.mean()):.1f}% | " + " | ".join(cells) + " |")

    pt = prob(te["feat"])
    v = np.where(pt >= high, 2, np.where(pt >= low, 1, 0))
    three = ["", "Shipped three-way verdict, same unseen boards:", "",
             "| | said present | said check by eye | said missing |", "|---|---|---|---|",
             *(f"| really {n} | {(v[mask] == 0).sum()} | {(v[mask] == 1).sum()} | {(v[mask] == 2).sum()} |"
               for n, mask in (("present", ~yt), ("missing", yt)))]
    per = ["", "By part type and board colour (two-way errors / checks):", "", "| | errors | checks |", "|---|---|---|"]
    pred = pt >= best_cut(ptr, y)
    for field in ("kind", "mask"):
        for val in np.unique(te[field]):
            s_ = te[field] == val
            per.append(f"| {val} | {(pred[s_] != yt[s_]).sum()} | {s_.sum()} |")
    wq = np.load(HERE / "out" / "wrong.npy")
    q = ["", f"Alignment quality on the right board: min {te['quality'].min():.2f}, median {np.median(te['quality']):.2f} "
         f"({len(uniq)} photos). On a different board: max {wq.max():.2f}, median {np.median(wq):.2f} ({len(wq)} photos)."]
    text = "\n".join(["# Benchmark results", "", f"Generated by `python -m bench.fit {split}`. Set: {split}, {len(yt)} part checks, "
                      f"{yt.sum()} missing, {len(uniq)} photos, boards never used for fitting. "
                      "The `harsh` level is never used for fitting either. All images are synthetic. "
                      "The last four columns are photos fully right at each level.", "", *lines, *three, *q, *per]) + "\n"
    (HERE / ("RESULTS.md" if split == "test" else "RESULTS-dev.md")).write_text(text)
    print(text)


if __name__ == "__main__":
    main(*sys.argv[1:])
