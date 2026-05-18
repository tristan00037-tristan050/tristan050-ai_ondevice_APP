# PR #737 — option C 수집 계획 Summary

## metadata
- dataset_id: card1_evalset_v1_1_500
- actual_github_pr: 737
- legacy_handoff_label: PR #735+ (chat 인계 박스 표기)
- source_pr: 737
- branch: Option-C-Collection-Plan
- patch_type: collection_plan_no_algorithm_no_measurement
- verdict: MEASURED_ONLY
- correction_cycle: 메타데이터 정합 정정 (PR 번호 #735→#737)

## 메타데이터 정합 정정 (강화 안건 17 — 정직 보고)
- 결함: chat 인계 박스가 'PR #735+' 표기를 사용했으나 실제 GitHub PR 은 #737. PR title/body/evidence 의 source_pr 가 735 로 고정됨.
- 정정: actual_github_pr 737 / legacy_handoff_label 'PR #735+' 분리 기록. source_pr 를 실제 번호 737 로 정정 (옵션 B — 파일명 유지).
- 측정값 영향 0 — 메타데이터 정정만. main 측정값 / sentinel / 회귀 정합 유지 (시나리오 1 분포 불변).

## 본 PR 의 본질 (정직 보고)
- 계획 PR — 정식 Internal Alpha 배포 계획 + option C 권위 측정 protocol 정착. 측정값 변경 0, 새 측정 알고리즘 0, 알고리즘/prompt/model 변경 0.
- 카드 1 내부 알파 정식 진입 결정 (STATUS=ALPHA_PROMOTION) 후속 — auto_apply OFF + manual review only 절대 준수 (자문 6차 M-14).

## 자문 5차 → 자문 6차 정정 정직 보고
- 최소 sample size: 자문 5차 50건 → 자문 6차 M-12 최소 100 / 권장 150 / 강한 권장 200.
- 잔여 A4 9건: 자문 5차 4 옵션 → 자문 6차 M-5 옵션 D 1순위.
- semantic-aware guard: 자문 6차 §5 허용 형태 (post-hoc policy + warning + low_confidence marking) 정량 정의.
- Controlled Beta 진입: 자문 6차 §11 8 조건 정량 명시.
- reviewer 구성: 자문 6차 §10 최소 2명 + 권장 3명 + adjudicator.

## option C 권위 측정 path
- 4 카테고리 user feedback: useful / irrelevant / unsafe / needs_edit.
- 최소 100건 / 권장 150건 stratum 구성.
- Cohen's κ 개선: 현 proxy 0.6735 → 권위 목표 >= 0.7 (calibration round 10건).
- proxy 한계 정직 (Standard 12-H) — 권위 측정 전 Controlled Beta 진입 결정 불가 (자문 6차 M-10/M-13).

## main 측정값 정합 (변동 0)
- strict_action_f1 0.6452 / deadline_f1 0.8702 / action_fp 207 / safety 6종 — 전부 불변. metric contract v2.0.0 유지.

## verdict: MEASURED_ONLY
계획 PR — 금지 verdict 미사용. forbidden grep 10 패턴 0건.