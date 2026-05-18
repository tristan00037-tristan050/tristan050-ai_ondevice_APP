# Standard 12-L — Privacy / Measurement / Governance Integrity (통합)

## metadata
- actual_github_pr: 740
- legacy_handoff_label: PR #740+ (chat 인계 박스 표기)
- source_pr: 740
- standard_id: 12-L
- branch: Standard-12-L-Consolidation
- verdict: MEASURED_ONLY

## 본질

강화 안건 18~23 (6건)을 Standard 12-L 단일 표준으로 통합 정착한다.
Privacy 핵심 가치 + measurement integrity + governance integrity 를
하나의 통합 표준으로 묶어 모든 evidence 생성 PR 에 의무 적용한다.

## 통합 6 안건

| 안건 | 이름 | 정착 PR | 산출물 |
|---|---|---|---|
| 18 | Privacy meta-only audit | #738 | privacy_meta_only_audit.md |
| 19 | HEAD SHA 정합성 메타데이터 무결성 | #739 | head_sha_integrity_audit.json |
| 20 | MAIN_METRICS evidence 기반 검증 | #739 | before_after_main_metrics.json |
| 21 | drift_rate contract 입력 비교 기반 | #739 | policy_drift_assessment.json |
| 22 | measurement integrity fail-closed sentinel | #739 | measurement_governance_integrity_audit.md |
| 23 | governance integrity fail-closed sentinel | #739 | measurement_governance_integrity_audit.md |

## 의무 적용 규칙

모든 evidence 생성 PR 은 다음을 준수한다:

1. **Privacy meta-only** — 원문 utterance 를 evidence 에 저장하지 않는다.
   필요 시 `utterance_digest` (sha256)로만 기록 (안건 18).
2. **HEAD SHA 정합** — PR body 검토 기준 SHA 를 실제 latest head 와
   동기화한다 (안건 19).
3. **measurement 권위 evidence 기반** — before/after 측정값을 상수
   하드코딩하지 않고 권위 evidence 에서 읽어 delta 를 실측한다 (안건 20).
4. **governance contract 입력 비교** — drift_rate 를 하드코딩하지 않고
   contract before/after 입력 비교로 산출한다 (안건 21).
5. **fail-closed sentinel** — delta·drift 검증 sentinel 을 의무화하고,
   불일치 시 fail-closed 한다 (안건 22/23).

## Standard 12 와의 관계

Standard 12-L 은 Standard 12-B~K 에 이은 11번째 하위 표준이다. Privacy
(핵심 가치)와 measurement/governance integrity 를 통합하여, evidence
생성 자체의 무결성을 보증한다.

## main 측정값 정합

본 통합 정착은 표준 문서 통합만 — 측정/알고리즘 변경 0. main 측정값
(strict_action_f1 0.6452 / deadline_f1 0.8702 / action_fp 207 / safety
6종) delta 0 (권위 evidence 기반 실측 확인).
