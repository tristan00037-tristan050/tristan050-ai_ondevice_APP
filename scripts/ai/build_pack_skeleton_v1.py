#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path

PACKS = ["micro_default", "small_default"]

def ensure_file(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(content, encoding="utf-8")

def main() -> None:
    for pack in PACKS:
        pack_dir = Path("packs") / pack
        pack_dir.mkdir(parents=True, exist_ok=True)
        ensure_file(pack_dir / "tokenizer.json", "{}\n")
        ensure_file(pack_dir / "config.json", "{}\n")
        ensure_file(pack_dir / "chat_template.jinja", "{# algorithm-team placeholder #}\n")
    print("PACK_SKELETON_PREPARED=1")

if __name__ == "__main__":
    main()
