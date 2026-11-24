"""Builds the benchmark: photos with known answers, and the scores of every method.

  train boards  100..139, easy / line / redraw           fits the weights
  dev boards    500..539, easy / line / redraw / harsh   looked at while designing
  test boards   900..959, easy / line / redraw / harsh   run once, at the end

No board is in two splits. "harsh" is never seen while fitting. Boxes are drawn with
human sloppiness and only some parts are named, as a real user would.
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np
from skimage.metrics import structural_similarity

from bench import synth
from boardcheck import evidence as ev
from boardcheck.align import align
from boardcheck.imaging import fit_long, to_gray
from bench.dropped_light import match_light
from boardcheck.pipeline import WORK_LONG, Reference, features_for

OUT = Path(__file__).parent / "out"
SPLITS = {"train": (range(100, 140), ("easy", "line", "redraw")),
          "dev": (range(500, 540), ("easy", "line", "redraw", "harsh")),
         "test": (range(900, 960), ("easy", "line", "redraw", "harsh"))}


def sloppy(p, r):
    j = lambda n: r.uniform(-.06, .10) * n
    x0, y0, x1, y1 = p.x - j(p.w), p.y - j(p.h), p.x + p.w + j(p.w), p.y + p.h + j(p.h)
    return dict(id=p.name, name=p.name, x=x0, y=y0, w=x1 - x0, h=y1 - y0)


def baselines(R: Reference, photo):
    """Simpler methods, scored on the same boxes. Higher = more likely missing."""
    test = fit_long(photo, WORK_LONG)
    raw = cv2.resize(test, (R.work.shape[1], R.work.shape[0]))
    al = align(R.work, test, R.boxes).warped
    rg, gg, ag = to_gray(R.work), to_gray(raw), to_gray(al)
    ssim = structural_similarity(rg, ag, full=True)[1]
    out = []
    for b in R.boxes:
        x0, y0, x1, y1 = ev.clip_box(b, rg.shape)
        s = (slice(y0, y1), slice(x0, x1))
        reach = 8
        area = ag[max(0, y0 - reach):y1 + reach, max(0, x0 - reach):x1 + reach]
        ncc = cv2.matchTemplate(area, rg[s], cv2.TM_CCOEFF_NORMED).max() if rg[s].std() > 1 else 0
        out.append([cv2.absdiff(rg, gg)[s].mean(), cv2.absdiff(rg, ag)[s].mean(),
                    1 - ssim[s].mean(), 1 - ncc])
    return out


def ablations(R: Reference, photo):
    """The full measurement set with one stage changed."""
    test = fit_long(photo, WORK_LONG)
    a = align(R.work, test, R.boxes)
    plain = cv2.resize(test, (R.work.shape[1], R.work.shape[0]))
    everywhere = np.ones(R.bare.shape, bool)
    out = {}
    for name, img, inside in (("with_light", match_light(R.work, a.warped, R.bare & a.inside), a.inside),
                              ("no_align", plain, everywhere)):
        v = ev.View.of(img)
        fl = ev.noise_floor(R.view, v, R.bare, inside, R.boxes)
        out[name] = [ev.measure(R.view, v, b, p, fl, R.bare)[0] for b, p in zip(R.boxes, R.palettes)]
    return out


def one_board(args):
    seed, levels = args
    cv2.setNumThreads(1)
    b = synth.make_board(seed)
    r = np.random.default_rng(seed + 9999)
    ref_photo, _ = synth.capture(synth.render(b), synth.Shot(noise=2, jpeg=93), seed)
    named = [p for p in b.parts if r.random() < r.uniform(.4, 1)] or b.parts[:3]
    R = Reference(ref_photo, [sloppy(p, r) for p in named])
    rows = []
    for li, lvl in enumerate(levels):
        for kind in (0, 1):  # 0 = complete, 1 = some missing
            gone = []
            if kind:
                gone = [p.name for p in r.permutation(np.array(named, dtype=object))[:int(r.integers(1, 5))]]
            wiped = [g for g in gone if r.random() < .4]
            sd = seed * 100 + li * 10 + kind
            img = synth.render(b, [g for g in gone if g not in wiped], wiped=wiped,
                               text_seed=sd if lvl == "redraw" else None)
            photo, _ = synth.capture(img, synth.LEVELS[lvl], sd)
            al, feats, _ = features_for(R, photo)
            base, abl = baselines(R, photo), ablations(R, photo)
            for i, p in enumerate(named):
                rows.append(dict(photo=f"{seed}-{lvl}-{kind}", level=lvl, mask=b.mask, kind=p.kind,
                                 gone=p.name in gone, wiped=p.name in wiped, quality=al.quality,
                                 feat=feats[i], base=base[i], with_light=abl["with_light"][i], no_align=abl["no_align"][i]))
    return rows


def wrong_board(seed):
    """Quality reported when the photo shows a different board altogether."""
    cv2.setNumThreads(1)
    a, b = synth.make_board(seed), synth.make_board(seed + 3000, mask=synth.make_board(seed).mask)
    R = Reference(synth.render(a), [dict(id=p.name, name=p.name, x=p.x, y=p.y, w=p.w, h=p.h) for p in a.parts])
    photo, _ = synth.capture(synth.render(b), synth.LEVELS["line"], seed)
    return align(R.work, fit_long(photo, WORK_LONG), R.boxes).quality


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    with ProcessPoolExecutor(8) as pool:
        for split in sys.argv[1:] or ("train", "dev"):
            seeds, levels = SPLITS[split]
            rows = [x for part in pool.map(one_board, [(s, levels) for s in seeds]) for x in part]
            keys = rows[0].keys()
            np.savez_compressed(OUT / f"{split}.npz", **{k: np.array([x[k] for x in rows]) for k in keys})
            print(split, len(rows), "part checks,", sum(x["gone"] for x in rows), "missing", file=sys.stderr)
        np.save(OUT / "wrong.npy", np.array(list(pool.map(wrong_board, range(700, 760)))))
