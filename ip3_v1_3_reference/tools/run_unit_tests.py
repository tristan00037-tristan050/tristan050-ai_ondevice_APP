#!/usr/bin/env python3
from __future__ import annotations
import subprocess, sys
from pathlib import Path

def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    cmd = [sys.executable, "-m", "unittest", "discover", "-s", str(root / "tests"), "-p", "test*.py"]
    proc = subprocess.run(cmd, cwd=root)
    if proc.returncode != 0:
        return proc.returncode
    print("UNIT_TESTS_OK")
    return 0
if __name__ == "__main__": raise SystemExit(main())
