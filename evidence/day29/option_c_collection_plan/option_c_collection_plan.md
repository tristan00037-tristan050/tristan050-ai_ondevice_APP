# option C Collection Plan (자문 6차 정합)

## metadata
- source_pr: 735
- branch: Option-C-Collection-Plan
- verdict: MEASURED_ONLY

## 목적

PR #733 의 manual_suggestion_precision (msp)은 deterministic
reviewer-simulation **proxy** 다. Controlled Beta 진입 정량 결정에는
권위 측정(option C — 실제 Internal Alpha user feedback)이 필요하다
(자문 6차 M-10). 본 계획은 정식 Internal Alpha 배포 후 option C 권위
측정 수집 protocol 을 정착한다.

## 4 카테고리 user feedback (자문 6차 §3.4)

| 카테고리 | 의미 |
|---|---|
| `useful` | manual suggestion 이 사용자에게 유용 |
| `irrelevant` | suggestion 이 무관 |
| `unsafe` | suggestion 이 위험/부적절 |
| `needs_edit` | suggestion 이 수정 필요 (부분 유용) |

`manual_suggestion_precision = useful / (useful + irrelevant + unsafe +
needs_edit)`.

## sample size (자문 6차 M-12)

- 최소 **100건**, 권장 **150건**, 강한 권장 **200건**.
- 자문 5차 6.5 의 ≥ 50건에서 상향 정정 — n=50 은 msp 비율 지표가
  흔들리고, n≥100 에서 해석 가능 (신뢰 구간 95%).
- stratum 구성은 `sample_stratum_구성.json` 참조.

## 수집 인프라 (PR #733 활용)

- `alpha_feedback_schema_v1` — feedback 레코드 schema.
- collection pipeline — collector → digest → privacy guard → audit logger.
- digest 저장 (raw text 0) / 외부 전송 0 — `privacy_guarantee_audit.md`.

## 수집 기간

정식 Internal Alpha 배포 후 sample size 충족 시점까지. auto_apply OFF +
manual review only (자문 6차 M-14) 운영 조건 하에서만 수집한다.

## 후속

option C 권위 측정 완료 → `controlled_beta_8조건_정량.json` 8 조건 정량
평가 → Controlled Beta 진입 정량 결정 (별도 판정 PR). 본 PR 은 계획만
정착하며 진입 결정을 내리지 않는다 (PROCEED 금지).
