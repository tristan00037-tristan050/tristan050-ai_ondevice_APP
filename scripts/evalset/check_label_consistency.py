#!/usr/bin/env python3
"""check_label_consistency.py — 단계 6.5.5 Day 3 CI Gate G8~G15.

알고리즘 팀 Day 3 추가 차단 기준 8가지를 단일 스크립트로 통합 검사. fail-closed.

  G8  ANNOTATOR_MISSING_WHEN_DOUBLE_LABELED
        label_status=double_labeled 인데 annotator_a 또는 annotator_b 누락
  G9  REVIEWER_MISSING_WHEN_APPROVED
        label_status ∈ {approved, gold_reviewed} 인데 reviewer 누락
        label_status = adjudicated 인데 adjudicator 누락
  G10 PRIMARY_INTENT_MISMATCH_GOLD
        item.intent_type 과 gold.intent_type 불일치 (enforced status 만)
  G11 DEADLINE_TYPE_INCONSISTENT_WITH_OBJECT
        deadline_type ∈ {NONE, INQUIRY, URGENCY, CONDITION} 인데 gold.deadline 존재
        deadline_type ∈ {HARD, SOFT} 인데 gold.deadline 누락
  G12 NO_ACTION_HAS_NONEMPTY_ACTIONS
        intent_type=NO_ACTION 인데 gold.actions 비어있지 않음
  G13 AUTO_APPLY_REQUIRES_APPROVED
        auto_apply_allowed=true 인데 label_status ∉ {approved}
  G14 USERLOG_TEXT_NOT_NULL
        source ∈ {internal_log_redacted, beta_log_redacted, adjudicated_boundary}
        인데 text != null (스키마 + Gate 이중 차단)
  G15 EVIDENCE_INCONSISTENT_WHEN_APPROVED
        evidence 가 text/text_redacted 안에 없음 + label_status ∈ {gold_reviewed, approved}

Returns:
  exit 0 — ok=true (위반 0건)
  exit 1 — fail_class 첫 위반 코드 노출
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ENFORCED_STATUSES = {"gold_reviewed", "approved", "adjudicated", "gold_v1"}
APPROVED_LIKE     = {"approved", "gold_reviewed", "gold_v1"}
# PR #704 P2 정정: G13 기준 — auto_apply_allowed=true 허용 status 집합
# (Day 4 final_gold/gold_v1/adjudicated 도 자동 적용 허용)
APPROVED_LIKE_STATUSES = {"approved", "gold_reviewed", "gold_v1", "adjudicated"}
USERLOG_SOURCES   = {"internal_log_redacted", "beta_log_redacted",
                     "adjudicated_boundary"}

GATE_CODES = {
    "G8":  "ANNOTATOR_MISSING_WHEN_DOUBLE_LABELED",
    "G9":  "REVIEWER_MISSING_WHEN_APPROVED",
    "G10": "PRIMARY_INTENT_MISMATCH_GOLD",
    "G11": "DEADLINE_TYPE_INCONSISTENT_WITH_OBJECT",
    "G12": "NO_ACTION_HAS_NONEMPTY_ACTIONS",
    "G13": "AUTO_APPLY_REQUIRES_APPROVED_LIKE",
    "G14": "USERLOG_TEXT_NOT_NULL",
    "G15": "EVIDENCE_INCONSISTENT_WHEN_APPROVED",
}


def _resolve_source(item: Dict[str, Any]) -> str:
    text = item.get("text")
    if isinstance(text, str) and text:
        return text
    redacted = item.get("text_redacted")
    if isinstance(redacted, str) and redacted:
        return redacted
    return ""


def _validate_item(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    sid    = item.get("sample_id", "unknown")
    status = item.get("label_status", "")
    src    = item.get("source", "")
    violations: List[Dict[str, Any]] = []

    # ── G14: userlog text != null (먼저 검사 — PII 경로 차단) ─────────
    if src in USERLOG_SOURCES and item.get("text") is not None:
        violations.append({
            "sample_id":  sid, "gate": "G14",
            "fail_class": GATE_CODES["G14"],
            "detail":     "userlog 인데 text 가 null 이 아님",
        })

    # ── G8: double_labeled 인데 annotator 누락 ─────────────────────────
    if status == "double_labeled":
        if not item.get("annotator_a") or not item.get("annotator_b"):
            violations.append({
                "sample_id":  sid, "gate": "G8",
                "fail_class": GATE_CODES["G8"],
                "detail":     "annotator_a 또는 annotator_b 누락",
            })

    # ── G9: approved/gold_reviewed/adjudicated 인데 reviewer/adjudicator 누락 ─
    if status in APPROVED_LIKE and not item.get("reviewer"):
        violations.append({
            "sample_id":  sid, "gate": "G9",
            "fail_class": GATE_CODES["G9"],
            "detail":     f"{status} 인데 reviewer 누락",
        })
    if status == "adjudicated" and not item.get("adjudicator"):
        violations.append({
            "sample_id":  sid, "gate": "G9",
            "fail_class": GATE_CODES["G9"],
            "detail":     "adjudicated 인데 adjudicator 누락",
        })

    # ── G13: auto_apply_allowed=true 인데 APPROVED_LIKE_STATUSES 외 ──
    # PR #704 P2 정정: scheme enum 정합. approved/gold_reviewed/gold_v1/adjudicated 허용.
    if item.get("auto_apply_allowed") is True and status not in APPROVED_LIKE_STATUSES:
        violations.append({
            "sample_id":            sid, "gate": "G13",
            "fail_class":           GATE_CODES["G13"],
            "current_status":       status,
            "required_status_set":  sorted(APPROVED_LIKE_STATUSES),
            "detail":               (f"auto_apply_allowed=true 인데 "
                                     f"label_status={status} (허용 집합 외)"),
        })

    # ── enforced status 만 G10/G11/G12/G15 검사 ────────────────────────
    if status not in ENFORCED_STATUSES:
        return violations

    gold = item.get("gold") or {}

    # ── G10: item.intent_type ≠ gold.intent_type ───────────────────────
    primary = item.get("intent_type")
    gold_intent = gold.get("intent_type")
    if primary != gold_intent:
        violations.append({
            "sample_id":  sid, "gate": "G10",
            "fail_class": GATE_CODES["G10"],
            "detail":     f"primary={primary}, gold.intent_type={gold_intent}",
        })

    # ── G11: deadline_type 과 gold.deadline 정합 ────────────────────────
    dtype     = item.get("deadline_type", "NONE")
    gold_dl   = gold.get("deadline")
    if dtype in {"NONE", "INQUIRY", "URGENCY", "CONDITION"}:
        if gold_dl is not None:
            violations.append({
                "sample_id":  sid, "gate": "G11",
                "fail_class": GATE_CODES["G11"],
                "detail":     f"deadline_type={dtype} 인데 gold.deadline 존재",
            })
    elif dtype in {"HARD", "SOFT"}:
        if gold_dl is None:
            violations.append({
                "sample_id":  sid, "gate": "G11",
                "fail_class": GATE_CODES["G11"],
                "detail":     f"deadline_type={dtype} 인데 gold.deadline 누락",
            })

    # ── G12: NO_ACTION 인데 actions 비어있지 않음 ──────────────────────
    if primary == "NO_ACTION":
        actions = gold.get("actions") or []
        if len(actions) > 0:
            violations.append({
                "sample_id":  sid, "gate": "G12",
                "fail_class": GATE_CODES["G12"],
                "detail":     f"NO_ACTION 인데 gold.actions={len(actions)}건",
            })

    # ── G15: evidence 불일치 + approved/gold_reviewed ──────────────────
    if status in APPROVED_LIKE:
        source_text = _resolve_source(item)
        if source_text:
            def _check(ev):
                return isinstance(ev, str) and ev and ev in source_text

            # gold.deadline.evidence
            if isinstance(gold_dl, dict):
                ev = gold_dl.get("evidence")
                if ev is not None and not _check(ev):
                    violations.append({
                        "sample_id":  sid, "gate": "G15",
                        "fail_class": GATE_CODES["G15"],
                        "detail":     f"deadline evidence not in text: {ev!r}",
                    })
            # gold.materials[*].evidence
            for idx, m in enumerate(gold.get("materials") or []):
                if isinstance(m, dict):
                    ev = m.get("evidence")
                    if ev is not None and not _check(ev):
                        violations.append({
                            "sample_id":  sid, "gate": "G15",
                            "fail_class": GATE_CODES["G15"],
                            "detail":     f"materials[{idx}] evidence not in text: {ev!r}",
                        })
            # gold.actions[*].evidence
            for idx, a in enumerate(gold.get("actions") or []):
                if isinstance(a, dict):
                    ev = a.get("evidence")
                    if ev is not None and not _check(ev):
                        violations.append({
                            "sample_id":  sid, "gate": "G15",
                            "fail_class": GATE_CODES["G15"],
                            "detail":     f"actions[{idx}] evidence not in text: {ev!r}",
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

    parse_total      = len(parse_errors)
    violation_total  = len(violations)
    ok = (parse_total == 0) and (violation_total == 0)
    if not ok:
        if parse_total > 0:
            fail_class = "JSON_PARSE_ERROR"
        else:
            fail_class = violations[0]["fail_class"]
    else:
        fail_class = None

    # gate별 위반 카운트 집계
    by_gate: Dict[str, int] = {code: 0 for code in GATE_CODES.values()}
    for v in violations:
        by_gate[v["fail_class"]] = by_gate.get(v["fail_class"], 0) + 1

    report = {
        "ok":                ok,
        "fail_class":        fail_class,
        "total_items":       total,
        "violation_count":   violation_total,
        "parse_error_count": parse_total,
        "by_gate":           by_gate,
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
