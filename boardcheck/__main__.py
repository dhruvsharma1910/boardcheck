"""python -m boardcheck   starts the app and opens the browser."""
from __future__ import annotations

import argparse
import socket
import threading
import webbrowser
from pathlib import Path

import uvicorn

from .server import create_app


def free_port(wanted: int) -> int:
    for port in range(wanted, wanted + 20):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise SystemExit("No free port found.")


def main():
    ap = argparse.ArgumentParser(prog="boardcheck", description="Find missing parts on a circuit board.")
    ap.add_argument("--port", type=int, default=8321)
    ap.add_argument("--data", type=Path, default=Path(__file__).parent.parent / "data")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    port = free_port(a.port)
    url = f"http://127.0.0.1:{port}"
    print(f"\n  BoardCheck is running at {url}\n  Close this window or press Ctrl+C to stop it.\n")
    if not a.no_browser:
        threading.Timer(1.0, webbrowser.open, [url]).start()
    uvicorn.run(create_app(a.data), host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
