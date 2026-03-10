#!/usr/bin/env python3
from __future__ import annotations
import hashlib
from pathlib import Path

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        h.update(f.read())
    return h.hexdigest()

def main() -> None:
    template = Path("packs/micro_default/chat_template.jinja")
    if not template.exists():
        raise SystemExit("CHAT_TEMPLATE_MISSING")
    digest = sha256_file(template)
    print(f"CHAT_TEMPLATE_DIGEST_SHA256={digest}")

if __name__ == "__main__":
    main()
