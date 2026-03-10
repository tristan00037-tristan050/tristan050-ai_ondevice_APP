#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

PACK_DIR = Path("packs/small_default")
PACK_DIR.mkdir(parents=True, exist_ok=True)

if __name__ == "__main__":
    print("build_small_default_v1.py prepared")
