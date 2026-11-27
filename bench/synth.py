"""Draws practice circuit boards with known ground truth.

Nothing in the app imports this file. It exists because the brief gives no
data: each board is built from a seed, any part can be left off, and the
empty footprint (pads, solder, silkscreen outline) shows where it was.

`render()` is the board itself. `capture()` is the camera, the light, and
optionally the drift an AI image editor adds when it redraws a photo.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

SS = 2  # supersampling: draw at 2x, shrink at the end

# (solder mask BGR, silkscreen BGR). Deliberately includes awkward ones:
# black parts on a black board, white silkscreen on a white board.
MASKS = {
    "green": ((62, 104, 28), (228, 234, 232)),
    "darkgreen": ((38, 62, 18), (214, 220, 218)),
    "blue": ((128, 62, 18), (232, 232, 228)),
    "red": ((34, 30, 150), (230, 232, 235)),
    "black": ((34, 32, 30), (205, 208, 206)),
    "white": ((222, 226, 226), (60, 58, 56)),
    "purple": ((96, 34, 74), (226, 228, 228)),
}


@dataclass
class Part:
    name: str
    kind: str
    x: int  # box of the body plus leads, in final pixels
    y: int
    w: int
    h: int
    vertical: bool = False
    style: int = 0

    @property
    def box(self):
        return (self.x, self.y, self.w, self.h)


@dataclass
class Board:
    seed: int
    w: int
    h: int
    mask: str
    parts: list = field(default_factory=list)


SIZES = {  # kind: (w, h) ranges in final pixels, horizontal orientation
    "resistor": ((30, 46), (15, 22)),
    "capacitor": ((28, 44), (16, 24)),
    "diode": ((40, 54), (20, 27)),
    "led": ((32, 44), (20, 27)),
    "soic": ((84, 124), (72, 92)),
    "qfp": ((120, 170), (120, 170)),
    "electrolytic": ((66, 104), (66, 104)),
    "inductor": ((62, 92), (62, 92)),
    "crystal": ((96, 120), (36, 46)),
    "header": ((130, 250), (30, 38)),
    "usb": ((110, 140), (84, 104)),
    "button": ((62, 78), (62, 78)),
    "sot": ((44, 54), (42, 52)),
}
PREFIX = {
    "resistor": "R", "capacitor": "C", "diode": "D", "led": "LED", "soic": "U",
    "qfp": "U", "electrolytic": "C", "inductor": "L", "crystal": "Y",
    "header": "J", "usb": "J", "button": "SW", "sot": "Q",
}


def make_board(seed: int, w: int = 1280, h: int = 960, mask: str | None = None,
               density: float | None = None) -> Board:
    r = np.random.default_rng(seed)
    board = Board(seed, w, h, mask or str(r.choice(list(MASKS))))
    wanted = int((density or r.uniform(0.5, 1.0)) * 30)
    big = [k for k in ("qfp", "usb", "header", "soic", "electrolytic", "inductor",
                       "crystal", "button")]
    small = ["resistor", "capacitor", "diode", "led", "sot"]
    kinds = list(r.choice(big, size=max(4, wanted // 3))) + list(
        r.choice(small, size=wanted - wanted // 3, p=[.36, .34, .1, .1, .1]))
    counts: dict[str, int] = {}
    edge, gap = 60, 12
    for kind in kinds:
        (w0, w1), (h0, h1) = SIZES[kind]
        pw, ph = int(r.integers(w0, w1)), int(r.integers(h0, h1))
        if kind in ("qfp", "electrolytic", "inductor", "button"):
            ph = pw
        vert = bool(r.random() < 0.4)
        bw, bh = (ph, pw) if vert else (pw, ph)
        for _ in range(60):
            x = int(r.integers(edge, w - edge - bw))
            y = int(r.integers(edge, h - edge - bh))
            if all(x + bw + gap < q.x or q.x + q.w + gap < x or
                   y + bh + gap < q.y or q.y + q.h + gap < y for q in board.parts):
                p = PREFIX[kind]
                counts[p] = counts.get(p, 0) + 1
                board.parts.append(Part(f"{p}{counts[p]}", kind, x, y, bw, bh, vert,
                                        int(r.integers(0, 4))))
                break
    return board


# ---------------------------------------------------------------- drawing

def _c(v):
    return tuple(int(x) for x in np.clip(v, 0, 255))


def _rect(img, x0, y0, x1, y1, col, radius=0):
    x0, y0, x1, y1 = [int(round(v)) for v in (x0, y0, x1, y1)]
    if radius <= 0:
        cv2.rectangle(img, (x0, y0), (x1, y1), _c(col), -1, cv2.LINE_AA)
        return
    rad = int(min(radius, (x1 - x0) / 2, (y1 - y0) / 2))
    cv2.rectangle(img, (x0 + rad, y0), (x1 - rad, y1), _c(col), -1)
    cv2.rectangle(img, (x0, y0 + rad), (x1, y1 - rad), _c(col), -1)
    for cx, cy in ((x0 + rad, y0 + rad), (x1 - rad, y0 + rad),
                   (x0 + rad, y1 - rad), (x1 - rad, y1 - rad)):
        cv2.circle(img, (cx, cy), rad, _c(col), -1, cv2.LINE_AA)


def _pads(p: Part):
    """Pad rectangles in part-local horizontal coordinates (0..W, 0..H)."""
    W, H = (p.h, p.w) if p.vertical else (p.w, p.h)
    k = p.kind
    if k in ("resistor", "capacitor", "diode", "led", "crystal", "inductor", "electrolytic"):
        pw = max(6, 0.26 * W) if k in ("resistor", "capacitor", "diode", "led") else 0.2 * W
        ph = H if k in ("resistor", "capacitor", "diode", "led") else 0.5 * H
        y = (H - ph) / 2
        return [(0, y, pw, ph), (W - pw, y, pw, ph)]
    if k == "soic":
        n = 4 if W < 100 else 7
        step = W / n
        out = []
        for i in range(n):
            cx = (i + .5) * step
            out += [(cx - step * .22, 0, step * .44, H * .2),
                    (cx - step * .22, H * .8, step * .44, H * .2)]
        return out
    if k == "qfp":
        n = 10
        step, d, o = W * .8 / n, W * .1, W * .1
        out = []
        for i in range(n):
            c = o + (i + .5) * step
            out += [(c - step * .25, 0, step * .5, d), (c - step * .25, H - d, step * .5, d),
                    (0, c - step * .25, d, step * .5), (W - d, c - step * .25, d, step * .5)]
        return out
    if k == "sot":
        return [(W * .08, H * .72, W * .24, H * .28), (W * .68, H * .72, W * .24, H * .28),
                (W * .38, 0, W * .24, H * .28)]
    if k == "button":
        s = W * .2
        return [(0, H * .12, s, s), (W - s, H * .12, s, s), (0, H * .68, s, s), (W - s, H * .68, s, s)]
    if k == "header":
        n = max(3, int(W / 26))
        step = W / n
        return [((i + .5) * step - 7, H / 2 - 7, 14, 14) for i in range(n)]
    if k == "usb":
        return [(0, H * .15, W * .12, H * .2), (0, H * .65, W * .12, H * .2),
                (W * .88, H * .15, W * .12, H * .2), (W * .88, H * .65, W * .12, H * .2)]
    return []


def _local(img, p: Part):
    """A view helper that maps part-local horizontal coords onto the board."""
    def to(x, y):
        return ((p.x + y) * SS, (p.y + x) * SS) if p.vertical else ((p.x + x) * SS, (p.y + y) * SS)

    def rect(x, y, w, h, col, radius=0):
        a, b = to(x, y), to(x + w, y + h)
        _rect(img, min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]), col, radius * SS)
    return to, rect


def _footprint(img, p: Part, silk, r):
    to, rect = _local(img, p)
    W, H = (p.h, p.w) if p.vertical else (p.w, p.h)
    for (x, y, w, h) in _pads(p):
        base = np.array([150, 168, 178]) + r.normal(0, 6, 3)
        if p.kind == "header":
            c = to(x + w / 2, y + h / 2)
            cv2.circle(img, (int(c[0]), int(c[1])), int(7 * SS), _c((96, 170, 205)), -1, cv2.LINE_AA)
            cv2.circle(img, (int(c[0]), int(c[1])), int(3.4 * SS), _c((20, 22, 22)), -1, cv2.LINE_AA)
            continue
        rect(x, y, w, h, base, 1.5)
        rect(x + w * .22, y + h * .18, w * .4, h * .3, base + 48, 1)
    t = max(1, SS)
    a, b = to(-4, -4), to(W + 4, H + 4)
    cv2.rectangle(img, (int(min(a[0], b[0])), int(min(a[1], b[1]))),
                  (int(max(a[0], b[0])), int(max(a[1], b[1]))), _c(silk), t, cv2.LINE_AA)
    if p.kind == "electrolytic":
        c = to(W / 2, H / 2)
        cv2.circle(img, (int(c[0]), int(c[1])), int(W * .5 * SS), _c(silk), t, cv2.LINE_AA)
    cv2.putText(img, p.name, (int(p.x * SS), int((p.y - 7) * SS)), cv2.FONT_HERSHEY_SIMPLEX,
                .42 * SS, _c(silk), t, cv2.LINE_AA)


def _shadow(img, p: Part, strength=.42, grow=5):
    x0, y0 = int((p.x + 2) * SS), int((p.y + 3) * SS)
    x1, y1 = int((p.x + p.w + grow) * SS), int((p.y + p.h + grow) * SS)
    m = 10 * SS
    X0, Y0, X1, Y1 = max(0, x0 - m), max(0, y0 - m), min(img.shape[1], x1 + m), min(img.shape[0], y1 + m)
    a = np.zeros((Y1 - Y0, X1 - X0), np.float32)
    cv2.rectangle(a, (x0 - X0, y0 - Y0), (x1 - X0, y1 - Y0), strength, -1)
    a = cv2.GaussianBlur(a, (0, 0), 3.2 * SS)[..., None]
    roi = img[Y0:Y1, X0:X1].astype(np.float32)
    img[Y0:Y1, X0:X1] = np.clip(roi * (1 - a), 0, 255).astype(np.uint8)


def _mark(img, p: Part, text, scale, col):
    """Laser-marked text, centred, rotated with the part."""
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale * SS, SS)
    pad = 4
    tile = np.zeros((th + 2 * pad, tw + 2 * pad), np.uint8)
    cv2.putText(tile, text, (pad, th + pad), cv2.FONT_HERSHEY_SIMPLEX, scale * SS, 255, max(1, SS - 1), cv2.LINE_AA)
    if p.vertical:
        tile = cv2.rotate(tile, cv2.ROTATE_90_CLOCKWISE)
    h, w = tile.shape
    x, y = int((p.x + p.w / 2) * SS - w / 2), int((p.y + p.h / 2) * SS - h / 2)
    if x < 0 or y < 0 or x + w > img.shape[1] or y + h > img.shape[0]:
        return
    a = (tile.astype(np.float32) / 255)[..., None]
    roi = img[y:y + h, x:x + w].astype(np.float32)
    img[y:y + h, x:x + w] = (roi * (1 - a) + np.array(col, np.float32) * a).astype(np.uint8)


def _part(img, p: Part, r, text_r):
    """Draw one fitted part over its footprint."""
    to, rect = _local(img, p)
    W, H = (p.h, p.w) if p.vertical else (p.w, p.h)
    k = p.kind
    _shadow(img, p, .5 if k in ("electrolytic", "usb", "header", "inductor") else .34,
            9 if k in ("electrolytic", "usb") else 4)
    tin = np.array([176, 186, 190]) + r.normal(0, 5, 3)
    blk = np.array([36, 35, 34]) + r.normal(0, 4)
    code = lambda n: "".join(text_r.choice(list("0123456789ABCDEFKLMNRSTX"), n))
    if k == "resistor":
        rect(0, 0, W, H, tin, 1)
        rect(W * .2, 0, W * .6, H, blk, 0)
        _mark(img, p, code(3), .26, (214, 216, 214))
    elif k == "capacitor":
        rect(0, 0, W, H, tin, 1)
        tan = np.array([(96, 140, 176), (70, 112, 150), (120, 150, 170), (150, 160, 168)][p.style]) + r.normal(0, 5, 3)
        rect(W * .22, 0, W * .56, H, tan, 1)
        rect(W * .26, H * .12, W * .48, H * .2, tan + 24, 1)
    elif k == "diode":
        rect(0, H * .25, W, H * .5, tin, 1)
        rect(W * .14, 0, W * .72, H, blk, 1)
        rect(W * .18, 0, W * .1, H, (190, 192, 192), 0)
    elif k == "led":
        rect(0, H * .1, W, H * .8, tin, 1)
        rect(W * .16, 0, W * .68, H, (216, 226, 228), 2)
        lens = [(90, 210, 240), (80, 90, 235), (110, 220, 120), (240, 190, 120)][p.style]
        c = to(W / 2, H / 2)
        cv2.circle(img, (int(c[0]), int(c[1])), int(H * .3 * SS), _c(lens), -1, cv2.LINE_AA)
        cv2.circle(img, (int(c[0] - 2 * SS), int(c[1] - 2 * SS)), int(H * .1 * SS), (250, 252, 252), -1, cv2.LINE_AA)
    elif k in ("soic", "qfp", "sot"):
        for (x, y, w, h) in _pads(p):
            rect(x, y, w, h, tin, .5)
            rect(x, y, w, h * .35, tin + 30, .5)
        if k == "soic":
            bx = (0, H * .13, W, H * .74)
        elif k == "qfp":
            bx = (W * .07, H * .07, W * .86, H * .86)
        else:
            bx = (0, H * .2, W, H * .6)
        rect(*bx, blk, 2)
        rect(bx[0] + 2, bx[1] + 2, bx[2] - 4, bx[3] * .07, blk + 26, 1)
        if k != "sot":
            c = to(bx[0] + 10, bx[1] + bx[3] - 10)
            cv2.circle(img, (int(c[0]), int(c[1])), int(3.2 * SS), _c(blk + 30), -1, cv2.LINE_AA)
            _mark(img, p, code(7), .36 if k == "soic" else .46, (150, 152, 150))
    elif k == "electrolytic":
        rect(0, H * .04, W, H * .92, blk + 14, 4)
        c = to(W / 2, H / 2)
        c = (int(c[0]), int(c[1]))
        rad = int(W * .47 * SS)
        cv2.circle(img, c, rad, _c((172, 178, 178)), -1, cv2.LINE_AA)
        cv2.circle(img, c, rad, _c((120, 124, 124)), 2 * SS, cv2.LINE_AA)
        cv2.circle(img, (c[0] - rad // 4, c[1] - rad // 4), rad // 2, _c((206, 210, 210)), -1, cv2.LINE_AA)
        cv2.ellipse(img, c, (rad, rad), 0, 60, 120, _c((36, 36, 38)), -1, cv2.LINE_AA)
        cv2.line(img, (c[0] - rad // 2, c[1]), (c[0] + rad // 2, c[1]), _c((140, 144, 144)), SS, cv2.LINE_AA)
        cv2.line(img, (c[0], c[1] - rad // 2), (c[0], c[1] + rad // 2), _c((140, 144, 144)), SS, cv2.LINE_AA)
    elif k == "inductor":
        rect(0, 0, W, H, (58, 60, 62) + r.normal(0, 4, 3), 6)
        c = to(W / 2, H / 2)
        c = (int(c[0]), int(c[1]))
        for i, rad in enumerate(np.linspace(W * .4, W * .12, 7)):
            cv2.circle(img, c, int(rad * SS), _c((40, 92, 168) if i % 2 == 0 else (28, 60, 112)), 2 * SS, cv2.LINE_AA)
    elif k == "crystal":
        rect(0, 0, W, H, (170, 176, 178), H * .45)
        rect(W * .04, H * .1, W * .92, H * .8, (194, 200, 202), H * .4)
        rect(W * .1, H * .16, W * .8, H * .16, (226, 230, 230), 2)
        _mark(img, p, f"{int(text_r.integers(4, 48))}.000", .4, (96, 98, 98))
    elif k == "header":
        rect(0, 0, W, H, blk, 1)
        for (x, y, w, h) in _pads(p):
            rect(x - 2, y - 2, w + 4, h + 4, blk + 14, 1)
            rect(x + 3, y + 3, w - 6, h - 6, (110, 190, 222), .5)
            rect(x + 4, y + 4, 3, 3, (190, 232, 244), 0)
    elif k == "usb":
        rect(0, 0, W, H, (168, 174, 176), 3)
        rect(W * .04, H * .05, W * .92, H * .9, (198, 203, 205), 3)
        rect(W * .14, H * .18, W * .22, H * .1, (132, 137, 139), 1)
        rect(W * .64, H * .18, W * .22, H * .1, (132, 137, 139), 1)
        rect(W * .05, H * .86, W * .9, H * .08, (120, 125, 127), 1)
    elif k == "button":
        rect(0, 0, W, H, (176, 182, 184), 3)
        for dx, dy in ((.12, .12), (.88, .12), (.12, .88), (.88, .88)):
            c = to(W * dx, H * dy)
            cv2.circle(img, (int(c[0]), int(c[1])), int(W * .05 * SS), _c((90, 92, 92)), -1, cv2.LINE_AA)
        c = to(W / 2, H / 2)
        col = [(40, 40, 42), (44, 44, 190), (60, 150, 220), (210, 212, 212)][p.style]
        cv2.circle(img, (int(c[0]), int(c[1])), int(W * .31 * SS), _c(col), -1, cv2.LINE_AA)
        cv2.circle(img, (int(c[0]), int(c[1])), int(W * .31 * SS), _c(np.array(col) * .6), SS, cv2.LINE_AA)


def _base(board: Board):
    """Bare board: mask, hidden copper, traces, vias, holes."""
    r = np.random.default_rng(board.seed * 7 + 1)
    mask, silk = MASKS[board.mask]
    H, W = board.h * SS, board.w * SS
    img = np.full((H, W, 3), (196, 198, 200), np.uint8)  # bench surface
    img = np.clip(img + cv2.resize(r.normal(0, 7, (H // 8, W // 8, 3)), (W, H)), 0, 255).astype(np.uint8)
    e = 22 * SS
    _rect(img, e, e, W - e, H - e, mask, 14 * SS)
    lift = np.array(mask) * 1.0 + (14 if sum(mask) < 400 else -12)
    for _ in range(int(r.integers(2, 5))):  # copper pours under the mask
        x, y = int(r.integers(e, W * .7)), int(r.integers(e, H * .7))
        _rect(img, x, y, min(W - e, x + r.integers(300, 1100)), min(H - e, y + r.integers(250, 800)), lift * .97, 8)
    for _ in range(int(r.integers(60, 120))):  # traces
        x, y = int(r.integers(e + 20, W - e - 20)), int(r.integers(e + 20, H - e - 20))
        th = int(r.choice([3, 4, 6, 10]))
        for _ in range(int(r.integers(2, 5))):
            d = int(r.integers(0, 8)) * np.pi / 4
            L = int(r.integers(40, 260))
            x2 = int(np.clip(x + L * np.cos(d), e + 14, W - e - 14))
            y2 = int(np.clip(y + L * np.sin(d), e + 14, H - e - 14))
            cv2.line(img, (x, y), (x2, y2), _c(lift), th, cv2.LINE_AA)
            x, y = x2, y2
    for _ in range(int(r.integers(50, 130))):  # vias
        x, y = int(r.integers(e + 30, W - e - 30)), int(r.integers(e + 30, H - e - 30))
        cv2.circle(img, (x, y), 5 * SS // 2 + 2, _c(lift + 18), -1, cv2.LINE_AA)
        cv2.circle(img, (x, y), 3, _c(np.array(mask) * .4), -1, cv2.LINE_AA)
    for x, y in ((48, 48), (board.w - 48, 48), (48, board.h - 48), (board.w - 48, board.h - 48)):
        cv2.circle(img, (x * SS, y * SS), 17 * SS, _c((120, 190, 214)), -1, cv2.LINE_AA)
        cv2.circle(img, (x * SS, y * SS), 11 * SS, _c((150, 152, 154)), -1, cv2.LINE_AA)
    return img, silk


def render(board: Board, missing=(), text_seed: int | None = None, wiped=()) -> np.ndarray:
    """The board as built, with the named parts in `missing` left off.

    text_seed re-rolls the markings printed on chips: what an AI editor does
    when it redraws the picture, and what a different batch code does for real.
    Parts in `wiped` are missing too, but their pads and silkscreen are gone as
    well: the way an image editor "removes" something by painting plain board.
    """
    img, silk = _base(board)
    wiped = set(wiped)
    missing = set(missing) | wiped
    for i, p in enumerate(board.parts):
        if p.name not in wiped:
            _footprint(img, p, silk, np.random.default_rng(board.seed * 31 + i))
    for i, p in enumerate(board.parts):
        if p.name not in missing:
            _part(img, p, np.random.default_rng(board.seed * 57 + i),
                  np.random.default_rng((board.seed if text_seed is None else text_seed) * 91 + i))
    return cv2.resize(img, (board.w, board.h), interpolation=cv2.INTER_AREA)


# ---------------------------------------------------------------- camera

@dataclass
class Shot:
    """How one photo differs from the perfect render."""
    shift: float = 0.0      # px
    rotate: float = 0.0     # degrees
    scale: float = 0.0      # fraction
    tilt: float = 0.0       # perspective, px at the corners
    gain: float = 0.0       # brightness, fraction
    gamma: float = 0.0
    tint: float = 0.0       # white balance, fraction per channel
    gradient: float = 0.0   # uneven light across the frame
    shadow: float = 0.0     # soft-edged shadow across the frame
    glare: float = 0.0      # bright reflection spot
    noise: float = 0.0
    blur: float = 0.0
    jpeg: int = 95
    redraw: float = 0.0     # AI-editor drift: local warp + repaint


LEVELS = {
    "easy": Shot(shift=1, rotate=.1, gain=.04, noise=2, jpeg=92),
    "line": Shot(shift=6, rotate=.6, scale=.006, tilt=2, gain=.12, gamma=.08, tint=.04,
                 gradient=.12, noise=4, blur=.5, jpeg=85),
    "harsh": Shot(shift=16, rotate=1.8, scale=.015, tilt=6, gain=.28, gamma=.2, tint=.1,
                  gradient=.3, shadow=.35, glare=.5, noise=8, blur=1.1, jpeg=65),
    "redraw": Shot(shift=4, rotate=.3, scale=.004, tilt=1.5, gain=.1, gamma=.08, tint=.06,
                   gradient=.08, noise=3, blur=.4, jpeg=85, redraw=1.0),
}


def capture(img: np.ndarray, s: Shot, seed: int):
    """Photograph `img`. Returns (photo, H) where H maps board px to photo px."""
    r = np.random.default_rng(seed)
    h, w = img.shape[:2]
    u = lambda a: r.uniform(-a, a) if a else 0.0
    out = img.copy()
    if s.redraw:
        amp, cell = 2.6 * s.redraw, 90
        gh, gw = h // cell + 3, w // cell + 3
        dx = cv2.resize(r.normal(0, amp * .6, (gh, gw)).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
        dy = cv2.resize(r.normal(0, amp * .6, (gh, gw)).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        out = cv2.remap(out, xx + dx, yy + dy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        out = cv2.bilateralFilter(out, 7, 34, 4)
        col = cv2.resize(r.normal(0, 5 * s.redraw, (h // 60, w // 60, 3)).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
        out = np.clip(out.astype(np.float32) + col, 0, 255).astype(np.uint8)
        sharp = cv2.GaussianBlur(out, (0, 0), 1.6)
        out = cv2.addWeighted(out, 1.35, sharp, -.35, 0)
    a, sc = np.deg2rad(u(s.rotate)), 1 + u(s.scale)
    c, d = np.cos(a) * sc, np.sin(a) * sc
    cx, cy = w / 2, h / 2
    M = np.array([[c, -d, cx - c * cx + d * cy + u(s.shift)],
                  [d, c, cy - d * cx - c * cy + u(s.shift)], [0, 0, 1]])
    H = M
    if s.tilt:
        src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
        H = cv2.getPerspectiveTransform(src, src + r.uniform(-s.tilt, s.tilt, (4, 2)).astype(np.float32)) @ M
    out = cv2.warpPerspective(out, H, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    f = out.astype(np.float32) / 255
    if s.gamma:
        f = np.power(f, 1 + u(s.gamma))
    f *= 1 + u(s.gain)
    if s.tint:
        f *= 1 + r.uniform(-s.tint, s.tint, 3).astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    if s.gradient:
        th = r.uniform(0, 2 * np.pi)
        g = ((xx / w - .5) * np.cos(th) + (yy / h - .5) * np.sin(th)) * 2
        f *= (1 + s.gradient * r.uniform(.4, 1) * g)[..., None]
    if s.shadow and r.random() < .7:
        th, off = r.uniform(0, 2 * np.pi), r.uniform(-.25, .25)
        g = (xx / w - .5) * np.cos(th) + (yy / h - .5) * np.sin(th) - off
        f *= (1 - s.shadow * r.uniform(.4, 1) / (1 + np.exp(-g * 26)))[..., None]
    if s.glare and r.random() < .6:
        gx, gy, sg = r.uniform(.1, .9) * w, r.uniform(.1, .9) * h, r.uniform(40, 110)
        f += (s.glare * r.uniform(.3, 1) * np.exp(-((xx - gx) ** 2 + (yy - gy) ** 2) / (2 * sg * sg)))[..., None]
    if s.blur:
        f = cv2.GaussianBlur(f, (0, 0), .25 + r.uniform(0, s.blur))
    if s.noise:
        f += r.normal(0, s.noise / 255 * r.uniform(.5, 1), f.shape).astype(np.float32)
    out = np.clip(f * 255, 0, 255).astype(np.uint8)
    q = int(max(40, min(100, s.jpeg + u(6))))
    out = cv2.imdecode(cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, q])[1], cv2.IMREAD_COLOR)
    return out, H


def in_clutter(img: np.ndarray, seed: int, scale: float = .45):
    """The board held small in a busy photo: a paper bag, a tiled floor, a hand
    over one edge, a cable plugged in. Returns (photo, M) where M maps board px
    to photo px (2x3)."""
    r = np.random.default_rng(seed)
    H, W = 1700, 1000
    out = np.zeros((H, W, 3), np.uint8)
    out[:] = (200, 204, 206)
    for y in range(0, H, 170):  # floor tiles and grout
        cv2.line(out, (0, y + int(r.integers(0, 20))), (W, y + int(r.integers(0, 40))), (150, 155, 158), 3)
    cv2.rectangle(out, (int(r.integers(250, 400)), 0), (W, int(r.integers(600, 900))), (96, 140, 178), -1)  # bag
    cv2.rectangle(out, (0, 0), (int(r.integers(150, 260)), int(r.integers(250, 420))), (40, 42, 48), -1)  # shadow
    h, w = img.shape[:2]
    s = scale * W / w * r.uniform(.9, 1.1)
    a = r.uniform(-4, 4)
    cx, cy = W * r.uniform(.42, .58), H * r.uniform(.4, .55)
    M = cv2.getRotationMatrix2D((w / 2, h / 2), a, s)
    M[:, 2] += (cx - w / 2, cy - h / 2)
    board = cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_AREA)
    inside = cv2.warpAffine(np.full((h, w), 255, np.uint8), M, (W, H), flags=cv2.INTER_NEAREST) > 0
    out[inside] = board[inside]
    # a cable plugged into the bottom edge, then a hand over the left edge
    bottom = M @ np.array([w * r.uniform(.3, .7), h, 1])
    pts = np.array([bottom, bottom + (r.uniform(-60, 60), 300), bottom + (r.uniform(-200, 200), 700)], np.int32)
    cv2.polylines(out, [pts], False, (25, 25, 28), 14)
    left = M @ np.array([0, h * r.uniform(.4, .8), 1])
    cv2.ellipse(out, (int(left[0]) - 60, int(left[1]) + 150), (150, 330), r.uniform(-20, 20), 0, 360, (120, 150, 205), -1)
    out = cv2.GaussianBlur(out, (0, 0), .7)
    out = np.clip(out.astype(np.float32) + r.normal(0, 3, out.shape), 0, 255).astype(np.uint8)
    return out, M
