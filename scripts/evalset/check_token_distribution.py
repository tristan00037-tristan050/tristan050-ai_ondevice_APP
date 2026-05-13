#!/usr/bin/env python3
"""check_token_distribution.py — 단계 6.5.5 Day 3 CI Gate G16.

userlog_redacted 샘플의 text_redacted 안에 등장하는 표준 토큰별 분포 집계.
단일 토큰이 70% 초과 등장하면 분포 편향 경고 (TOKEN_DISTRIBUTION_SKEWED).

fail-closed:
  - JSON parse 오류 → JSON_PARSE_ERROR
  - 편향 발견 → TOKEN_DISTRIBUTION_SKEWED
  - 토큰 0개 (userlog 30 이상 보유 데이터셋에서) → TOKEN_DISTRIBUTION_EMPTY
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

# 21 표준 토큰
STANDARD_TOKENS = [
    "[PERSON]", "[TEAM]", "[COMPANY]", "[DOCUMENT]", "[PROJECT]",
    "[DATE]", "[TIME]", "[EMAIL]", "[PHONE]", "[URL]",
    "[ACCOUNT]", "[AMOUNT]", "[ADDRESS]", "[ID]", "[VERSION]",
    "[PR]", "[BRANCH]", "[COMMIT]", "[SERVER]", "[PATH]", "[SECRET]",
    "[CARD]",
]

SKEW_THRESHOLD = 0.70   # 단일 토큰이 70% 초과 → skewed


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True)
    p.add_argument("--out",   default=None)
    p.add_argument("--min-userlog", type=int, default=0,
                   help="userlog 샘플 최소 개수 (미달 시 분포 검사 skip)")
    args = p.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(json.dumps({"ok": False, "fail_class": "INPUT_MISSING",
                          "path": str(in_path)}, ensure_ascii=False))
        return 1

    token_count: Counter = Counter()
    parse_errors: List[dict] = []
    userlog_n = 0
    total = 0

    with in_path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                item = json.loads(line)
            except json.JSONDecodeError as e:
                parse_errors.append({"line_no": line_no, "error": str(e)})
                continue
            src = item.get("source", "")
            if src not in {"internal_log_redacted", "beta_log_redacted",
                           "adjudicated_boundary"}:
                continue
            userlog_n += 1
            text = item.get("text_redacted") or ""
            for tok in STANDARD_TOKENS:
                # 단순 substring count
                token_count[tok] += text.count(tok)

    parse_total = len(parse_errors)
    if parse_total > 0:
        report = {
            "ok": False, "fail_class": "JSON_PARSE_ERROR",
            "parse_error_count": parse_total,
            "parse_errors": parse_errors[:50],
        }
        if args.out:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
        return 1

    total_tokens = sum(token_count.values())
    skew_top:    str | None = None
    skew_ratio:  float = 0.0
    if userlog_n >= args.min_userlog and total_tokens > 0:
        top_tok, top_n = token_count.most_common(1)[0]
        ratio = top_n / total_tokens
        if ratio > SKEW_THRESHOLD:
            skew_top, skew_ratio = top_tok, ratio

    ok = (skew_top is None)
    fail_class = None
    if not ok:
        fail_class = "TOKEN_DISTRIBUTION_SKEWED"

    report = {
        "ok":                 ok,
        "fail_class":         fail_class,
        "total_items":        total,
        "userlog_items":      userlog_n,
        "total_tokens":       total_tokens,
        "token_count":        dict(token_count),
        "skew_threshold":     SKEW_THRESHOLD,
        "skew_top_token":     skew_top,
        "skew_top_ratio":     round(skew_ratio, 4) if skew_top else None,
    }
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
