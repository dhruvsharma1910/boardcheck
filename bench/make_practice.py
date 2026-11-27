"""Writes samples/boards/: practice boards with their parts already named.

Each board gets a good reference photo, a parts.json, and photos to check:
complete, one part gone, three gone, both again in harsh light, and a photo
of a different board that the app should refuse. Boards 3001-3005 and
3101-3105 are not used by the benchmark or the model fit.

    python -m bench.make_practice
"""
import json
import shutil
from pathlib import Path

import cv2
import numpy as np

from bench import synth

OUT = Path(__file__).parent.parent / "samples" / "boards"
BOARDS = [("blue", 3001), ("red", 3002), ("black", 3003), ("white", 3004), ("purple", 3005)]
SMALL = ("resistor", "capacitor", "led", "diode", "sot")


def make(colour: str, seed: int) -> dict:
    out = OUT / colour
    out.mkdir(parents=True, exist_ok=True)
    b = synth.make_board(seed, mask=colour, density=1.0)
    parts = sorted(b.parts, key=lambda p: -p.w * p.h)
    big = [p.name for p in parts[:6]]
    small = [p.name for p in parts if p.kind in SMALL][:10]
    r = np.random.default_rng(seed)
    one = [str(r.choice(small))]
    rest = [n for n in small if n not in one]
    three = [str(r.choice(big[1:]))] + [str(n) for n in r.choice(rest, 2, replace=False)]
    harsh = [str(r.choice(rest))]
    shots = {
        "reference": ([], [], synth.Shot(noise=2, jpeg=94), 1),
        "1-good": ([], [], synth.LEVELS["line"], 22),
        "2-one-missing": (one, [], synth.LEVELS["line"], 33),
        "3-three-missing": (three[:2], three[2:], synth.LEVELS["line"], 44),
        "4-good-harsh-light": ([], [], synth.LEVELS["harsh"], 55),
        "5-one-missing-harsh-light": (harsh, [], synth.LEVELS["harsh"], 66),
    }
    missing = {}
    for name, (gone, wiped, shot, s) in shots.items():
        img, _ = synth.capture(synth.render(b, gone, wiped=wiped), shot, seed * 100 + s)
        cv2.imwrite(str(out / f"{name}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if name != "reference":
            missing[name] = sorted(gone + wiped)
    other = synth.make_board(seed + 100, mask=colour, density=1.0)
    img, _ = synth.capture(synth.render(other), synth.LEVELS["line"], seed * 100 + 77)
    cv2.imwrite(str(out / "6-wrong-board.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    named = [p for p in b.parts if p.name in set(big + small)]
    info = dict(
        name=f"Practice board: {colour}",
        parts=[dict(name=p.name, x=p.x - 2, y=p.y - 2, w=p.w + 4, h=p.h + 4) for p in named],
        missing=missing, wrong_board=["6-wrong-board"])
    (out / "parts.json").write_text(json.dumps(info, indent=1))
    return info


if __name__ == "__main__":
    shutil.rmtree(OUT, ignore_errors=True)
    for colour, seed in BOARDS:
        info = make(colour, seed)
        print(colour, len(info["parts"]), "parts", {k: v for k, v in info["missing"].items() if v})
