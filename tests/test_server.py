"""The real server on a real port, driven over HTTP like the browser does."""
import json
import re
import socket
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import cv2
import uvicorn

from bench import synth
from boardcheck.server import create_app

STATIC = Path(__file__).parent.parent / "boardcheck" / "static"


class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            cls.port = s.getsockname()[1]
        cls.server = uvicorn.Server(uvicorn.Config(create_app(Path(cls.tmp.name)), host="127.0.0.1", port=cls.port, log_level="error"))
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()
        while not cls.server.started:
            time.sleep(.05)
        cls.board = synth.make_board(77, mask="blue")
        cls.good = cv2.imencode(".jpg", synth.render(cls.board))[1].tobytes()
        cls.gone = cls.board.parts[1].name
        cls.bad = cv2.imencode(".jpg", synth.render(cls.board, [cls.gone]))[1].tobytes()

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(5)
        cls.tmp.cleanup()

    def call(self, method, path, body=None, files=None, host=None):
        headers, data = {}, None
        if files:
            b = uuid.uuid4().hex
            data = b"".join(f'--{b}\r\nContent-Disposition: form-data; name="photo"; filename="{n}"\r\n'
                            f"Content-Type: application/octet-stream\r\n\r\n".encode() + c + b"\r\n" for n, c in files) + f"--{b}--\r\n".encode()
            headers["Content-Type"] = f"multipart/form-data; boundary={b}"
        elif body is not None:
            data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
        if host:
            headers["Host"] = host
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data, headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw, code, head = r.read(), r.status, r.headers
        except urllib.error.HTTPError as e:
            raw, code, head = e.read(), e.code, e.headers
        try:
            return code, json.loads(raw), head
        except ValueError:
            return code, raw, head

    def new_board(self, named=True):
        _, b, _ = self.call("POST", "/api/boards", files=[("good.jpg", self.good)])
        if named:
            parts = [dict(id=p.name, name=p.name, x=p.x, y=p.y, w=p.w, h=p.h) for p in self.board.parts]
            code, b, _ = self.call("PUT", f"/api/boards/{b['id']}/parts", parts)
            self.assertEqual(code, 200)
        return b

    def test_whole_demo(self):
        b = self.new_board()
        self.assertEqual(b["name"], "good")
        _, ok, _ = self.call("POST", f"/api/boards/{b['id']}/checks", files=[("1.jpg", self.good)])
        _, bad, _ = self.call("POST", f"/api/boards/{b['id']}/checks", files=[("2.jpg", self.bad)])
        self.assertEqual(ok["status"], "ok")
        self.assertEqual(bad["status"], "missing")
        self.assertEqual([p["name"] for p in bad["parts"] if p["verdict"] == "missing"], [self.gone])
        # names survive: the board and its checks are read back from disk
        self.assertEqual(len(self.call("GET", f"/api/boards/{b['id']}")[1]["parts"]), len(self.board.parts))
        self.assertEqual(len(self.call("GET", f"/api/boards/{b['id']}/checks")[1]), 2)
        for which in ("photo", "aligned"):
            code, raw, head = self.call("GET", f"/api/boards/{b['id']}/checks/{bad['id']}/{which}.jpg")
            self.assertEqual((code, head["Content-Type"]), (200, "image/jpeg"))

    def test_operator_answer_changes_the_result_and_can_be_undone(self):
        b = self.new_board()
        _, c, _ = self.call("POST", f"/api/boards/{b['id']}/checks", files=[("2.jpg", self.bad)])
        pid = next(p["id"] for p in c["parts"] if p["verdict"] == "missing")
        url = f"/api/boards/{b['id']}/checks/{c['id']}"
        self.assertEqual(self.call("PATCH", url, dict(part_id=pid, answer="present"))[1]["status"], "ok")
        self.assertEqual(self.call("PATCH", url, dict(part_id=pid, answer=None))[1]["status"], "missing")

    def test_naming_rules(self):
        b = self.new_board(named=False)
        url = f"/api/boards/{b['id']}/parts"
        box = dict(x=10, y=10, w=40, h=40)
        self.assertEqual(self.call("PUT", url, [dict(id="a", name="R1", **box), dict(id="b", name="r1 ", **box)])[0], 422)
        self.assertEqual(self.call("PUT", url, [dict(id="a", name="   ", **box)])[0], 422)
        self.assertEqual(self.call("PUT", url, [dict(id="a", name="R1", x=9000, y=10, w=40, h=40)])[0], 422)
        self.assertEqual(self.call("POST", f"/api/boards/{b['id']}/checks", files=[("1.jpg", self.good)])[0], 422)

    def test_bad_upload_gets_a_plain_message(self):
        code, body, _ = self.call("POST", "/api/boards", files=[("x.jpg", b"hello")])
        self.assertEqual(code, 422)
        self.assertIn("could not be read", body["detail"])

    def test_click_suggests_a_box(self):
        b = self.new_board(named=False)
        p = self.board.parts[0]
        _, r, _ = self.call("POST", f"/api/boards/{b['id']}/suggest", dict(x=p.x + p.w / 2, y=p.y + p.h / 2))
        self.assertIsNotNone(r["box"])

    def test_cannot_climb_out_of_the_data_folder(self):
        for path in ("/api/boards/..%2f..%2fetc", "/api/boards/zzzzzzzzzzzz", "/api/samples/..%2fREADME.md",
                     "/api/boards/000000000000/reference.jpg", "/../requirements.txt"):
            self.assertIn(self.call("GET", path)[0], (404, 405), path)

    def test_other_websites_cannot_talk_to_it(self):
        self.assertEqual(self.call("GET", "/api/boards", host="evil.example")[0], 400)

    def test_delete(self):
        b = self.new_board()
        self.assertEqual(self.call("DELETE", f"/api/boards/{b['id']}")[0], 200)
        self.assertEqual(self.call("GET", f"/api/boards/{b['id']}")[0], 404)

    def test_works_with_no_network(self):
        """Any attempt to reach another machine during a full check fails the test."""
        tried = []
        real = socket.socket.connect
        def guard(sock, addr):
            if sock.family in (socket.AF_INET, socket.AF_INET6) and addr[0] not in ("127.0.0.1", "::1", "localhost"):
                tried.append(addr)
                raise OSError("network is off")
            return real(sock, addr)
        socket.socket.connect = guard
        try:
            self.test_whole_demo()
        finally:
            socket.socket.connect = real
        self.assertEqual(tried, [])

    def test_page_loads_nothing_from_elsewhere(self):
        _, _, head = self.call("GET", "/")
        self.assertIn("default-src 'self'", head["Content-Security-Policy"])
        for f in STATIC.iterdir():
            urls = [u for u in re.findall(r"https?://[^\s\"'`)]+", f.read_text()) if not u.startswith("http://www.w3.org/")]
            self.assertEqual(urls, [], f.name)


if __name__ == "__main__":
    unittest.main()
