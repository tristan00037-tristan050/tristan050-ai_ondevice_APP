"""Standard 9 — Dataset Integrity Fail-Closed CI guard.

평가 PR 의 dataset integrity 를 fail-closed 로 검증한다. 알고리즘/모델/임계값
변경은 하지 않으며, evidence 의 coverage_report 정합성만 검사한다.

정착 근거: Standard #6 coverage fail-closed sentinel 이 PR #718/#722/#723/
#725/#726 5회에 걸쳐 회귀를 입증 — dataset-level integrity 를 단일 표준으로
승격한다 (자문 4차 8 명시).

reusable API (sentinel test 가 import):
  - COVERAGE_REPORT_FIELDS : coverage_report 필수 12 필드
  - FAIL_CLASSES           : 허용 fail_class 집합
  - classify_coverage()    : item/pred id 리스트 → fail_class
  - validate_coverage_report() : coverage_report dict → 위반 목록
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Sequence

ROOT = Path(__file__).resolve().parents[2]

# ── coverage_report 필수 12 필드 (PR #723/#725/#726/#727 정합) ──────────────
COVERAGE_REPORT_FIELDS: List[str] = [
    "coverage_checked",
    "expected_samples",
    "measured_samples",
    "missing_count",
    "missing_ids",
    "extra_count",
    "extra_ids",
    "gold_duplicate_count",
    "gold_duplicate_ids",
    "prediction_duplicate_count",
    "prediction_duplicate_ids",
    "fail_class",
]

# ── 허용 fail_class ────────────────────────────────────────────────────────
FAIL_CLASSES = {
    "GOLD_SAMPLE_ID_DUPLICATE",       # gold 측 sample_id 중복
    "FULL_EVAL_COVERAGE_MISMATCH",    # missing / extra / prediction 중복
    "SEMANTIC_LABEL_VIOLATION",       # gold label 이 schema enum 위반
    "ACTION_UNIT_MISMATCH",           # action unit 분할 단위 불일치
    "AB_COMPOSITION_MISMATCH",        # AB 구성 불일치 (Standard 7 연계)
}

# baseline / patched mode 분리 산식 원칙 (PR #727 정합)
MEASURE_MODE_PRINCIPLE = (
    "baseline 와 patched 측정은 서로 다른 actionable/예측 소스를 사용해야 한다. "
    "두 mode 가 동일 pre-patch 필드를 공유하면 patch 효과가 측정에 반영되지 않는다."
)


def classify_coverage(item_ids: Sequence[str],
                       pred_ids: Sequence[str]) -> str | None:
    """gold/prediction id 리스트 → fail_class (정합 시 None).

    우선순위: gold 중복 > (missing | extra | prediction 중복).
    """
    gold_dup = [s for s, c in Counter(item_ids).items() if c > 1]
    pred_dup = [s for s, c in Counter(pred_ids).items() if c > 1]
    missing = set(item_ids) - set(pred_ids)
    extra = set(pred_ids) - set(item_ids)
    if gold_dup:
        return "GOLD_SAMPLE_ID_DUPLICATE"
    if missing or extra or pred_dup:
        return "FULL_EVAL_COVERAGE_MISMATCH"
    return None


def validate_coverage_report(cov: Dict[str, Any]) -> List[str]:
    """coverage_report dict 정합 검증 → 위반 메시지 목록 (빈 목록 = 정합)."""
    issues: List[str] = []
    for fld in COVERAGE_REPORT_FIELDS:
        if fld not in cov:
            issues.append(f"missing field: {fld}")
    if issues:
        return issues

    fc = cov["fail_class"]
    if fc is not None and fc not in FAIL_CLASSES:
        issues.append(f"unknown fail_class: {fc}")

    # fail_class 와 count 정합
    has_gold_dup = cov["gold_duplicate_count"] > 0
    has_drift = (cov["missing_count"] > 0 or cov["extra_count"] > 0
                 or cov["prediction_duplicate_count"] > 0)
    if has_gold_dup and fc != "GOLD_SAMPLE_ID_DUPLICATE":
        issues.append("gold_duplicate_count > 0 이나 fail_class 미설정")
    elif (not has_gold_dup) and has_drift and fc != "FULL_EVAL_COVERAGE_MISMATCH":
        issues.append("missing/extra/pred_dup 존재하나 fail_class 미설정")
    elif (not has_gold_dup) and (not has_drift) and fc not in (None,
            "SEMANTIC_LABEL_VIOLATION", "ACTION_UNIT_MISMATCH",
            "AB_COMPOSITION_MISMATCH"):
        issues.append("coverage 정합인데 fail_class 가 비-null")

    # count vs ids 정합
    for cnt, ids in [("missing_count", "missing_ids"),
                     ("extra_count", "extra_ids"),
                     ("gold_duplicate_count", "gold_duplicate_ids"),
                     ("prediction_duplicate_count", "prediction_duplicate_ids")]:
        if cov[cnt] == 0 and cov[ids]:
            issues.append(f"{cnt}=0 이나 {ids} 비어있지 않음")
    return issues


# 평가 evidence 검출 패턴 — branch_* 디렉토리의 평가 산출물
EVAL_EVIDENCE_GLOBS = [
    "evidence/day*/branch_*/summary.md",
    "evidence/day*/branch_*/ab_*.json",
    "evidence/day*/branch_*/full_eval_*.json",
]


def find_evaluation_evidence_dirs(root: Path) -> List[Path]:
    """평가 evidence 디렉토리 검출 (summary.md / ab_*.json / full_eval_*.json)."""
    eval_dirs: set = set()
    for pattern in EVAL_EVIDENCE_GLOBS:
        for path in root.glob(pattern):
            eval_dirs.add(path.parent)
    return sorted(eval_dirs)


def audit_evidence(root: Path) -> Dict[str, Any]:
    """평가 evidence 의 coverage_report.json 정합 감사 (fail-closed).

    Codex P1-C 정정: 평가 evidence 가 존재하는데 coverage_report.json 이
    0건이면 fail-closed 한다 (이전에는 `ok` 가 violations 만으로 산출되어
    artifact 누락이 fail-open 으로 통과했다 — dataset integrity 검사 우회).

    fail-closed 경로:
      1) `missing_required_artifact` — 평가 evidence 검출 + coverage_report
         0건 → `COVERAGE_REPORT_MISSING` violation 추가.
      2) `ok` 는 violations 가 비어있고 missing_required_artifact 가 아닐
         때만 true (return 라인에서 두 조건을 명시적으로 합산).
    """
    reports = sorted(root.glob("evidence/**/coverage_report.json"))
    eval_dirs = find_evaluation_evidence_dirs(root)
    audited: List[Dict[str, Any]] = []
    violations: List[Dict[str, Any]] = []

    # fail-closed #1: 평가 evidence 존재 + coverage_report 0건 → 필수 artifact 누락
    missing_required_artifact = bool(eval_dirs) and not reports
    if missing_required_artifact:
        violations.append({
            "fail_class": "COVERAGE_REPORT_MISSING",
            "message": (f"평가 evidence {len(eval_dirs)}개 디렉토리가 검출되었으나 "
                        f"coverage_report.json 0건 — Standard 9 는 모든 평가 "
                        f"evidence 에 coverage_report 를 요구한다."),
            "eval_evidence_dirs": [str(d.relative_to(root)) for d in eval_dirs],
        })

    for rp in reports:
        rel = str(rp.relative_to(root))
        try:
            cov = json.loads(rp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            violations.append({"file": rel, "issues": [f"읽기 실패: {exc}"]})
            audited.append({"file": rel, "ok": False})
            continue
        iss = validate_coverage_report(cov)
        audited.append({"file": rel, "ok": not iss})
        if iss:
            violations.append({"file": rel, "issues": iss})

    # fail-closed #2: ok 는 violations 부재 AND 필수 artifact 누락 아님
    ok = (not violations) and (not missing_required_artifact)
    return {"checked": len(reports), "audited": audited,
            "eval_evidence_dirs_count": len(eval_dirs),
            "missing_required_artifact": missing_required_artifact,
            "violations": violations, "ok": ok}


def main() -> int:
    result = audit_evidence(ROOT)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
