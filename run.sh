#!/bin/sh
# Mac and Linux: sets up once, then runs offline.
# If there is a wheels/ folder next to this file, even the set-up needs no internet.
cd "$(dirname "$0")" || exit 1
NEEDS="import sys; sys.exit(sys.version_info < (3, 12))"
PY=
for c in python3.12 python3.13 python3.14 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c "$NEEDS" 2>/dev/null; then PY=$c; break; fi
done
if [ ! -x .venv/bin/python ] || ! .venv/bin/python -c "import cv2, fastapi, uvicorn, multipart, PIL, pillow_heif" 2>/dev/null; then
  if [ -z "$PY" ]; then
    echo "BoardCheck needs Python 3.12 or newer, and none was found on this computer."
    echo "Install it from https://www.python.org/downloads/ and run this again."
    exit 1
  fi
  "$PY" -m venv --clear .venv || exit 1
  install() { .venv/bin/python -m pip install -q --disable-pip-version-check "$@" -r requirements.txt; }
  if [ -d wheels ]; then
    echo "First run: installing from the wheels folder. No internet needed."
    install --no-index --find-links wheels || { echo "That did not work with this Python. Trying the internet instead."; install; } || exit 1
  else
    echo "First run: installing what BoardCheck needs. This needs internet once."
    install || exit 1
  fi
fi
exec .venv/bin/python -m boardcheck "$@"
