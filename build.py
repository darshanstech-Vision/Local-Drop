"""Reproducible Windows bundle with an isolated DLL search path."""
import argparse
import os
from pathlib import Path
import sys


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", default=str(root / "dist"))
    parser.add_argument("--work", default=str(root / "build"))
    args = parser.parse_args()
    windows = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    # Foreign ICU/Qt/OpenSSL DLLs on PATH can silently contaminate a build.
    os.environ["PATH"] = os.pathsep.join(map(str, [Path(sys.executable).parent,
        windows / "System32", windows, windows / "System32/WindowsPowerShell/v1.0"]))
    from PyInstaller.__main__ import run
    run(["--noconfirm", "--clean", "--windowed", "--onedir", "--name", "LocalDrop",
         "--distpath", args.dist, "--workpath", args.work, "--specpath", args.work,
         str(root / "run.py")])


if __name__ == "__main__":
    main()
