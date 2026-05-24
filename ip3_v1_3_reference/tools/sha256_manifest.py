#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

EXCLUDE_NAMES = {"sha256_manifest.txt"}
EXCLUDE_DIRS = {".git", "__pycache__", ".pytest_cache"}


def iter_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if path.is_file() and path.name not in EXCLUDE_NAMES:
            yield path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description="Write or verify package SHA-256 manifest.")
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    manifest = root / "evidence" / "sha256_manifest.txt"
    entries = [(sha256_file(p), str(p.relative_to(root)).replace("\\", "/")) for p in iter_files(root)]
    rendered = "".join(f"{digest}  {rel}\n" for digest, rel in entries)
    if args.verify:
        if not manifest.exists():
            print("SHA256_MANIFEST_FAIL missing evidence/sha256_manifest.txt", file=sys.stderr)
            return 2
        actual = manifest.read_text(encoding="utf-8")
        if actual != rendered:
            print("SHA256_MANIFEST_FAIL manifest mismatch", file=sys.stderr)
            return 2
        print(f"SHA256_MANIFEST_VERIFY_OK files={len(entries)}")
        return 0
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"SHA256_MANIFEST_OK files={len(entries)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
