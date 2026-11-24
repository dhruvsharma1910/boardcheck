"""Writes samples/: one good board, three photos of it, and where the parts are."""
import json
from pathlib import Path

import cv2

from bench import synth

OUT = Path(__file__).parent.parent / "samples"
b = synth.make_board(8, mask="green", density=1.0)
parts = sorted(b.parts, key=lambda p: -p.w * p.h)
big, small = [p.name for p in parts[:6]], [p.name for p in parts if p.kind in ("resistor", "capacitor", "led")]
shots = {
    "reference": ([], [], synth.Shot(noise=2, jpeg=94), 1),
    "photo-1-complete": ([], [], synth.LEVELS["line"], 22),
    "photo-2-missing": ([big[1], small[0]], [small[3]], synth.LEVELS["line"], 33),
    "photo-3-harsh-light": ([small[1]], [], synth.LEVELS["harsh"], 47),
}
answers = {}
for name, (gone, wiped, shot, seed) in shots.items():
    img, _ = synth.capture(synth.render(b, gone, wiped=wiped), shot, seed)
    cv2.imwrite(str(OUT / f"{name}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    answers[name] = gone + wiped
named = [p for p in b.parts if p.name in set(big + small[:8]) | {g for a in answers.values() for g in a}]
(OUT / "parts.json").write_text(json.dumps(dict(
    parts=[dict(name=p.name, x=p.x - 2, y=p.y - 2, w=p.w + 4, h=p.h + 4) for p in named],
    missing=answers), indent=1))
print(answers, len(named))
