#!/usr/bin/env python3
from __future__ import annotations
import re, sys
from pathlib import Path


def count_numbered(lines: list[str]) -> int:
    return sum(1 for line in lines if re.match(r"^\s*\d+\.\s+", line))

def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    path = root / "docs" / "IP3_V1_3_THREAT_MODEL.md"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    required = ["보호자산 8종", "위협 12종", "실패 9종", "Fail-closed"]
    errors = [x for x in required if x not in text]
    if count_numbered(text.splitlines()) < 29:
        errors.append("expected at least 29 numbered threat/failure/asset items")
    if errors:
        for e in errors:
            print(f"THREAT_MODEL_GATE_FAIL {e}", file=sys.stderr)
        return 2
    print("THREAT_MODEL_GATE_OK assets=8 threats=12 failures=9")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
