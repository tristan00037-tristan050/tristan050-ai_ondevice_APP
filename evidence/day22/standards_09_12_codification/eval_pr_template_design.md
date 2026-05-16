# Evaluation PR Template Design

## metadata
- source_pr: 728
- verdict: MEASURED_ONLY
- generated_at: 2026-05-16

## 목적

평가 PR (`scripts/eval/*` · `tests/eval/*` · `evidence/day*/`) 에 운영 표준
1~12 를 자동 적용하는 전용 PR template 정착.

## 파일

`.github/PULL_REQUEST_TEMPLATE/eval_pr.md` (신규)
- 기존 `.github/pull_request_template.md` (Enterprise OS 기본 template) 는 유지.
- 평가 PR 작성 시 `?template=eval_pr.md` 로 선택 적용.

## 체크리스트 구성

| 섹션 | 항목 수 | 표준 |
|---|---|---|
| STATUS | 1 | Standard 12 (MEASURED_ONLY/PATCH_CONTINUE/HOLD) |
| Standard 9 — Dataset Integrity | 5 | Standard 9 |
| Standard 12 — Honest Reporting | 6 | Standard 12 |
| 회귀 monitor | 3 | Branch B-2 / D / safety |
| sentinel test | 4 | Standard 4 / 7 / 9 / 11 |
| forbidden grep | 2 | Standard 12 |
| 운영 표준 1~12 점검 | 4 | Standard 1/2/3/5/8 |

## 정합 원칙

- STATUS 라인은 본문 최상단, PROCEED verdict 출현 금지.
- 검토 기준 head SHA 를 개요에 명시 (Standard 2).
- Algorithm Branch 라벨과 GitHub PR 번호 분리 표기 (Standard 5).
- coverage_report 12 필드 / expected_vs_observed / delta 정직 보고 필수.

## verdict: MEASURED_ONLY
