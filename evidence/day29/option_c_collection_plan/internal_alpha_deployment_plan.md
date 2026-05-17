# Internal Alpha Deployment Plan

## metadata
- source_pr: 737
- branch: Option-C-Collection-Plan
- verdict: MEASURED_ONLY

## 카드 1 내부 알파 정식 진입 결정 확정 경계

카드 1 내부 알파 정식 진입은 main 정착 완료 (STATUS=ALPHA_PROMOTION).
본 배포 계획은 그 확정 경계를 정합 준수한다:

1. **auto_apply OFF** — 절대 준수 (자문 6차 M-14).
2. **manual review only** — 모든 suggestion 은 사용자 수동 검토 (M-14).
3. **Controlled Beta 아님** — msp 권위 측정 ≥ 0.80 + dangerous 개선 후
   별도 결정 (자문 6차 M-13).
4. **Production Candidate 아님** — strict_action_f1 ≥ 0.90 시 별도 결정.
5. 금지 verdict 및 출시·상용 단계 표현은 사용하지 않는다 (계획 PR).

## 배포 대상

Internal Alpha 사용자 (사내 폐쇄 환경). 외부 전송 경로 없음.

## 배포 시점

본 PR 머지 후 별도 운영 단계. 본 PR 은 계획만 정착한다.

## 운영 조건

- auto_apply OFF — 자동 실행 없음. suggestion 은 manual review 대상.
- manual review only — 사용자가 각 suggestion 을 수동 채택/무시.
- 수집 feedback 은 4 카테고리 (useful / irrelevant / unsafe / needs_edit).
- privacy guarantee — digest 저장, 외부 전송 0 (`privacy_guarantee_audit.md`).
- 사용자 동의 — `user_consent_protocol.md` 정합.

## 모니터링 protocol (PR #733 계측 인프라)

- alpha_feedback collection pipeline 이 feedback 을 digest 로 수집.
- audit logger 가 모든 feedback 레코드를 1:1 기록.
- unsafe 카테고리 발생 시 즉시 검토 (semantic-aware guard v0 warning).
- msp / κ / unsafe_suggestion_rate 를 sample size 충족 시점에 집계.

## main 측정값 정합

배포는 계측만 수행 — 알고리즘/prompt/model 변경 0. main 측정값
(strict_action_f1 0.6452 / deadline_f1 0.8702 / safety 6종) 변동 0.
