#!/usr/bin/env python3
"""check_token_distribution.py — 단계 6.5.5 Day 3 CI Gate G16.

userlog_redacted 샘플의 text_redacted 안에 등장하는 표준 토큰별 분포 집계.

PR #704 P1 정정 (2026-05-13):
  fail-closed 분리.
  - BLOCK (exit 1): userlog ≥ min_userlog 인데 표준 토큰 0개 → TOKEN_DISTRIBUTION_EMPTY
    (tokenization / redaction 회귀 — PII 누출 위험 의심).
  - WARNING (exit 0, ok=true): SKEW (단일 토큰 > 70%) 또는 LOW_VARIETY (8종 미만).
  - JSON parse → JSON_PARSE_ERROR (fail-closed).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

# 22 표준 토큰
STANDARD_TOKENS = [
    "[PERSON]", "[TEAM]", "[COMPANY]", "[DOCUMENT]", "[PROJECT]",
    "[DATE]", "[TIME]", "[EMAIL]", "[PHONE]", "[URL]",
    "[ACCOUNT]", "[AMOUNT]", "[ADDRESS]", "[ID]", "[VERSION]",
    "[PR]", "[BRANCH]", "[COMMIT]", "[SERVER]", "[PATH]", "[SECRET]",
    "[CARD]",
]

SKEW_THRESHOLD     = 0.70   # 단일 토큰이 70% 초과 → SKEW warning
MIN_TOKEN_VARIETY  = 8      # 종류 < 8 → LOW_VARIETY warning


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True)
    p.add_argument("--out",   default=None)
    p.add_argument("--min-userlog", type=int, default=0,
                   help="이 값 이상이면 EMPTY 차단 발동 (기본 0 = 항상 검사)")
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
                token_count[tok] += text.count(tok)

    # ── JSON parse error → fail-closed ──────────────────────────────────
    if parse_errors:
        report = {
            "ok":                  False,
            "fail_class":          "JSON_PARSE_ERROR",
            "parse_error_count":   len(parse_errors),
            "parse_errors":        parse_errors[:50],
        }
        if args.out:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
        return 1

    total_tokens     = sum(token_count.values())
    detected_tokens  = [t for t, n in token_count.items() if n > 0]

    # ── BLOCK: userlog ≥ min_userlog 인데 토큰 0개 ─────────────────────
    if userlog_n >= args.min_userlog and total_tokens == 0 and userlog_n > 0:
        report = {
            "ok":                False,
            "fail_class":        "TOKEN_DISTRIBUTION_EMPTY",
            "message":           (f"userlog {userlog_n}건인데 표준 토큰 0개 검출 "
                                  "(tokenization 회귀 의심)"),
            "block_type":        "BLOCK",
            "userlog_count":     userlog_n,
            "total_tokens":      0,
            "detected_tokens":   [],
            "total_items":       total,
        }
        if args.out:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
        return 1

    # ── WARNING: SKEW / LOW_VARIETY (ok=true 유지) ─────────────────────
    warnings: List[Dict[str, Any]] = []
    skew_top:    str | None  = None
    skew_ratio:  float       = 0.0
    if userlog_n >= args.min_userlog and total_tokens > 0:
        top_tok, top_n = token_count.most_common(1)[0]
        if top_n > 0:
            ratio = top_n / total_tokens
            if ratio > SKEW_THRESHOLD:
                skew_top, skew_ratio = top_tok, ratio
                warnings.append({
                    "type":       "TOKEN_DISTRIBUTION_SKEW",
                    "top_token":  skew_top,
                    "ratio":      round(skew_ratio, 4),
                    "threshold":  SKEW_THRESHOLD,
                    "block_type": "WARNING",
                })

    if total_tokens > 0 and len(detected_tokens) < MIN_TOKEN_VARIETY:
        warnings.append({
            "type":                 "TOKEN_VARIETY_LOW",
            "detected_count":       len(detected_tokens),
            "minimum_recommended":  MIN_TOKEN_VARIETY,
            "block_type":           "WARNING",
        })

    report = {
        "ok":                 True,
        "fail_class":         None,
        "total_items":        total,
        "userlog_count":      userlog_n,
        "total_tokens":       total_tokens,
        "detected_tokens":    detected_tokens,
        "token_distribution": dict(token_count),
        "warnings":           warnings,
        "skew_threshold":     SKEW_THRESHOLD,
    }
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
