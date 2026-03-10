#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

try:
    from .common_pack_build_v1 import ensure_dir, safe_print_kv, write_json
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from common_pack_build_v1 import ensure_dir, safe_print_kv, write_json


def main() -> None:
    tokenizer_path = Path("packs/micro_default/tokenizer.json")
    if not tokenizer_path.exists():
        raise SystemExit("TOKENIZER_JSON_MISSING")

    try:
        data = json.loads(tokenizer_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise SystemExit("TOKENIZER_JSON_PARSE_ERROR")

    facts = {
        "vocab_size": data.get("model", {}).get("vocab_size") or len(data.get("vocab", {})),
        "bos_token": data.get("bos_token"),
        "eos_token": data.get("eos_token"),
    }
    out_dir = Path("tmp")
    ensure_dir(out_dir)
    write_json(out_dir / "tokenizer_facts.json", facts)
    safe_print_kv("TOKENIZER_FACTS_EXTRACTED", "1")


if __name__ == "__main__":
    main()
