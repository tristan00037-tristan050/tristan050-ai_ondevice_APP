# Standard 10 — Strict Policy Base Drift

Status: active from the next evaluation PR after PR #729
Scope: `scripts/eval/*`, `tests/eval/*`, `evidence/day*/`, label guide files,
evaluation PR descriptions
Codified by: GitHub PR #729 (Algorithm Branch 영역 변경 없음 — 정착 PR)
CI guard: `scripts/ci/check_standard_10.py`
Sentinel: `tests/standards/test_standard_10_strict_policy_base_drift.py`

## Purpose

평가 결과의 시계열 비교가 의미를 가지려면 평가 기준 자체가 시간에 따라
흔들리지 않아야 한다. metric threshold 가 슬그머니 바뀌거나 label guide 가
version 없이 변경되면, 이전 PR 의 측정값과 이후 PR 의 측정값을 비교할 수
없게 된다 (base drift).

자문 4차 8 은 Branch C-lite / 정밀 patch 진입 전에 Standard 10 을 정착할
것을 시급 권고했다. 본 표준은 metric threshold 변경 금지, label guide
version bump, before/after comparison, old/new policy drift report 를
단일 표준으로 정착시킨다.

## 원칙 1 — metric threshold 변경 금지

평가 기준(metric threshold)은 평가 PR 에서 변경할 수 없다. 시계열 비교의
기준점이기 때문이다.

정착 기준 (`check_standard_10.METRIC_THRESHOLDS`):

| metric | threshold | 방향 |
|---|---|---|
| `deadline_f1` | 0.86 | 외부 베타 기준 (하향 금지) |
| `normalized_action_f1` | 0.75 | 기준 (하향 금지) |
| `false_deadline_rate` | 0.02 | safety gate 상한 (상향 금지) |
| `no_action_fp_rate` | 0.03 | safety gate 상한 (상향 금지) |
| `auto_apply_precision` | 0.95 | 하향 절대 금지 |

`detect_metric_threshold_changes()` 가 평가 PR 의 threshold dict 를 정착
기준과 대조해 변경 키를 검출한다. 변경이 있으면 fail-closed.

## 원칙 2 — label guide 변경 시 version bump (SemVer)

label guide 가 변경되면 SemVer (`MAJOR.MINOR.PATCH`) version 을 반드시
bump 한다. version 없는 변경은 과거 결과와의 비교 가능성을 파괴한다.

version bump 대상:

- normalized_action label set
- deadline strength taxonomy (HARD / SOFT / INQUIRY / URGENCY / CONDITION / NONE)
- safety policy

`parse_semver()` / `is_version_bumped()` 가 version 형식과 증가 여부를
검증한다. label 의미 변경(MAJOR), label 추가(MINOR), 표기 정정(PATCH)에
맞춰 적절한 자리수를 올린다.

## 원칙 3 — before/after comparison 필수

Branch D-2 / C-lite 등 정밀 patch PR 은 patch 전 baseline 과 patch 후
측정값을 표로 비교해야 한다.

`before_after_comparison.json` 형식 (필수 필드 — `BEFORE_AFTER_FIELDS`):

```json
{
  "comparison": [
    {"metric": "deadline_f1", "before": 0.8438, "after": 0.8702,
     "delta": 0.0264}
  ]
}
```

`delta` 는 `after - before` 와 일치해야 하며, positive / negative / zero
모두 정직 보고한다 (Standard 12 연계).

## 원칙 4 — old policy vs new policy drift report

policy(label guide / 평가 정책)가 변경되면 drift report 를 작성한다.

`policy_drift_report.json` 형식 (필수 필드 — `DRIFT_REPORT_FIELDS`):

```json
{
  "policy_name": "deadline strength taxonomy",
  "old_policy_version": "1.0.0",
  "new_policy_version": "1.1.0",
  "drift_rate": 0.07,
  "drift_class": "PATCH_CONTINUE",
  "samples_compared": 500
}
```

## drift threshold 등급

`classify_drift(old_value, new_value)` — `drift_rate = |new - old| / |old|`:

| drift_rate | drift_class | 처리 |
|---|---|---|
| < 5% | `OK` | 정상 — 비교 가능성 유지 |
| 5% ~ 20% | `PATCH_CONTINUE` | drift 명시 + 추가 cycle |
| ≥ 20% | `HOLD` | 정착 보류 — base drift 과다 |

drift 가 5% 이상이면 그 사실을 숨기지 않고 명시하며, verdict 는
`PATCH_CONTINUE` 또는 `HOLD` 로 한정한다.

## 의무 적용 범위

- 모든 평가 PR 에 자동 적용된다.
- Branch C-lite / 정밀 patch PR 은 진입 전 본 표준을 충족해야 한다.
- CI guard `check_standard_10.py` 가 evidence 의 before/after comparison
  과 drift report 형식을 감사한다.
- 평가 PR template 의 Standard 10 체크리스트로 강제된다.
