"""The local web server. Listens on this computer only and calls nothing else."""
from __future__ import annotations

import json
import re
from collections import OrderedDict
from pathlib import Path
from typing import Literal

import cv2
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import pinouts
from .decide import CHECK, MISSING, PRESENT, Model
from .imaging import BadPhoto, jpeg, load_image
from .pipeline import Reference, check_photo, visibility
from .store import ID, NotFound, Store
from .suggest import find_parts, suggest_box

HERE = Path(__file__).parent
SAMPLES = HERE.parent / "samples"
PRACTICE = SAMPLES / "boards"
SAFE = r"[\w-]+"
MAX_BYTES = 40 * 1024 * 1024
# The page may load from this server and nowhere else. The browser enforces it.
CSP = ("default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; "
       "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")


class PartIn(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=40)
    x: float
    y: float
    w: float = Field(ge=4)
    h: float = Field(ge=4)


class Point(BaseModel):
    x: float
    y: float


class Rename(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class Split(BaseModel):
    x: float
    y: float
    w: float = Field(gt=0)
    h: float = Field(gt=0)
    pinout: str = Field(max_length=80)
    connector: str = Field(max_length=16)
    corner: Literal["top-left", "top-right", "bottom-right", "bottom-left"] = "top-left"


class Answer(BaseModel):
    part_id: str
    answer: Literal["present", "missing"] | None


def settle(result: dict) -> dict:
    """Photo status from part verdicts, with the operator's answers on top."""
    if result["status"] == "unreadable":
        return result
    final = [p.get("answer") or p["verdict"] for p in result["parts"]]
    result["status"] = "missing" if MISSING in final else "check" if CHECK in final else "ok"
    return result


def create_app(data_dir: Path) -> FastAPI:
    app = FastAPI(title="BoardCheck", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])
    store, model = Store(data_dir), Model.load()
    cache: OrderedDict[tuple, Reference] = OrderedDict()

    def reference(board: dict) -> Reference:
        key = (board["id"], board["rev"])
        if key not in cache:
            img = cv2.imread(str(store.board_dir(board["id"]) / "reference.jpg"))
            cache[key] = Reference(img, board["parts"])
            while len(cache) > 4:
                cache.popitem(last=False)
        cache.move_to_end(key)
        return cache[key]

    async def read(photo: UploadFile) -> bytes:
        data = await photo.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise BadPhoto("This file is over 40 MB. Use a smaller photo.")
        return data

    @app.middleware("http")
    async def headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path.startswith("/api") or request.url.path in ("/", "/app.js", "/app.css"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def unclear(_, e):
        """Say what was wrong in words, not as a list of field paths."""
        said = [str(x.get("msg", "")).removeprefix("Value error, ") for x in e.errors()[:3]]
        return JSONResponse({"detail": "; ".join(said) or "That request was not understood."}, 422)

    @app.exception_handler(BadPhoto)
    async def bad_photo(_, e):
        return JSONResponse({"detail": str(e)}, 422)

    @app.exception_handler(NotFound)
    async def not_found(_, e):
        return JSONResponse({"detail": "Not found. It may have been deleted."}, 404)

    # -- boards
    @app.get("/api/boards")
    def boards():
        return store.boards()

    @app.post("/api/boards")
    async def add_board(photo: UploadFile = File(...), name: str = Form("")):
        img = load_image(await read(photo))
        title = name.strip()[:60] or re.sub(r"\.[^.]*$", "", photo.filename or "").strip()[:60] or "New board"
        return store.create(title, jpeg(img, 95), img.shape[1], img.shape[0])

    @app.get("/api/boards/{bid}")
    def get_board(bid: str):
        return store.board(bid)

    @app.patch("/api/boards/{bid}")
    def rename(bid: str, body: Rename):
        return store.update(bid, name=body.name.strip())

    @app.delete("/api/boards/{bid}")
    def remove(bid: str):
        store.delete(bid)
        return {"ok": True}

    @app.get("/api/boards/{bid}/reference.jpg")
    def reference_image(bid: str):
        return FileResponse(store.board_dir(bid) / "reference.jpg")

    @app.put("/api/boards/{bid}/parts")
    def save_parts(bid: str, parts: list[PartIn]):
        b = store.board(bid)
        seen, clean = set(), []
        for p in parts:
            name = p.name.strip()
            if not name:
                raise HTTPException(422, "Every part needs a name.")
            if name.lower() in seen:
                raise HTTPException(422, f"Two parts are called {name}. Give each part its own name.")
            seen.add(name.lower())
            x, y = max(0.0, p.x), max(0.0, p.y)
            w, h = min(p.w, b["width"] - x), min(p.h, b["height"] - y)
            if w < 4 or h < 4:
                raise HTTPException(422, f"The box for {name} is outside the photo.")
            clean.append(dict(id=p.id, name=name, x=x, y=y, w=w, h=h))
        b = store.update(bid, parts=clean)
        if clean:
            for p, v in zip(b["parts"], visibility(reference(b), model)):
                p["visibility"] = v
        return b

    @app.post("/api/boards/{bid}/suggest")
    def suggest(bid: str, at: Point):
        b = store.board(bid)
        img = cv2.imread(str(store.board_dir(bid) / "reference.jpg"))
        box = suggest_box(img, at.x, at.y, [(p["x"], p["y"], p["w"], p["h"]) for p in b["parts"]])
        return {"box": None if box is None else dict(zip("xywh", map(float, box)))}

    @app.post("/api/boards/{bid}/find")
    def find(bid: str):
        """Every part the app can see, except those already named."""
        b = store.board(bid)
        img = cv2.imread(str(store.board_dir(bid) / "reference.jpg"))
        boxes = find_parts(img, [(p["x"], p["y"], p["w"], p["h"]) for p in b["parts"]])
        return {"boxes": [dict(zip("xywh", map(float, box))) for box in boxes]}

    # -- checks
    @app.get("/api/boards/{bid}/checks")
    def checks(bid: str):
        return store.checks(bid)

    @app.post("/api/boards/{bid}/checks")
    async def add_check(bid: str, photo: UploadFile = File(...)):
        board = store.board(bid)
        if not board["parts"]:
            raise HTTPException(422, "Name at least one part first.")
        img = load_image(await read(photo))
        from starlette.concurrency import run_in_threadpool

        res = await run_in_threadpool(lambda: check_photo(reference(board), img, model))
        named = {p["id"]: p for p in board["parts"]}
        result = dict(
            file=(photo.filename or "photo")[:120], status=res.status, note=res.note,
            quality=round(res.quality, 3), method=res.method, width=img.shape[1], height=img.shape[0],
            parts=[dict(id=p.id, name=p.name, verdict=p.verdict, score=round(p.score, 4), reason=p.reason,
                        quad=[[round(v, 1) for v in c] for c in p.quad],
                        box={k: named[p.id][k] for k in "xywh"}, answer=None) for p in res.parts])
        return store.add_check(bid, result, jpeg(img, 92), jpeg(res.warped, 92))

    @app.patch("/api/boards/{bid}/checks/{cid}")
    def answer(bid: str, cid: str, body: Answer):
        r = store.check(bid, cid)
        for p in r["parts"]:
            if p["id"] == body.part_id:
                p["answer"] = body.answer
                return store.save_check(bid, cid, settle(r))
        raise NotFound(body.part_id)

    @app.delete("/api/boards/{bid}/checks/{cid}")
    def remove_check(bid: str, cid: str):
        store.delete_check(bid, cid)
        return {"ok": True}

    @app.get("/api/boards/{bid}/checks/{cid}/{which}.jpg")
    def check_image(bid: str, cid: str, which: Literal["photo", "aligned"]):
        return FileResponse(store.check_dir(bid, cid) / f"{which}.jpg")

    # -- sample photos shipped with the app, so it can be tried in one click
    @app.get("/api/samples")
    def samples():
        return sorted(p.name for p in SAMPLES.glob("*.jpg")) if SAMPLES.exists() else []

    @app.get("/api/samples/{name}")
    def sample(name: str):
        if not re.fullmatch(r"[\w-]+\.(jpg|json)", name) or not (SAMPLES / name).exists():
            raise NotFound(name)
        return FileResponse(SAMPLES / name)

    # -- pinouts: what each pin of a known connector means
    @app.get("/api/pinouts")
    def list_pinouts():
        return pinouts.all_pinouts(data_dir)

    @app.post("/api/pinouts")
    def teach_pinout(spec: pinouts.PinoutIn):
        return pinouts.teach(data_dir, spec)

    @app.delete("/api/pinouts/{pid}")
    def forget_pinout(pid: str):
        if not pinouts.forget(data_dir, pid):
            raise HTTPException(404, "Only boards you taught can be deleted, and this one was not found.")
        return {"ok": True}

    @app.post("/api/pinouts/split")
    def split_pins(body: Split):
        board = pinouts.find(data_dir, body.pinout)
        conn = next((c for c in board["connectors"] if c["id"] == body.connector), None) if board else None
        if conn is None:
            raise NotFound(body.connector)
        box = (body.x, body.y, body.w, body.h)
        if not pinouts.pin_count_fits(box, conn):
            raise HTTPException(422, f"This box is too small for {len(conn['pins'])} pins. Zoom in and draw it around the whole connector.")
        return {"pins": pinouts.split(box, conn, body.corner)}

    # -- practice boards: parts already named, photos with known answers
    @app.get("/api/practice")
    def practice():
        out = []
        for d in sorted(PRACTICE.iterdir()) if PRACTICE.is_dir() else []:
            if re.fullmatch(SAFE, d.name) and (d / "parts.json").exists() and (d / "reference.jpg").exists():
                out.append(dict(id=d.name, name=json.loads((d / "parts.json").read_text())["name"],
                                photos=sorted(p.name for p in d.glob("[0-9]*.jpg"))))
        return out

    @app.get("/api/practice/{pid}/{name}")
    def practice_file(pid: str, name: str):
        if not re.fullmatch(SAFE, pid) or not re.fullmatch(r"[\w-]+\.(jpg|json)", name) or not (PRACTICE / pid / name).exists():
            raise NotFound(name)
        return FileResponse(PRACTICE / pid / name)

    app.mount("/", StaticFiles(directory=HERE / "static", html=True), name="static")
    return app


__all__ = ["create_app", "PRESENT", "CHECK", "MISSING", "ID"]
