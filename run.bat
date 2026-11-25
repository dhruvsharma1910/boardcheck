@echo off
rem Windows: sets up once, then runs offline.
rem If there is a wheels folder next to this file, even the set-up needs no internet.
setlocal
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python -c "import cv2, fastapi, uvicorn, multipart, PIL, pillow_heif" 2>nul && goto run
)
set "PY="
for %%c in ("py -3.12" "py -3.13" "py -3.14" "py -3" "python") do (
  if not defined PY (
    %%~c -c "import sys; sys.exit(sys.version_info < (3, 12))" >nul 2>nul && set "PY=%%~c"
  )
)
if not defined PY (
  echo BoardCheck needs Python 3.12 or newer, and none was found on this computer.
  echo Install it from https://www.python.org/downloads/ and run this again.
  pause
  exit /b 1
)
%PY% -m venv --clear .venv || exit /b 1
if exist wheels (
  echo First run: installing from the wheels folder. No internet needed.
  .venv\Scripts\python -m pip install -q --disable-pip-version-check --no-index --find-links wheels -r requirements.txt && goto run
  echo That did not work with this Python. Trying the internet instead.
) else (
  echo First run: installing what BoardCheck needs. This needs internet once.
)
.venv\Scripts\python -m pip install -q --disable-pip-version-check -r requirements.txt || exit /b 1
:run
.venv\Scripts\python -m boardcheck %*
