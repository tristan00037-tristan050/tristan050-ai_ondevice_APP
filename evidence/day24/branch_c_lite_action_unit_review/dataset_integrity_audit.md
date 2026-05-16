# Dataset Integrity Audit — Codex P1 2건 정정

## metadata
- source_pr: 730
- correction_cycle: Codex P1 (2건)
- branch: C-lite
- verdict: MEASURED_ONLY
- generated_at: 2026-05-16

## 정정 대상

Codex P1 2건 — `scripts/eval/pr730_branch_c_lite_review.py` 의 dataset
integrity 결함. 분석 PR 본질 (gold / 알고리즘 / 측정값 변경 0) 은 불변.

## P1-A — raw MIXED-A source rows duplicate fail-closed

- 결함: `src_rows = {r["sample_id"]: r for r in mixed["rows"]}` dict
  comprehension 이 duplicate sample_id 를 silently collapse → `mixed_ids`
  가 이미 unique 가 되어, source classification 파일에 중복이 있어도
  통과했다.
- 정정: `detect_duplicates()` 로 raw `mixed_id_list` 단계에서 중복 검출.
  중복 발견 시 `fail_class=SOURCE_SAMPLE_ID_DUPLICATE` + return 1
  (downstream 분석 차단).
- `gold_duplicate_count` 를 raw 기준으로 산출 (이전엔 collapse 후 항상 0).

## P1-B — predictions duplicate fail-closed

- 결함: `preds[p["sample_id"]] = p` dict assignment 이 duplicate
  sample_id 를 silently overwrite → `prediction_duplicate_count` 가 0 으로
  고정, 중복 prediction 이 review set 을 오염시킬 수 있었다.
- 정정: `load_inputs()` 가 `pred_rows` raw list 를 보존. `detect_duplicates()`
  로 `pred_id_list` 중복 검출. 중복 발견 시
  `fail_class=FULL_EVAL_COVERAGE_MISMATCH` + return 1.
- `prediction_duplicate_count` 를 raw 기준 초과 건수로 산출 (고정값 0 제거).

## coverage_report 재생성 (raw vs unique 정합)

| 필드 | 값 |
|---|---|
| expected_samples | 67 |
| measured_samples | 67 |
| gold_duplicate_count | 0 |
| prediction_duplicate_count | 0 |
| source_sample_ids_count | 67 |
| source_sample_ids_unique_count | 67 |
| prediction_sample_ids_count | 500 |
| prediction_sample_ids_unique_count | 500 |
| fail_class | null |

raw count == unique count — MIXED-A source 67건 / predictions 500건 모두
중복 0건. fail-closed 조건 미발동 (정합).

## 정정 후 PR #730 본질적 결론 정합 유지

| 결론 | 정정 전 | 정정 후 | 정합 |
|---|---|---|---|
| MIXED-A 67건 unique | 67 | 67 | 유지 |
| predictions unique | (미산출) | 500 | 정합 |
| A1 action_unit_mismatch | 0/30 | 0/30 | 유지 |
| A3 product_equivalent | 23/30 | 23/30 | 유지 |
| A4 true_model_error | 7/30 | 7/30 | 유지 |
| 정식 Branch C 진입 | 부적합 | 부적합 | 유지 |

→ dataset integrity 산식 정정은 raw 입력에 중복이 없음을 확인했을 뿐,
PR #730 의 본질적 결론을 변경하지 않는다.

## 정직 보고 (Standard 12 자기 적용)

P1-A/B 는 PR #725 latent bug fail-closed 정착 + PR #728 P1-C fail-closed
패턴과 동일 계열의 결함이다. 해당 패턴이 PR #730 인계 박스에 dataset
integrity 항목으로 명시되지 못한 한계 — Codex 봇이 동일 패턴을 사전
차단 (4중 안전망 정확 작동). 정정은 PR #728 패턴(raw 보존 + 중복 검출
fail-closed)을 그대로 재사용.

## verdict: MEASURED_ONLY
