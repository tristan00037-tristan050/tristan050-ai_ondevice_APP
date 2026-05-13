#!/usr/bin/env python3
"""check_evidence_consistency.py — 단계 6.5.5 Day 2 CI Gate #7.

label_status 가 gold_reviewed / approved / adjudicated 인 샘플은 gold.* 의 모든
evidence 가 text(synthetic_gold) 또는 text_redacted(userlog_redacted) 안에
substring 으로 존재해야 한다.

label_status=draft / double_labeled / rejected_pii 인 샘플은 검증 면제.

fail-closed 원칙 (Day 1 P1 정정 동일):
  - JSON parse error → ok=False, fail_class=JSON_PARSE_ERROR
  - evidence 불일치 → ok=False, fail_class=EVIDENCE_NOT_IN_TEXT
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# 검증 대상 label_status (approved 이상)
ENFORCE_STATUSES = {"gold_reviewed", "approved", "adjudicated"}


def _resolve_source_text(item: Dict[str, Any]) -> Optional[str]:
    """text(synthetic_gold) 우선, 없으면 text_redacted(userlog) 사용."""
    text = item.get("text")
    if isinstance(text, str) and text:
        return text
    redacted = item.get("text_redacted")
    if isinstance(redacted, str) and redacted:
        return redacted
    return None


def _check_evidence(evidence: Any, source: str) -> bool:
    """evidence 가 source 의 substring 인지."""
    if not isinstance(evidence, str) or not evidence:
        return False
    return evidence in source


def _validate_item(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    """샘플 1건의 모든 evidence 위반 목록 반환 (빈 = OK)."""
    violations: List[Dict[str, Any]] = []
    status = item.get("label_status", "draft")
    if status not in ENFORCE_STATUSES:
        return violations   # 검증 면제

    source = _resolve_source_text(item)
    if source is None:
        violations.append({
            "sample_id": item.get("sample_id", "unknown"),
            "kind":      "no_source_text",
            "detail":    "text 와 text_redacted 모두 비어있음",
        })
        return violations

    gold = item.get("gold") or {}

    # gold.deadline.evidence
    deadline = gold.get("deadline")
    if isinstance(deadline, dict):
        ev = deadline.get("evidence")
        if ev is not None and not _check_evidence(ev, source):
            violations.append({
                "sample_id": item.get("sample_id", "unknown"),
                "kind":      "deadline_evidence_not_in_text",
                "evidence":  ev,
            })

    # gold.materials[*].evidence
    materials = gold.get("materials") or []
    if isinstance(materials, list):
        for idx, m in enumerate(materials):
            if not isinstance(m, dict):
                continue
            ev = m.get("evidence")
            if ev is not None and not _check_evidence(ev, source):
                violations.append({
                    "sample_id": item.get("sample_id", "unknown"),
                    "kind":      "material_evidence_not_in_text",
                    "index":     idx,
                    "evidence":  ev,
                })

    # gold.actions[*].evidence
    actions = gold.get("actions") or []
    if isinstance(actions, list):
        for idx, a in enumerate(actions):
            if not isinstance(a, dict):
                continue
            ev = a.get("evidence")
            if ev is not None and not _check_evidence(ev, source):
                violations.append({
                    "sample_id": item.get("sample_id", "unknown"),
                    "kind":      "action_evidence_not_in_text",
                    "index":     idx,
                    "evidence":  ev,
                })

    return violations


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True)
    p.add_argument("--out",   default=None)
    args = p.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(json.dumps({"ok": False, "fail_class": "INPUT_MISSING",
                          "path": str(in_path)}, ensure_ascii=False))
        return 1

    violations: List[Dict[str, Any]] = []
    parse_errors: List[Dict[str, Any]] = []
    total = enforced = exempt = 0

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
            status = item.get("label_status", "draft")
            if status in ENFORCE_STATUSES:
                enforced += 1
                for v in _validate_item(item):
                    v["line_no"] = line_no
                    violations.append(v)
            else:
                exempt += 1

    parse_total = len(parse_errors)
    violation_total = len(violations)
    ok = (parse_total == 0) and (violation_total == 0)
    fail_class = None
    if not ok:
        # parse error 가 더 심각 (검사 자체 불가능)
        fail_class = "JSON_PARSE_ERROR" if parse_total > 0 else "EVIDENCE_NOT_IN_TEXT"
    report = {
        "ok":                 ok,
        "fail_class":         fail_class,
        "total_items":        total,
        "enforced_items":     enforced,
        "exempt_items":       exempt,
        "violation_count":    violation_total,
        "parse_error_count":  parse_total,
        "violations":         violations[:50],
        "parse_errors":       parse_errors[:50],
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
