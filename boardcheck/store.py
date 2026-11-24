"""Boards and checks as plain files under data/. No database to install.

  data/boards/<id>/board.json       name, parts, revision
  data/boards/<id>/reference.jpg    the good board
  data/boards/<id>/checks/<id>/     photo.jpg, aligned.jpg, result.json
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path

ID = re.compile(r"^[0-9a-f]{12}$")


class NotFound(KeyError):
    pass


def new_id() -> str:
    return uuid.uuid4().hex[:12]


class Store:
    def __init__(self, root: Path):
        self.root = Path(root) / "boards"
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    # -- paths: ids are checked, so a request can never climb out of data/
    def board_dir(self, bid: str) -> Path:
        d = self.root / bid
        if not ID.match(bid) or not (d / "board.json").exists():
            raise NotFound(bid)
        return d

    def check_dir(self, bid: str, cid: str) -> Path:
        d = self.board_dir(bid) / "checks" / cid
        if not ID.match(cid) or not (d / "result.json").exists():
            raise NotFound(cid)
        return d

    @staticmethod
    def _write(path: Path, obj):
        """Write to a temp file and swap it in, so a crash never leaves half a file."""
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, indent=1)
        os.replace(tmp, path)

    # -- boards
    def create(self, name: str, jpg: bytes, width: int, height: int) -> dict:
        bid = new_id()
        d = self.root / bid
        (d / "checks").mkdir(parents=True)
        (d / "reference.jpg").write_bytes(jpg)
        board = dict(id=bid, name=name, width=width, height=height, created=time.time(), rev=0, parts=[])
        self._write(d / "board.json", board)
        return board

    def board(self, bid: str) -> dict:
        return json.loads((self.board_dir(bid) / "board.json").read_text())

    def boards(self) -> list[dict]:
        out = []
        for d in self.root.iterdir():
            if (d / "board.json").exists():
                b = json.loads((d / "board.json").read_text())
                out.append(dict(id=b["id"], name=b["name"], created=b["created"], parts=len(b["parts"])))
        return sorted(out, key=lambda b: -b["created"])

    def update(self, bid: str, **changes) -> dict:
        with self.lock:
            b = self.board(bid)
            b.update(changes)
            if "parts" in changes:
                b["rev"] += 1
            self._write(self.board_dir(bid) / "board.json", b)
            return b

    def delete(self, bid: str):
        shutil.rmtree(self.board_dir(bid))

    # -- checks
    def add_check(self, bid: str, result: dict, photo: bytes, aligned: bytes) -> dict:
        cid = new_id()
        d = self.board_dir(bid) / "checks" / cid
        d.mkdir(parents=True)
        (d / "photo.jpg").write_bytes(photo)
        (d / "aligned.jpg").write_bytes(aligned)
        result = dict(result, id=cid, time=time.time())
        self._write(d / "result.json", result)
        return result

    def checks(self, bid: str) -> list[dict]:
        d = self.board_dir(bid) / "checks"
        out = [json.loads(p.read_text()) for p in d.glob("*/result.json")]
        return sorted(out, key=lambda c: c["time"])

    def check(self, bid: str, cid: str) -> dict:
        return json.loads((self.check_dir(bid, cid) / "result.json").read_text())

    def save_check(self, bid: str, cid: str, result: dict) -> dict:
        with self.lock:
            self._write(self.check_dir(bid, cid) / "result.json", result)
        return result

    def delete_check(self, bid: str, cid: str):
        shutil.rmtree(self.check_dir(bid, cid))
