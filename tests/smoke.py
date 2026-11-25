"""Starts the app the way a user does, checks the sample photos, compares the answers.

  python tests/smoke.py            uses run.sh, or run.bat on Windows
  python tests/smoke.py --python   starts "python -m boardcheck" directly

Not part of the unit tests: the first run may install packages.
"""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).parent.parent
SAMPLES = ROOT / "samples"
PORT = 8399
URL = f"http://127.0.0.1:{PORT}"


def start(data):
    if "--python" in sys.argv:
        cmd = [sys.executable, "-m", "boardcheck"]
    else:
        cmd = ["cmd", "/c", "run.bat"] if os.name == "nt" else ["./run.sh"]
    own_group = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    return subprocess.Popen([*cmd, "--no-browser", "--port", str(PORT), "--data", data], cwd=ROOT, **own_group)


def stop(app):
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(app.pid)], capture_output=True)
    else:
        os.killpg(app.pid, signal.SIGTERM)
    app.wait(20)


def call(method, path, body=None, photo=None):
    headers, data = {}, None
    if photo:
        b = uuid.uuid4().hex
        data = (f'--{b}\r\nContent-Disposition: form-data; name="photo"; filename="{photo.name}"\r\n'
                "Content-Type: image/jpeg\r\n\r\n").encode() + photo.read_bytes() + f"\r\n--{b}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={b}"
    elif body is not None:
        data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
    req = urllib.request.Request(URL + path, data, headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def wait(app, limit):
    """The first run installs packages, so this can take minutes."""
    began = time.time()
    while time.time() - began < limit:
        if app.poll() is not None:
            raise SystemExit(f"The app stopped by itself with code {app.returncode}.")
        try:
            urllib.request.urlopen(URL, timeout=2).read()
            return time.time() - began
        except OSError:
            time.sleep(.5)
    raise SystemExit(f"The app did not answer within {limit} s.")


def main():
    answers = json.loads((SAMPLES / "parts.json").read_text())
    wrong = 0
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as data:
        app = start(data)
        try:
            print(f"app answered after {wait(app, 600):.0f} s")
            board = call("POST", "/api/boards", photo=SAMPLES / "reference.jpg")
            parts = [dict(id=f"p{i}", **p) for i, p in enumerate(answers["parts"])]
            call("PUT", f"/api/boards/{board['id']}/parts", parts)
            for name, gone in answers["missing"].items():
                r = call("POST", f"/api/boards/{board['id']}/checks", photo=SAMPLES / f"{name}.jpg")
                said = sorted(p["name"] for p in r["parts"] if p["verdict"] == "missing")
                unsure = sorted(p["name"] for p in r["parts"] if p["verdict"] == "check")
                # Harsh light is the sample for "check by eye": the app may ask for a
                # look, but exactly the missing part must be flagged, either way.
                good = sorted(said + unsure) == sorted(gone) if "harsh" in name else said == sorted(gone) and not unsure
                wrong += not good
                print(f"{'ok   ' if good else 'WRONG'} {name}: missing {said or 'nothing'}"
                      + (f", unsure about {unsure}" if unsure else "") + ("" if good else f", expected {sorted(gone)}"))
        finally:
            stop(app)
    raise SystemExit(1 if wrong else 0)


if __name__ == "__main__":
    main()
