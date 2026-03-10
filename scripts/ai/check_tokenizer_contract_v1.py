#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

def main() -> None:
    tokenizer_path = Path("packs/micro_default/tokenizer.json")
    if not tokenizer_path.exists():
        raise SystemExit("TOKENIZER_JSON_MISSING")
    data = json.loads(tokenizer_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("TOKENIZER_JSON_INVALID")
    print("TOKENIZER_CONTRACT_PRECHECK_OK=1")

if __name__ == "__main__":
    main()
