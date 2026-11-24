@echo off
rem Windows: sets up once (needs internet), then runs offline.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo First run: installing what BoardCheck needs. This needs internet once.
  py -3 -m venv .venv || exit /b 1
  .venv\Scripts\python -m pip install -q -r requirements.txt || exit /b 1
)
.venv\Scripts\python -m boardcheck %*
