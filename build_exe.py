#!/usr/bin/env python3
"""Build a standalone executable using PyInstaller.

Usage:
    python build_exe.py          # builds dist/long-xls.exe (Windows) or dist/long-xls
    python build_exe.py --onedir # builds dist/long-xls/ directory bundle

Requires: pip install pyinstaller
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
ENTRY = HERE / "src" / "long_xls" / "cli.py"


def main():
    onedir = "--onedir" in sys.argv

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "long-xls",
        "--noconfirm",
        "--clean",
        "--paths", str(HERE / "src"),
    ]

    if onedir:
        cmd.append("--onedir")
    else:
        cmd.append("--onefile")

    cmd.append(str(ENTRY))

    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

    if onedir:
        print(f"\nDone: dist/long-xls/")
    else:
        exe_name = "long-xls.exe" if sys.platform == "win32" else "long-xls"
        print(f"\nDone: dist/{exe_name}")


if __name__ == "__main__":
    main()
