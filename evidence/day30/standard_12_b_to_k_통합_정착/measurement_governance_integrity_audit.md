# Measurement / Governance Integrity Audit (Codex P1×2 — 강화 안건 19~23)

## metadata
- actual_github_pr: 739
- legacy_handoff_label: PR #739+ (chat 인계 박스 표기)
- source_pr: 739
- branch: Standard-12-B-to-K-Consolidation
- correction_cycle: Codex P1×2 (measurement / governance integrity)
- verdict: MEASURED_ONLY

## Codex P1 #1 — measurement integrity 결함

`before_after_main_metrics.json` 의 comparison 이 `MAIN_METRICS` **상수**
값으로 `before == after`, `delta 0.0` 를 생성했다. 실제 측정 없이 delta 0
을 출력 — Standard 12 정직 보고 본질 위반 가능.

**정정**: `read_authoritative_metrics()` 가 merged PR 의 권위 evidence
(day21 deadline / day26 strict_action_f1·action_fp)에서 측정값을 읽고,
`build_before_after_comparison()` 가 delta 를 실측 산출. 각 row 에
`source: authoritative_evidence`. 권위 evidence 누락 시 fail-closed
(ValueError).

## Codex P1 #2 — governance integrity 결함

`policy_drift_assessment.json` 이 `drift_rate: 0.0`, `drift_class: "OK"`,
`samples_compared: 0` 을 무조건 출력했다. contract drift 측정 없이 OK —
Standard 10 fail-closed gate 가 false pass.

**정정**: `measure_policy_drift(contract_before, contract_after)` 가
contract 입력을 key 단위 비교해 drift 산출. drift 발견 시 `DRIFT_DETECTED`
+ `fail_class`. `samples_compared` 는 contract 키 수 실측.
`is_standard10_policy_drift_report: True`.

## 강화 안건 19~23 정착

| 안건 | 내용 |
|---|---|
| 19 | HEAD SHA 정합성 — PR body 검토 기준 SHA ↔ 실제 latest head 동기 |
| 20 | MAIN_METRICS 하드코딩 금지 — 권위 evidence 기반 비교 의무 |
| 21 | drift_rate 하드코딩 금지 — contract 입력 비교 기반 의무 |
| 22 | measurement integrity fail-closed sentinel 의무 (delta 실측 검증) |
| 23 | governance integrity fail-closed sentinel 의무 (drift 검증) |

## fail-closed sentinel

- `#18` before/after 가 `source: authoritative_evidence` (강화 안건 20).
- `#19` policy_drift 가 `source: contract_input_comparison` (강화 안건 21).
- `#20` delta == after − before (measurement integrity, 강화 안건 22).
- `#21` drift_class DRIFT_DETECTED 시 fail_class 필수 (governance, 안건 23).
- `#22` head_sha_integrity_audit pr_body_review_sha == actual_latest_head_sha
  (강화 안건 19).

## 측정값 영향 (정직 보고 — 시나리오 1)

본 정정은 measurement/governance integrity 산식 정정이다. before/after 는
권위 evidence 에서 읽어도 동일(통합 정착 PR — 측정 변경 0) → delta 0
**실측 확인**. contract before/after 동일 → drift_rate 0 **실측 확인**.
하드코딩 0.0 을 실측 0.0 으로 대체 — main 측정값 분포 불변.

## 거버넌스 안전망 자기 진화 사례 4호

사례 1(PR #734 코드 패턴) / 사례 2(PR #737 작성 프로세스) / 사례 3(PR #738
Privacy meta-only) / **사례 4(PR #739 measurement·governance integrity —
Codex 봇 + 재검토팀)**. 강화 안건 19~23 (Standard 12-M~ 정량 기반).
