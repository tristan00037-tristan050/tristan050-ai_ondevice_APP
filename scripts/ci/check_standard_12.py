"""Standard 12 — Honest Reporting Pattern CI guard.

평가 PR 의 보고가 실패를 숨기지 않는지 fail-closed 로 검증한다. 측정값을
변경하지 않으며, 보고 텍스트의 패턴만 검사한다.

정착 근거: "실패를 숨기지 않는 것 = 가장 중요한 성공" (자문 4차 8 명시).
정직 보고 패턴은 거버넌스 안전망 신뢰의 기반이다.

reusable API (sentinel test 가 import):
  - FORBIDDEN_PATTERNS       : 기존 forbidden grep 10 패턴
  - STANDARD_12_PATTERNS     : Standard 12 확장 패턴 (측정값 임의 조정 등)
  - ALLOWED_STATUS           : 허용 STATUS 토큰
  - scan_forbidden()         : 텍스트 → forbidden 매칭 목록
  - validate_status_line()   : STATUS 라인 정합 검증
  - validate_honest_report() : 보고 dict 정직성 검증
  - requires_root_cause_reeval() : 추정 vs 실측 괴리 → 재평가 의무 여부
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]

# ── 기존 forbidden grep 10 패턴 (test_forbidden_strings_day14 정합) ─────────
FORBIDDEN_PATTERNS: List[str] = [
    r"production candidate approved",
    r"PRODUCTION_CANDIDATE_PASS",
    r"release ready",
    r"beta ready",
    r"external beta ready",
    r"auto_apply_accuracy",
    r"card1_gold_v1\b",
    r"BUTLER_INTEGRATION_READY",
    r"PROCEED",
    r"최종 승인",
]

# ── Standard 12 확장 패턴 — 측정값 임의 조정 / 실패 은폐 신호 ───────────────
STANDARD_12_PATTERNS: List[str] = [
    r"측정값[^\n]{0,8}(임의|수동)[^\n]{0,4}조정",
    r"(threshold|임계값)[^\n]{0,12}(낮춰|낮춤|하향)",
    r"실패[^\n]{0,6}숨기",
    r"회귀[^\n]{0,6}(은폐|숨김)",
    r"테스트[^\n]{0,8}(완화|느슨하게)[^\n]{0,8}통과",
]

# ── 허용 STATUS 토큰 (PROCEED 는 금지) ─────────────────────────────────────
ALLOWED_STATUS = {"MEASURED_ONLY", "PATCH_CONTINUE", "HOLD"}

# ── 정직 보고 필수 항목 ────────────────────────────────────────────────────
REQUIRED_REPORT_KEYS = ["expected", "observed"]


def scan_forbidden(text: str) -> List[str]:
    """텍스트에서 forbidden 10 + Standard 12 확장 패턴 매칭 목록."""
    hits: List[str] = []
    for pat in FORBIDDEN_PATTERNS + STANDARD_12_PATTERNS:
        if re.search(pat, text):
            hits.append(pat)
    return hits


def validate_status_line(text: str) -> List[str]:
    """본문 STATUS 라인 정합 — 허용 토큰 1개 + PROCEED 부재."""
    issues: List[str] = []
    m = re.search(r"STATUS\s*=\s*([A-Z_]+)", text)
    if not m:
        issues.append("STATUS= 라인 누락")
        return issues
    status = m.group(1)
    if status not in ALLOWED_STATUS:
        issues.append(f"허용되지 않은 STATUS: {status} "
                      f"(허용: {sorted(ALLOWED_STATUS)})")
    if re.search(r"\bPROCEED\b", text):
        issues.append("PROCEED 토큰 발견 — 정착/측정 PR 에서 금지")
    return issues


def validate_honest_report(report: Dict[str, Any]) -> List[str]:
    """보고 dict 정직성 검증.

    필수: expected_vs_observed, delta 명시 (0 포함), natural_shortage 명시.
    """
    issues: List[str] = []
    evo = report.get("expected_vs_observed")
    if evo is None:
        issues.append("expected_vs_observed 누락")
    elif isinstance(evo, dict):
        for k in REQUIRED_REPORT_KEYS:
            if k not in evo:
                issues.append(f"expected_vs_observed.{k} 누락")

    # delta 는 0 이어도 명시 의무
    if "delta" not in report:
        issues.append("delta 누락 — 0/음수도 명시 의무")

    # natural shortage 가 발생했으면 명시 의무
    if report.get("natural_shortage") and not report.get("natural_shortage_note"):
        issues.append("natural_shortage=true 이나 natural_shortage_note 미명시")
    return issues


def requires_root_cause_reeval(expected: float, observed: float,
                                tol: float = 0.5) -> bool:
    """추정 회복량 대비 실측이 tol 비율 미만이면 원인 재평가 의무 (PR #725 정합).

    expected <= 0 이면 추정 자체가 없으므로 재평가 불요.
    """
    if expected <= 0:
        return False
    return observed < expected * tol


# ── PROCEED 위반 판정 — line/context 기반 (Codex P1-A 정정) ────────────────
_PROCEED_RE = re.compile(r"\bPROCEED\b")
_NEGATION_RE = re.compile(r"(절대|금지|불가|prohibit|forbidden)")


def is_proceed_violation_in_text(text: str) -> bool:
    """PROCEED 위반 검증 — variable-width lookbehind 미사용.

    Python `re` 는 가변폭 lookbehind 를 지원하지 않으므로 `(?<!금지[^\n]{0,4})`
    형태는 re.error 를 일으킨다 (Codex P1-A). 대신 line 단위로 스캔하고
    같은 line 에 부정 단어(절대/금지/불가/prohibit/forbidden)가 있으면
    설명문으로 간주해 위반에서 제외한다.

    - "PROCEED 절대 금지" / "금지 verdict (PROCEED)" → pass (설명문)
    - "결론: PROCEED" / "verdict: PROCEED" → violation
    """
    for line in text.splitlines():
        if _PROCEED_RE.search(line) and not _NEGATION_RE.search(line):
            return True
    return False


def audit_summaries(root: Path) -> Dict[str, Any]:
    """evidence/day*/ 하위 summary.md 의 forbidden 패턴 0건 검증.

    Codex P1-B 정정: day22 hardcoded → evidence/day*/ 전체로 scan 범위 확장
    (day23+ 폴더로 영구 우회 불가).
    """
    summaries = sorted(root.glob("evidence/day*/**/summary.md"))
    violations: List[Dict[str, Any]] = []
    for sp in summaries:
        text = sp.read_text(encoding="utf-8")
        hits = scan_forbidden(text)
        # PROCEED 는 line/context 기반으로 별도 판정 (설명문 제외)
        real_hits = [h for h in hits if h != r"PROCEED"]
        if is_proceed_violation_in_text(text):
            real_hits.append(r"PROCEED")
        if real_hits:
            violations.append({"file": str(sp.relative_to(root)),
                               "patterns": real_hits})
    return {"checked": len(summaries), "violations": violations,
            "ok": not violations}


def main() -> int:
    result = audit_summaries(ROOT)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
