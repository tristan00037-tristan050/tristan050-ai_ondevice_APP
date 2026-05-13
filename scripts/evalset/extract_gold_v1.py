#!/usr/bin/env python3
"""extract_gold_v1.py — 단계 6.5.5 Day 5.

label_status='gold_v1' 인 샘플만 추출하여 별도 fixture 출력.
fail-closed: parse 오류 / 후보 0건 → exit 1.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True)
    p.add_argument("--out",   required=True)
    args = p.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(json.dumps({"ok": False, "fail_class": "INPUT_MISSING"},
                         ensure_ascii=False))
        return 1

    extracted = []
    with in_path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as e:
                print(json.dumps({"ok": False, "fail_class": "JSON_PARSE_ERROR",
                                  "line_no": line_no, "error": str(e)},
                                 ensure_ascii=False))
                return 1
            if item.get("label_status") == "gold_v1":
                extracted.append(item)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        "\n".join(json.dumps(it, ensure_ascii=False) for it in extracted) + "\n",
        encoding="utf-8",
    )

    ok = len(extracted) > 0
    report = {
        "ok":              ok,
        "fail_class":      None if ok else "NO_GOLD_V1_ITEMS",
        "extracted_count": len(extracted),
        "output":          str(out_path),
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
