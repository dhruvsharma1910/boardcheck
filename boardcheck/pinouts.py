"""What each pin of a connector means, and where each pin sits in a box.

A pinout is a board (Arduino Uno, Basys 3, ...) with its connectors. Built-in
pinouts live in boardcheck/pinouts/ and were copied from the makers' own
documents (each file names its sources). Boards the user teaches are saved in
the data folder, next to their saved boards.

Nothing here knows where a connector is on a photo. The user boxes it and says
which connector it is and which corner pin 1 is in; split() then divides the
box into pins using the connector's standard arrangement.
"""
from __future__ import annotations

import json
import re
import secrets
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

BUILT_IN = Path(__file__).with_name("pinouts")
LAYOUTS = ("row", "pmod", "dual", "dip")
CORNERS = ("top-left", "top-right", "bottom-right", "bottom-left")


class PinIn(BaseModel):
    name: str = Field(min_length=1, max_length=24)
    meaning: str = Field(default="", max_length=40)


class ConnectorIn(BaseModel):
    id: str = Field(min_length=1, max_length=16)
    name: str = Field(default="", max_length=80)
    layout: Literal["row", "pmod", "dual", "dip"]
    pins: list[PinIn] = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def _fits(self):
        if self.layout != "row" and len(self.pins) % 2:
            raise ValueError(f"{self.id}: two rows need an even number of pins")
        names = [p.name.strip().lower() for p in self.pins]
        if len(set(names)) != len(names):
            raise ValueError(f"{self.id}: two pins have the same name")
        return self


class PinoutIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    connectors: list[ConnectorIn] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def _unique(self):
        ids = [c.id.strip().lower() for c in self.connectors]
        if len(set(ids)) != len(ids):
            raise ValueError("two connectors have the same name")
        return self


def _read(path: Path, built_in: bool) -> dict:
    d = json.loads(path.read_text())
    PinoutIn.model_validate({"name": d["name"], "connectors": [
        dict(c, pins=[{"name": n, "meaning": m} for n, m in c["pins"]]) for c in d["connectors"]]})
    return dict(id=path.stem, name=d["name"], built_in=built_in, sources=d.get("sources", []),
                note=d.get("note", ""), connectors=d["connectors"])


def all_pinouts(data_dir: Path) -> list[dict]:
    out = [_read(p, True) for p in sorted(BUILT_IN.glob("*.json"))]
    taught = data_dir / "pinouts"
    out += [_read(p, False) for p in sorted(taught.glob("*.json"))] if taught.is_dir() else []
    return out


def find(data_dir: Path, pid: str) -> dict | None:
    return next((p for p in all_pinouts(data_dir) if p["id"] == pid), None)


def teach(data_dir: Path, spec: PinoutIn) -> dict:
    """Save a board the user described. Returns it as all_pinouts() would."""
    slug = re.sub(r"[^a-z0-9]+", "-", spec.name.lower()).strip("-")[:30] or "board"
    pid = f"taught-{slug}-{secrets.token_hex(3)}"
    folder = data_dir / "pinouts"
    folder.mkdir(parents=True, exist_ok=True)
    body = dict(name=spec.name.strip(), sources=["taught in BoardCheck"], connectors=[
        dict(id=c.id.strip(), name=c.name.strip(), layout=c.layout,
             pins=[[p.name.strip(), p.meaning.strip()] for p in c.pins]) for c in spec.connectors])
    (folder / f"{pid}.json").write_text(json.dumps(body, indent=1))
    return _read(folder / f"{pid}.json", False)


def forget(data_dir: Path, pid: str) -> bool:
    """Delete a taught board. Built-in boards cannot be deleted."""
    if not re.fullmatch(r"taught-[a-z0-9-]+", pid):
        return False
    path = data_dir / "pinouts" / f"{pid}.json"
    if not path.exists():
        return False
    path.unlink()
    return True


def label(name: str, meaning: str) -> str:
    """The part name a pin gets: its name, and what it means if that adds anything."""
    text = name if not meaning or meaning.lower() == name.lower() else f"{name} = {meaning}"
    return text[:40]


def _cell(layout: str, i: int, n: int) -> tuple[int, int]:
    """(column, row) of pin i (0-based), with pin 1 at column 0, row 0."""
    cols = n if layout == "row" else n // 2
    if layout == "row":
        return i, 0
    if layout == "pmod":   # 1..n/2 along one row, the rest along the other, same direction
        return (i, 0) if i < cols else (i - cols, 1)
    if layout == "dual":   # 1 and 2 side by side across the rows, then 3 and 4, ...
        return i // 2, i % 2
    return (i, 0) if i < cols else (n - 1 - i, 1)  # dip: down one side, back up the other


def split(box, connector: dict, corner: str = "top-left") -> list[dict]:
    """Divide a box drawn around a connector into one box per pin.

    The pins run along the box's longer side. `corner` says where pin 1 is.
    For a chip ("dip"), the pins are the two strips along the long sides.
    """
    if corner not in CORNERS:
        raise ValueError("corner must be one of " + ", ".join(CORNERS))
    x, y, w, h = map(float, box)
    pins, layout = connector["pins"], connector["layout"]
    n = len(pins)
    rows = 1 if layout == "row" else 2
    cols = n if rows == 1 else n // 2
    flat = w >= h
    long_, short = (w, h) if flat else (h, w)
    step, band = long_ / cols, short / rows
    if layout == "dip":
        band = short * .25
    right, bottom = corner.endswith("right"), corner.startswith("bottom")
    flip_col, flip_row = (right, bottom) if flat else (bottom, right)
    out = []
    for i, (name, meaning) in enumerate(pins):
        c, r = _cell(layout, i, n)
        c = cols - 1 - c if flip_col else c
        r = rows - 1 - r if flip_row else r
        u = c * step + .08 * step
        v = (r * band if layout != "dip" else (0 if r == 0 else short - band)) + .08 * band
        du, dv = .84 * step, .84 * band
        px, py, pw, ph = (x + u, y + v, du, dv) if flat else (x + v, y + u, dv, du)
        out.append(dict(name=label(name, meaning), pin=name, meaning=meaning, x=px, y=py, w=pw, h=ph))
    return out


def pin_count_fits(box, connector: dict, smallest: float = 4.0) -> bool:
    x, y, w, h = box
    n = len(connector["pins"])
    cols = n if connector["layout"] == "row" else n // 2
    rows = 1 if connector["layout"] == "row" else 2
    long_, short = max(w, h), min(w, h)
    band = short * .25 if connector["layout"] == "dip" else short / rows
    return .84 * long_ / max(1, cols) >= smallest and .84 * band >= smallest


__all__ = ["PinIn", "ConnectorIn", "PinoutIn", "all_pinouts", "find", "teach", "forget", "split",
           "pin_count_fits", "label", "LAYOUTS", "CORNERS"]
