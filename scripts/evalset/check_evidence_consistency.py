#!/usr/bin/env python3
"""check_evidence_consistency.py — 단계 6.5.5 Day 2 CI Gate #7.

label_status 가 gold_reviewed / approved / adjudicated 인 샘플은 gold.* 의 모든
evidence 가 text(synthetic_gold) 또는 text_redacted(userlog_redacted) 안에
substring 으로 존재해야 한다.

label_status 가 draft / double_labeled / rejected_pii 인 샘플은 검증 면제.

PR #703 P1 정정 (2026-05-13): fail-closed 강화.
  - evidence 가 None 또는 빈 문자열이면 EVIDENCE_MISSING 으로 차단
    (이전엔 silently skip → 부분 라벨링이 통과되는 fail-open 버그).
  - label_status 가 알려진 enum 에 없으면 UNKNOWN_LABEL_STATUS 로 차단.
  - enforced status 인데 gold 자체가 비어있으면 GOLD_MISSING_WHEN_ENFORCED.
  - JSON parse 오류는 별도 카운터 + JSON_PARSE_ERROR (Day 1 P2 동일).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# label_status 분류 (PR #703 P1 정정)
ENFORCED_STATUSES = {"gold_reviewed", "approved", "adjudicated"}
EXEMPT_STATUSES   = {"draft", "double_labeled", "rejected_pii"}


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
    if not isinstance(evidence, str) or not evidence:
        return False
    return evidence in source


def _validate_item(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    """샘플 1건 → 위반 목록 (빈 = OK).

    PR #703 P1: evidence None/"" 은 fail-closed (EVIDENCE_MISSING).
    """
    violations: List[Dict[str, Any]] = []
    sid = item.get("sample_id", "unknown")
    status = item.get("label_status", "")

    # ── 면제 ────────────────────────────────────────────────────────────
    if status in EXEMPT_STATUSES:
        return violations

    # ── 알 수 없는 status → fail-closed ────────────────────────────────
    if status not in ENFORCED_STATUSES:
        return [{
            "sample_id":    sid,
            "kind":         "unknown_label_status",
            "label_status": status,
        }]

    # ── enforced status 인데 gold 자체가 없음 → fail-closed ─────────────
    gold = item.get("gold")
    if not gold:
        return [{
            "sample_id":    sid,
            "kind":         "gold_missing_when_enforced",
            "label_status": status,
        }]

    source = _resolve_source_text(item)
    if source is None:
        violations.append({
            "sample_id": sid,
            "kind":      "no_source_text",
            "detail":    "text 와 text_redacted 모두 비어있음",
        })
        return violations

    # ── gold.deadline.evidence ──────────────────────────────────────────
    deadline = gold.get("deadline")
    if deadline is not None:
        if not isinstance(deadline, dict):
            violations.append({
                "sample_id": sid,
                "kind":      "invalid_deadline_object",
            })
        else:
            ev = deadline.get("evidence")
            if ev is None or ev == "":
                violations.append({
                    "sample_id": sid,
                    "kind":      "evidence_missing",
                    "field":     "gold.deadline.evidence",
                })
            elif not _check_evidence(ev, source):
                violations.append({
                    "sample_id": sid,
                    "kind":      "deadline_evidence_not_in_text",
                    "evidence":  ev,
                })

    # ── gold.materials[*].evidence ──────────────────────────────────────
    materials = gold.get("materials") or []
    if isinstance(materials, list):
        for idx, m in enumerate(materials):
            if not isinstance(m, dict):
                violations.append({
                    "sample_id": sid,
                    "kind":      "invalid_material_object",
                    "index":     idx,
                })
                continue
            ev = m.get("evidence")
            if ev is None or ev == "":
                violations.append({
                    "sample_id": sid,
                    "kind":      "evidence_missing",
                    "field":     f"gold.materials[{idx}].evidence",
                })
            elif not _check_evidence(ev, source):
                violations.append({
                    "sample_id": sid,
                    "kind":      "material_evidence_not_in_text",
                    "index":     idx,
                    "evidence":  ev,
                })

    # ── gold.actions[*].evidence ────────────────────────────────────────
    actions = gold.get("actions") or []
    if isinstance(actions, list):
        for idx, a in enumerate(actions):
            if not isinstance(a, dict):
                violations.append({
                    "sample_id": sid,
                    "kind":      "invalid_action_object",
                    "index":     idx,
                })
                continue
            ev = a.get("evidence")
            if ev is None or ev == "":
                violations.append({
                    "sample_id": sid,
                    "kind":      "evidence_missing",
                    "field":     f"gold.actions[{idx}].evidence",
                })
            elif not _check_evidence(ev, source):
                violations.append({
                    "sample_id": sid,
                    "kind":      "action_evidence_not_in_text",
                    "index":     idx,
                    "evidence":  ev,
                })

    return violations


def _violation_to_fail_class(v: Dict[str, Any]) -> str:
    kind = v.get("kind", "")
    if kind == "unknown_label_status":
        return "UNKNOWN_LABEL_STATUS"
    if kind == "gold_missing_when_enforced":
        return "GOLD_MISSING_WHEN_ENFORCED"
    if kind == "evidence_missing":
        return "EVIDENCE_MISSING"
    if "evidence_not_in_text" in kind:
        return "EVIDENCE_NOT_IN_TEXT"
    return "INVALID_OBJECT"


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
            status = item.get("label_status", "")
            if status in EXEMPT_STATUSES:
                exempt += 1
            else:
                enforced += 1
                for v in _validate_item(item):
                    v["line_no"] = line_no
                    violations.append(v)

    parse_total      = len(parse_errors)
    violation_total  = len(violations)
    ok = (parse_total == 0) and (violation_total == 0)
    fail_class: Optional[str] = None
    if not ok:
        # parse error 우선 (검사 자체 불가능이 더 심각)
        if parse_total > 0:
            fail_class = "JSON_PARSE_ERROR"
        else:
            # 첫 위반의 fail_class 노출
            fail_class = _violation_to_fail_class(violations[0])

    report = {
        "ok":                ok,
        "fail_class":        fail_class,
        "total_items":       total,
        "enforced_items":    enforced,
        "exempt_items":      exempt,
        "violation_count":   violation_total,
        "parse_error_count": parse_total,
        "violations":        violations[:50],
        "parse_errors":      parse_errors[:50],
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
