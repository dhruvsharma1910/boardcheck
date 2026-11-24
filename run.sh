#!/bin/sh
# Mac and Linux: sets up once (needs internet), then runs offline.
cd "$(dirname "$0")" || exit 1
PY=$(command -v python3.12 || command -v python3)
[ -n "$PY" ] || { echo "Python 3.12 or newer is needed: https://www.python.org/downloads/"; exit 1; }
if [ ! -x .venv/bin/python ] || ! .venv/bin/python -c "import cv2, fastapi, uvicorn, multipart, PIL" 2>/dev/null; then
  echo "First run: installing what BoardCheck needs. This needs internet once."
  "$PY" -m venv .venv && .venv/bin/python -m pip install -q -r requirements.txt || exit 1
fi
exec .venv/bin/python -m boardcheck "$@"
