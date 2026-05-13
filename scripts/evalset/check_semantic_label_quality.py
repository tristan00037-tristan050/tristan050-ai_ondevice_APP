#!/usr/bin/env python3
"""check_semantic_label_quality.py — 단계 6.5.5+ Day 8 CI Gate G23 v0.

알고리즘 팀 옵션 C 확정 (2026-05-15): 개별 row 의미-라벨 일관성 패턴 검증.

Hard fail (fail-closed):
  1. PURE_QUESTION_MISLABELED_AS_REQUEST
     순수 정보 문의 패턴(어떻게 되나요/언제인가요/누구인가요/어디인가요)
     + intent_type=REQUEST + action_required=true + 행동동사 없음
  2. REPORT_MISLABELED_AS_REQUEST
     보고형 어미(완료했습니다/보고드립니다/안내드립니다/공유했습니다/전달했습니다)
     + intent_type=REQUEST

Warning (ok=true 유지):
  1. AMBIGUOUS_REQUEST_PATTERN — '가능한가요/확인 가능할까요' + REQUEST + 행동동사 없음
  2. AMBIGUOUS_REPORT_PATTERN  — '처리하겠습니다' + REPORT/REQUEST 경계
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

PURE_QUESTION_PATTERNS = ["어떻게 되나요", "언제인가요", "누구인가요", "어디인가요"]
REPORT_FIXED_PATTERNS  = ["완료했습니다", "보고드립니다", "안내드립니다",
                          "공유했습니다", "전달했습니다"]

WARNING_PATTERNS_REQUEST = ["가능한가요", "확인 가능할까요"]
WARNING_PATTERNS_REPORT  = ["처리하겠습니다"]

# Day 10 G23 v1 — 약속/수행 보고 경계 패턴 (warning only, hard 승격 금지)
WARNING_PATTERNS_PROMISE = ["처리하겠습니다", "진행하겠습니다", "전달드리겠습니다"]

ACTION_VERB_PATTERNS = [
    "보내", "전달", "공유", "검토", "작성", "수정", "제출", "회신",
    "업로드", "확인 부탁", "조율", "해 주", "부탁드립", "보고 부탁",
    "정리해", "보내주", "주실 수 있나요",
]

FAIL_CLASS_PURE_Q = "PURE_QUESTION_MISLABELED_AS_REQUEST"
FAIL_CLASS_REPORT = "REPORT_MISLABELED_AS_REQUEST"
WARN_CLASS_REQ    = "AMBIGUOUS_REQUEST_PATTERN"
WARN_CLASS_REP    = "AMBIGUOUS_REPORT_PATTERN"
WARN_CLASS_PROMISE = "PROMISE_BOUNDARY_PATTERN"  # Day 10 G23 v1


def has_action_verb(text: str) -> bool:
    return any(v in text for v in ACTION_VERB_PATTERNS)


def _resolve_text(item: Dict[str, Any]) -> str:
    return item.get("text") or item.get("text_redacted") or ""


def _validate_item(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    text   = _resolve_text(item)
    intent = item.get("intent_type")
    sid    = item.get("sample_id", "unknown")
    violations: List[Dict[str, Any]] = []
    if not text:
        return violations

    for pat in PURE_QUESTION_PATTERNS:
        if pat in text and intent == "REQUEST" \
           and item.get("action_required") is True \
           and not has_action_verb(text):
            violations.append({
                "fail_class": FAIL_CLASS_PURE_Q,
                "sample_id":  sid, "text": text[:80],
                "pattern":    pat,
                "expected":   "QUESTION + action_required=false",
            })
            return violations

    for pat in REPORT_FIXED_PATTERNS:
        if pat in text and intent == "REQUEST":
            violations.append({
                "fail_class": FAIL_CLASS_REPORT,
                "sample_id":  sid, "text": text[:80],
                "pattern":    pat,
                "expected":   "REPORT + action_required=false",
            })
            return violations
    return violations


def _detect_warnings(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    text   = _resolve_text(item)
    intent = item.get("intent_type")
    sid    = item.get("sample_id", "unknown")
    warnings: List[Dict[str, Any]] = []
    if not text:
        return warnings
    for pat in WARNING_PATTERNS_REQUEST:
        if pat in text and intent == "REQUEST" and not has_action_verb(text):
            warnings.append({
                "warning_class": WARN_CLASS_REQ,
                "sample_id":     sid, "text": text[:80],
                "pattern":       pat,
            })
            break
    for pat in WARNING_PATTERNS_REPORT:
        if pat in text and intent in {"REPORT", "REQUEST"}:
            warnings.append({
                "warning_class": WARN_CLASS_REP,
                "sample_id":     sid, "text": text[:80],
                "pattern":       pat,
                "current_intent": intent,
            })
            break
    # Day 10 G23 v1 — PROMISE_BOUNDARY 약속/수행 보고 경계
    for pat in WARNING_PATTERNS_PROMISE:
        if pat in text and intent in {"REPORT", "REQUEST"}:
            warnings.append({
                "warning_class":  WARN_CLASS_PROMISE,
                "sample_id":      sid, "text": text[:80],
                "pattern":        pat,
                "current_intent": intent,
            })
            break
    return warnings


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True)
    p.add_argument("--out",   default=None)
    args = p.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(json.dumps({"ok": False, "fail_class": "INPUT_MISSING"},
                         ensure_ascii=False))
        return 1

    violations: List[Dict[str, Any]] = []
    warnings:   List[Dict[str, Any]] = []
    parse_errors: List[Dict[str, Any]] = []
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
            for v in _validate_item(item):
                v["line_no"] = line_no
                violations.append(v)
            for w in _detect_warnings(item):
                w["line_no"] = line_no
                warnings.append(w)

    if parse_errors:
        report = {"ok": False, "fail_class": "JSON_PARSE_ERROR",
                  "parse_error_count": len(parse_errors),
                  "parse_errors": parse_errors[:50]}
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
        return 1

    ok = len(violations) == 0
    report = {
        "ok":              ok,
        "fail_class":      None if ok else "SEMANTIC_LABEL_PATTERN_VIOLATION",
        "total_items":     total,
        "violation_count": len(violations),
        "warning_count":   len(warnings),
        "violations":      violations[:50],
        "warnings":        warnings[:50],
    }
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
