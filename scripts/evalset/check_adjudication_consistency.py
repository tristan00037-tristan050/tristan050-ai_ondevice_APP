#!/usr/bin/env python3
"""check_adjudication_consistency.py — 단계 6.5.5 Day 4 CI Gate G17~G21.

알고리즘 팀 Day 4 차단 기준을 단일 스크립트로 통합 검사. fail-closed.

  G17 ADJUDICATOR_MISSING_WHEN_ADJUDICATED
        label_status=adjudicated 또는 gold_v1 인데 adjudicator 누락
  G18 FINAL_GOLD_MISSING_WHEN_ADJUDICATED
        label_status=adjudicated 또는 gold_v1 인데 final_gold 누락
  G19 APPROVED_WITHOUT_DISAGREEMENT_RESOLUTION
        annotator_a/b 불일치 sample 인데 label_status=adjudicated
        인 경우 final_gold.disagreement_resolution 누락
  G20 AUTO_APPLY_REASONING_MISSING
        PR #705 P2-B 정정: top-level auto_apply_allowed=true
                            OR final_gold.auto_apply_allowed=true 인데
                            auto_apply_reasoning 누락/짧음(< 10자).
                            (이전엔 top-level 만 검사 → final_gold 우회 가능)
  G21 AUTO_APPLY_MISMATCH (PR #705 P2-C 신규)
        label_status ∈ {adjudicated, gold_v1} 인데
        top-level auto_apply_allowed ≠ final_gold.auto_apply_allowed.
        (top vs final 정합성 강제)

Returns: exit 0 (ok=true) or exit 1 with fail_class.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ENFORCED_ADJUDICATED      = {"adjudicated", "gold_v1"}
ADJUDICATED_LIKE_STATUSES = {"adjudicated", "gold_v1"}

GATE_CODES = {
    "G17": "ADJUDICATOR_MISSING_WHEN_ADJUDICATED",
    "G18": "FINAL_GOLD_MISSING_WHEN_ADJUDICATED",
    "G19": "APPROVED_WITHOUT_DISAGREEMENT_RESOLUTION",
    "G20": "AUTO_APPLY_REASONING_MISSING",
    "G21": "AUTO_APPLY_MISMATCH",
}

MIN_EXPLANATION_LEN = 10


def _is_disagreement(item: Dict[str, Any]) -> bool:
    a = item.get("annotator_a") or {}
    b = item.get("annotator_b") or {}
    if not a or not b:
        return False
    for k in ("intent_type", "deadline_type", "auto_apply_allowed"):
        if a.get(k) != b.get(k):
            return True
    return False


def _validate_item(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    sid    = item.get("sample_id", "unknown")
    status = item.get("label_status", "")
    violations: List[Dict[str, Any]] = []

    if status in ENFORCED_ADJUDICATED and not item.get("adjudicator"):
        violations.append({
            "sample_id":  sid, "gate": "G17",
            "fail_class": GATE_CODES["G17"],
            "detail":     f"{status} 인데 adjudicator 누락",
        })
    if status in ENFORCED_ADJUDICATED and not item.get("final_gold"):
        violations.append({
            "sample_id":  sid, "gate": "G18",
            "fail_class": GATE_CODES["G18"],
            "detail":     f"{status} 인데 final_gold 누락",
        })
    if status in ENFORCED_ADJUDICATED and _is_disagreement(item):
        fg = item.get("final_gold") or {}
        if not fg.get("disagreement_resolution"):
            violations.append({
                "sample_id":  sid, "gate": "G19",
                "fail_class": GATE_CODES["G19"],
                "detail":     "annotator 불일치 인데 disagreement_resolution 누락",
            })
    # ── G20: PR #705 P2-B 정정 — top-level OR final_gold 모두 검사 ──
    top_auto = item.get("auto_apply_allowed") is True
    fg       = item.get("final_gold") or {}
    fg_auto  = fg.get("auto_apply_allowed") is True
    if top_auto or fg_auto:
        reasoning = item.get("auto_apply_reasoning")
        if not isinstance(reasoning, dict):
            violations.append({
                "sample_id":             sid, "gate": "G20",
                "fail_class":            GATE_CODES["G20"],
                "top_level_auto_apply":  top_auto,
                "final_gold_auto_apply": fg_auto,
                "label_status":          status,
                "detail":                "auto_apply_reasoning 누락",
            })
        else:
            missing = []
            if not isinstance(reasoning.get("evidence_basis"), str) \
               or not reasoning.get("evidence_basis"):
                missing.append("evidence_basis")
            if not isinstance(reasoning.get("verifier_pass"), bool):
                missing.append("verifier_pass")
            explain = reasoning.get("explanation", "")
            if not isinstance(explain, str) or len(explain) < MIN_EXPLANATION_LEN:
                missing.append(f"explanation(min {MIN_EXPLANATION_LEN}chars)")
            if missing:
                violations.append({
                    "sample_id":             sid, "gate": "G20",
                    "fail_class":            GATE_CODES["G20"],
                    "missing":               missing,
                    "top_level_auto_apply":  top_auto,
                    "final_gold_auto_apply": fg_auto,
                    "detail":                "auto_apply_reasoning 필드 누락 또는 짧음",
                })

    # ── G21: PR #705 P2-C 신규 — top vs final_gold auto_apply 정합성 ──
    if status in ADJUDICATED_LIKE_STATUSES:
        top_raw = item.get("auto_apply_allowed")
        fg_raw  = fg.get("auto_apply_allowed") if isinstance(fg, dict) else None
        if top_raw is not None and fg_raw is not None and top_raw != fg_raw:
            violations.append({
                "sample_id":             sid, "gate": "G21",
                "fail_class":            GATE_CODES["G21"],
                "top_level_auto_apply":  top_raw,
                "final_gold_auto_apply": fg_raw,
                "label_status":          status,
                "detail":                "top-level 과 final_gold 의 auto_apply_allowed 불일치",
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

    parse_total     = len(parse_errors)
    violation_total = len(violations)
    ok = (parse_total == 0) and (violation_total == 0)
    fail_class = None
    if not ok:
        fail_class = "JSON_PARSE_ERROR" if parse_total > 0 else violations[0]["fail_class"]

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
