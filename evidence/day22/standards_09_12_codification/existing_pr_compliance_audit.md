# Existing PR Compliance Audit — PR #720~#727

## metadata
- source_pr: 728
- verdict: MEASURED_ONLY
- generated_at: 2026-05-16
- audit_scope: Standard 9 (Dataset Integrity) + Standard 12 (Honest Reporting)

## Standard 9 — coverage_report 정합 감사

`scripts/ci/check_standard_09.py audit_evidence()` 실측 결과.

| PR | Algorithm Branch | evidence day | coverage 형태 | 12 필드 | fail_class |
|---|---|---|---|---|---|
| #720 | B (prompt/schema) | day16 | full_eval_impact_summary 내장 | 부분 | null |
| #722 | B-2 (over-extraction) | day17 | full_eval_impact_summary 내장 | 부분 | null |
| #723 | D (measurement) | day18 | full_eval_impact_summary 내장 | 10 필드 | null |
| #724 | D (classifier) | day19 | full_eval_impact_summary.coverage_report | 정합 | null |
| #725 | B-3A (arbitration meas.) | day19 | coverage_report.json (독립) | **12 필드 ✓** | null |
| #726 | B-3B (arbitration apply) | day20 | coverage_report.json (독립) | **12 필드 ✓** | null |
| #727 | D-2 (targeted deadline) | day21 | coverage_report.json (독립) | **12 필드 ✓** | null |

독립 `coverage_report.json` 전수 감사: 3/3 정합 (위반 0건).

## 관측 — coverage 필드 진화

- PR #722 cycle: coverage 6 → 10 필드 (gold duplicate 탐지 추가).
- PR #726 cycle: coverage 10 → 12 필드 (prediction duplicate 추가).
- PR #720~#723 은 coverage 가 `full_eval_impact_summary.json` 에 내장되어
  독립 `coverage_report.json` 미존재 — Standard 9 정착 이전 형태.
- **정직 보고**: PR #720~#723 evidence 를 소급 12 필드로 재작성하지 않는다.
  Standard 9 는 정착 이후 평가 PR 부터 의무 적용 (소급 측정값 조정 금지).

## Standard 12 — Honest Reporting 정합 감사

| PR | STATUS | expected_vs_observed | delta 정직 보고 | natural shortage | latent bug 정직 보고 |
|---|---|---|---|---|---|
| #722 | PATCH_CONTINUE | 부분 | ✓ | n/a | — |
| #723 | PATCH_CONTINUE | 부분 | ✓ | n/a | BEHIND state 진단 명시 |
| #724 | PATCH_CONTINUE | ✓ | ✓ | NATURAL_SHORTAGE 명시 | — |
| #725 | MEASURED_ONLY | ✓ | ✓ (음수 포함) | n/a | MIXED-A 67건 A6 latent bug 명시 |
| #726 | PATCH_CONTINUE | ✓ | ✓ | ✓ | AR-2 hybrid merge noop 정직 보고 |
| #727 | PATCH_CONTINUE | ✓ | ✓ (HARD↔SOFT 미달 명시) | n/a | P1 산식 정정 정직 보고 |

PR #725~#727 은 Standard 12 패턴을 사실상 준수 — expected vs observed,
negative delta, latent bug, measurement integrity 를 모두 정직 보고.
PR #720~#723 은 expected_vs_observed 항목이 부분적 — 정착 이후 의무화.

## verdict 경계 감사

- PR #720~#727 verdict 는 MEASURED_ONLY / PATCH_CONTINUE 만 사용 — 금지
  대상 verdict 출현 0건 ✓
- forbidden grep 10 패턴: 각 PR evidence 0건 (각 PR 보고에 명시) ✓

## Codex P1-B 정정 후 scan 범위 재검증

CI guard scan 범위를 `evidence/day22` hardcoded → `evidence/day*/` 전체로
확장한 뒤 재실측.

- `check_standard_12.py audit_summaries()`: scan 대상 summary.md 9건
  (day15~day22), forbidden 패턴 위반 0건.
- `check_standard_09.py audit_evidence()`: coverage_report.json 3건 +
  평가 evidence 6 디렉토리 검출, fail-closed 조건 미발동, ok=true.
- day23+ 폴더 추가 시 자동 scan 대상 포함 — 영구 우회 경로 차단.

## 종합

- Standard 9: 독립 coverage_report.json 3종 (#725/#726/#727) 12 필드 정합.
  #720~#723 은 정착 이전 형태 — 소급 미적용 (honest, 측정값 조정 0).
- Standard 12: #725~#727 사실상 준수, #720~#723 부분 준수 → 정착으로
  전 평가 PR template 자동 적용. scan 범위는 day* 전체로 확장 (P1-B).

## verdict: MEASURED_ONLY
