"""Standard 10 — Strict Policy Base Drift CI guard.

평가 기준(metric threshold)과 label guide 의 시간적 일관성을 검증한다.
알고리즘/모델/임계값을 변경하지 않으며, 평가 PR 의 정책 drift 만 검사한다.

정착 근거: 자문 4차 8 — Branch C-lite / 정밀 patch 전, 평가 기준이 시간에
따라 흔들리면 과거 결과와 비교 불가. metric threshold 변경 금지 + label
guide version bump + before/after comparison 으로 base drift 를 차단한다.

reusable API (sentinel test 가 import):
  - METRIC_THRESHOLDS          : 정착 평가 기준 (변경 금지)
  - DRIFT_PATCH_CONTINUE/HOLD  : drift 등급 경계
  - parse_semver()             : 'MAJOR.MINOR.PATCH' → tuple
  - is_version_bumped()        : label guide version 증가 여부
  - detect_metric_threshold_changes() : 정착 기준 대비 변경 키
  - classify_drift()           : drift 비율 → OK / PATCH_CONTINUE / HOLD
  - validate_before_after()    : before/after comparison 형식 검증
  - validate_drift_report()    : policy drift report 형식 검증
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]

# ── 정착 평가 기준 — 평가 PR 에서 변경 금지 (Standard 10) ──────────────────
METRIC_THRESHOLDS: Dict[str, float] = {
    "deadline_f1":           0.86,    # 외부 베타 기준
    "normalized_action_f1":  0.75,
    "false_deadline_rate":   0.02,    # safety gate 상한
    "no_action_fp_rate":     0.03,    # safety gate 상한
    "auto_apply_precision":  0.95,    # 하향 금지
}

# ── policy drift 등급 경계 ─────────────────────────────────────────────────
DRIFT_PATCH_CONTINUE = 0.05   # 5% 이상 → PATCH_CONTINUE
DRIFT_HOLD           = 0.20   # 20% 이상 → HOLD

# ── version bump 대상 label guide ──────────────────────────────────────────
LABEL_GUIDE_TARGETS = [
    "normalized_action label set",
    "deadline strength taxonomy",   # HARD/SOFT/INQUIRY/URGENCY/CONDITION/NONE
    "safety policy",
]

# ── before/after comparison / drift report 필수 필드 ──────────────────────
BEFORE_AFTER_FIELDS = ["metric", "before", "after", "delta"]
DRIFT_REPORT_FIELDS = ["policy_name", "old_policy_version", "new_policy_version",
                       "drift_rate", "drift_class", "samples_compared"]


def parse_semver(version: str) -> Tuple[int, int, int]:
    """'MAJOR.MINOR.PATCH' → (major, minor, patch). 형식 위반 시 ValueError."""
    parts = str(version).strip().split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"SemVer 형식 위반: {version!r} (MAJOR.MINOR.PATCH)")
    return tuple(int(p) for p in parts)  # type: ignore[return-value]


def is_version_bumped(old: str, new: str) -> bool:
    """new SemVer 가 old 보다 엄격히 증가했는지."""
    return parse_semver(new) > parse_semver(old)


def detect_metric_threshold_changes(candidate: Dict[str, float]) -> List[str]:
    """candidate threshold dict 가 정착 METRIC_THRESHOLDS 와 다른 키 목록.

    평가 PR 은 정착 기준을 변경해서는 안 된다 (시간적 일관성 보증).
    """
    changed: List[str] = []
    for key, base in METRIC_THRESHOLDS.items():
        if key in candidate and abs(candidate[key] - base) > 1e-9:
            changed.append(key)
    return changed


def classify_drift(old_value: float, new_value: float) -> str:
    """old→new drift 비율 → 'OK' | 'PATCH_CONTINUE' | 'HOLD'.

    drift_rate = |new - old| / |old|. old == 0 이면 new 절대값 기준.
    """
    if old_value == 0:
        drift = abs(new_value)
    else:
        drift = abs(new_value - old_value) / abs(old_value)
    if drift >= DRIFT_HOLD:
        return "HOLD"
    if drift >= DRIFT_PATCH_CONTINUE:
        return "PATCH_CONTINUE"
    return "OK"


def validate_before_after(report: Dict[str, Any]) -> List[str]:
    """before/after comparison dict 형식 검증 → 위반 목록."""
    issues: List[str] = []
    rows = report.get("comparison")
    if not isinstance(rows, list) or not rows:
        issues.append("comparison 항목 누락 또는 비어있음")
        return issues
    for i, row in enumerate(rows):
        for fld in BEFORE_AFTER_FIELDS:
            if fld not in row:
                issues.append(f"comparison[{i}].{fld} 누락")
        if all(f in row for f in BEFORE_AFTER_FIELDS):
            expect = round(row["after"] - row["before"], 6)
            if abs(expect - row["delta"]) > 1e-6:
                issues.append(f"comparison[{i}].delta 불일치 "
                               f"(after-before={expect}, delta={row['delta']})")
    return issues


def validate_drift_report(report: Dict[str, Any]) -> List[str]:
    """policy drift report dict 형식 검증 → 위반 목록."""
    issues: List[str] = []
    for fld in DRIFT_REPORT_FIELDS:
        if fld not in report:
            issues.append(f"drift report 필드 누락: {fld}")
    if issues:
        return issues
    # version bump 정합 (old → new 증가)
    try:
        if not is_version_bumped(report["old_policy_version"],
                                  report["new_policy_version"]):
            issues.append("new_policy_version 이 old 대비 미증가 (version bump 누락)")
    except ValueError as exc:
        issues.append(f"policy version SemVer 위반: {exc}")
    # drift_class 가 drift_rate 와 정합
    rate = report["drift_rate"]
    expected = ("HOLD" if rate >= DRIFT_HOLD
                else "PATCH_CONTINUE" if rate >= DRIFT_PATCH_CONTINUE
                else "OK")
    if report["drift_class"] != expected:
        issues.append(f"drift_class 불일치 (rate={rate} → {expected}, "
                       f"기록={report['drift_class']})")
    return issues


def audit_evidence(root: Path) -> Dict[str, Any]:
    """evidence/day*/ 의 before/after + drift report 형식 감사."""
    violations: List[Dict[str, Any]] = []
    ba_files = sorted(root.glob("evidence/day*/**/before_after_comparison.json"))
    dr_files = sorted(root.glob("evidence/day*/**/policy_drift_report.json"))
    for fp in ba_files:
        iss = validate_before_after(json.loads(fp.read_text(encoding="utf-8")))
        if iss:
            violations.append({"file": str(fp.relative_to(root)), "issues": iss})
    for fp in dr_files:
        iss = validate_drift_report(json.loads(fp.read_text(encoding="utf-8")))
        if iss:
            violations.append({"file": str(fp.relative_to(root)), "issues": iss})
    return {"before_after_checked": len(ba_files),
            "drift_report_checked": len(dr_files),
            "violations": violations, "ok": not violations}


def main() -> int:
    result = audit_evidence(ROOT)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
