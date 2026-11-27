"""How well does "Find all parts" do?

  1. On drawn boards: how many real parts get a box, and how many boxes are
     real parts. A part counts as boxed when a box overlaps it with IoU > 0.5.
  2. The whole flow with no human naming: name every part with find_parts
     alone, take three parts off, and check the photos.
  3. The board held small in a busy photo (synth.in_clutter: a paper bag,
     tiles, a hand over one edge, a cable plugged in): boxes that land off the
     board, and parts boxed (IoU > 0.4; many parts are then only a few pixels).

Tuned on the training boards (100-139); report the development boards:

    python -m bench.find_eval 500 540
"""
import sys

import cv2
import numpy as np

from bench import synth
from boardcheck.decide import Model
from boardcheck.pipeline import Reference, check_photo
from boardcheck.suggest import find_parts


def iou(a, b):
    ix = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])) * max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    return ix / (a[2] * a[3] + b[2] * b[3] - ix)


def main(first, last):
    model = Model.load()
    by_colour = {}
    photos = right = unsure = wrong = 0
    for seed in range(first, last):
        b = synth.make_board(seed)
        ref_img, _ = synth.capture(synth.render(b), synth.Shot(noise=2, jpeg=94), seed)
        found = find_parts(ref_img)
        truth = [(p.x, p.y, p.w, p.h) for p in b.parts]
        c = by_colour.setdefault(b.mask, [0, 0, 0, 0])
        c[0] += len(truth)
        c[1] += sum(any(iou(t, f) > .5 for f in found) for t in truth)
        c[2] += len(found)
        c[3] += sum(any(iou(t, f) > .3 for t in truth) for f in found)

        ref = Reference(ref_img, [dict(id=str(i), name=f"Part {i + 1}", x=x, y=y, w=w, h=h) for i, (x, y, w, h) in enumerate(found)])
        owner = {}
        for p in b.parts:
            i = max(range(len(found)), key=lambda i: iou((p.x, p.y, p.w, p.h), found[i]), default=None)
            if i is not None and iou((p.x, p.y, p.w, p.h), found[i]) > .3:
                owner[p.name] = f"Part {i + 1}"
        covered = sorted(owner)
        gone = [str(n) for n in np.random.default_rng(seed).choice(covered, min(3, len(covered)), replace=False)]
        for level in ("line", "redraw"):
            for missing in ([], gone):
                img, _ = synth.capture(synth.render(b, missing), synth.LEVELS[level], seed * 7 + len(missing))
                r = check_photo(ref, img, model)
                said = {p.name for p in r.parts if p.verdict == "missing"}
                maybe = {p.name for p in r.parts if p.verdict == "check"}
                want = {owner[g] for g in missing}
                photos += 1
                if not said <= want or not want <= said | maybe:
                    wrong += 1
                elif maybe:
                    unsure += 1
                else:
                    right += 1

    held = off = held_hit = held_total = 0
    for seed in range(first, last):
        b = synth.make_board(seed)
        photo, M = synth.in_clutter(synth.render(b), seed)
        found = find_parts(photo)
        outline = cv2.transform(np.float32([[[0, 0], [b.w, 0], [b.w, b.h], [0, b.h]]]), M).reshape(-1, 1, 2)
        off += sum(cv2.pointPolygonTest(outline, (float(x + w / 2), float(y + h / 2)), True) < -5 for x, y, w, h in found)
        held += len(found)
        for p in b.parts:
            q = cv2.transform(np.float32([[[p.x, p.y], [p.x + p.w, p.y + p.h]]]), M)[0]
            box = (q[:, 0].min(), q[:, 1].min(), abs(q[1, 0] - q[0, 0]), abs(q[1, 1] - q[0, 1]))
            held_total += 1
            held_hit += any(iou(box, f) > .4 for f in found)

    t = [sum(v[i] for v in by_colour.values()) for i in range(4)]
    print(f"Boards {first}-{last - 1}: {t[1]}/{t[0]} parts boxed ({t[1] / t[0]:.1%}), "
          f"{t[3]}/{t[2]} boxes are parts ({t[3] / t[2]:.1%})")
    for colour, (n, hit, boxes, good) in sorted(by_colour.items()):
        print(f"  {colour:10s} {hit}/{n} boxed ({hit / n:.0%}), {good}/{boxes} boxes are parts")
    print(f"Named by find_parts alone, {photos} photos: {right} fully right, "
          f"{unsure} right but asked the operator to look, {wrong} with a wrong answer")
    print(f"Held small in a busy photo: {off} of {held} boxes off the board; "
          f"{held_hit}/{held_total} parts boxed ({held_hit / held_total:.0%})")


if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]))
