"""Practice set for the hardest case: black parts on black boards.

  python -m bench.dark_boards

Boards 2000..2039, all black. In no other split, so they may be looked at freely.
The final test boards (900..959) are not touched here.
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor

import cv2
import numpy as np

from bench import synth
from bench.dataset import OUT, sloppy
from boardcheck.decide import Model
from boardcheck.evidence import NAMES, features
from boardcheck.pipeline import Reference, features_for

SEEDS, LEVELS = range(2000, 2040), ("easy", "line", "redraw", "harsh")


def one_board(seed):
    cv2.setNumThreads(1)
    b = synth.make_board(seed, mask="black")
    r = np.random.default_rng(seed + 9999)
    ref, _ = synth.capture(synth.render(b), synth.Shot(noise=2, jpeg=93), seed)
    named = [p for p in b.parts if r.random() < r.uniform(.4, 1)] or b.parts[:3]
    R = Reference(ref, [sloppy(p, r) for p in named])
    rows = []
    for li, lvl in enumerate(LEVELS):
        for kind in (0, 1):
            gone = [p.name for p in r.permutation(np.array(named, dtype=object))[:int(r.integers(1, 5))]] if kind else []
            wiped = [g for g in gone if r.random() < .4]
            sd = seed * 100 + li * 10 + kind
            img = synth.render(b, [g for g in gone if g not in wiped], wiped=wiped, text_seed=sd if lvl == "redraw" else None)
            photo, _ = synth.capture(img, synth.LEVELS[lvl], sd)
            _, feats, _ = features_for(R, photo)
            rows += [dict(photo=f"{seed}-{lvl}-{kind}", level=lvl, kind=p.kind, name=p.name, gone=p.name in gone,
                          wiped=p.name in wiped, feat=f) for p, f in zip(named, feats)]
    return rows


def report(rows):
    m = Model.load()
    raw = np.array([x["feat"] for x in rows])
    gone = np.array([x["gone"] for x in rows])
    prob = np.array([m.probability(f) for f in raw])
    said = np.array([m.verdict(p) for p in prob])
    bad = ((said == "missing") & ~gone) | ((said == "present") & gone)
    photo = np.array([x["photo"] for x in rows])
    dirty = {p for p, b in zip(photo, bad) if b}
    print(f"{len(rows)} part checks, {gone.sum()} missing, {len(set(photo))} photos")
    print(f"wrong answers: {bad.sum()} in {len(dirty)} photos. sent to check by eye: "
          f"{((said == 'check') & gone).sum()} missing, {((said == 'check') & ~gone).sum()} present")
    for field in ("kind", "level"):
        v = np.array([x[field] for x in rows])
        print(field, {k: f"{bad[v == k].sum()}+{(said[v == k] == 'check').sum()}/{(v == k).sum()}" for k in np.unique(v)}, "(wrong + check / all)")
    print("\nnot answered outright:", *NAMES)
    for i in np.where(bad | (said == "check"))[0]:
        x = rows[i]
        print(f"{x['photo']:18s} {x['name']:6s} {x['kind']:12s} {'GONE' if gone[i] else 'here'}{' wiped' if x['wiped'] else ''} "
              f"said {said[i]:8s} p={prob[i]:.3f}", np.round(features(raw[i]), 2))


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    with ProcessPoolExecutor(8) as pool:
        rows = [x for part in pool.map(one_board, SEEDS) for x in part]
    np.save(OUT / "dark.npy", np.array(rows, dtype=object), allow_pickle=True)
    report(rows)
