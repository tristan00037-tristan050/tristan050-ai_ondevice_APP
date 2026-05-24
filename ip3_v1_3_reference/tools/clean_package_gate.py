#!/usr/bin/env python3
from __future__ import annotations
import argparse, os, stat, sys
from pathlib import Path
from typing import List

DIRTY_NAMES = {".DS_Store", "Thumbs.db"}
DIRTY_SUFFIXES = {".pyc", ".pyo"}
DIRTY_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache"}


def is_ascii(s: str) -> bool:
    try:
        s.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Check ASCII root and dirty artifact zero.")
    ap.add_argument("root", nargs="?", default=".")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    errors: List[str] = []
    if not is_ascii(root.name):
        errors.append(f"root directory name must be ASCII: {root.name}")
    if " " in root.name:
        errors.append(f"root directory name must not contain spaces: {root.name}")
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        parts = set(rel.parts)
        if path.name.startswith("._"):
            errors.append(f"AppleDouble artifact forbidden: {rel}")
        if path.name in DIRTY_NAMES:
            errors.append(f"dirty file forbidden: {rel}")
        if path.suffix.lower() in DIRTY_SUFFIXES:
            errors.append(f"compiled Python artifact forbidden: {rel}")
        if parts & DIRTY_DIRS:
            errors.append(f"dirty cache directory forbidden: {rel}")
        if path.is_file() and path.suffix.lower() == ".zip":
            errors.append(f"nested zip forbidden inside package root: {rel}")
    if errors:
        for err in errors:
            print(f"CLEAN_PACKAGE_FAIL {err}", file=sys.stderr)
        return 2
    print("CLEAN_PACKAGE_OK")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
