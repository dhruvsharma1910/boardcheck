"""Builds one zip that installs and runs with no internet at all.

  python tools/bundle.py          writes dist/BoardCheck-<system>.zip

The zip holds the app and the packages it needs, for the system this is run on.
"""
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
TAKE = ["run.bat" if sys.platform == "win32" else "run.sh", "requirements.txt", "README.md", "boardcheck", "samples"]
PYTHONS = ["3.12", "3.13"]
SYSTEM = {"Darwin": "mac", "Windows": "windows", "Linux": "linux"}[platform.system()] + "-" + platform.machine().lower()


def main():
    out = ROOT / "dist" / f"BoardCheck-{SYSTEM}.zip"
    out.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp) / "BoardCheck"
        home.mkdir()
        for name in TAKE:
            src = ROOT / name
            if src.is_dir():
                shutil.copytree(src, home / name, ignore=shutil.ignore_patterns("__pycache__"))
            else:
                shutil.copy2(src, home / name)
        for py in PYTHONS:
            subprocess.run([sys.executable, "-m", "pip", "download", "-q", "--disable-pip-version-check", "--only-binary=:all:",
                            "--python-version", py, "-r", str(ROOT / "requirements.txt"), "-d", str(home / "wheels")], check=True)
        # ZipFile keeps the "may be run" bit of run.sh, so unzip gives a script that starts.
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(p for p in home.rglob("*") if p.is_file()):
                z.write(f, f.relative_to(tmp))
    print(out.name, f"{out.stat().st_size / 1e6:.0f} MB")


if __name__ == "__main__":
    main()
