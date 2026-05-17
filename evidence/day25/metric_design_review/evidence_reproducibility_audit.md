# Evidence Reproducibility Audit (Codex P2)

## metadata
- source_pr: 731
- branch: Metric-Design-Review
- correction_cycle: Codex P2 (evidence 재현성 정정)
- verdict: MEASURED_ONLY

## 원칙 — tracked artifact 는 deterministic

git 으로 tracked 되는 evidence artifact 는 동일 입력에 대해 동일 출력이어야
한다. 재실행마다 값이 바뀌는 필드가 있으면:

- 무의미한 diff 가 발생해 검토자가 실제 변경을 식별하기 어렵다.
- 재현성 검증 (재실행 후 diff 0) 이 불가능하다.

## Codex P2 결함 본질

`_meta()` 가 `_now()` (wall-clock `datetime.now`) 기반 `generated_at` 을
모든 tracked evidence 에 기록했다. PR #731 의 10개 evidence 파일이 매
실행마다 `generated_at` 만 다른 diff 를 생성 — 재현성 훼손.

## 정정

- `_meta()` 에서 `generated_at` 필드 제거 (선택 A — 단순·명확).
- 미사용이 된 `_now()` 함수 및 `datetime` import 제거 (dead code 제거).
- tracked evidence 는 입력(dataset / predictions / MIXED-A source)에만
  의존 — 동일 입력 → 동일 출력.

## 재현성 정량 보증

P2 정정 후 `pr731_metric_design_review.py` 2회 연속 실행:

```
find evidence/day25/metric_design_review -name '*.json' -o -name '*.md' \
  | sort | xargs shasum  →  1차 / 2차 diff 0
```

재실행 diff **0** — deterministic 정합 입증.

## 강화 안건 10번 정착 사례

본 정정은 강화 안건 10번 (evidence 재현성 의무 — tracked artifact 는
wall-clock 비의존) 의 정착 사례다. 후속 평가 PR 의 evidence 생성 시
`generated_at` 류 wall-clock 필드를 tracked artifact 에 기록하지 않는다.
실행 시각이 필요하면 untracked 로그로 분리한다.

## Standard 12 정직 보고

P2 는 측정값이 아니라 evidence metadata 의 결함이었다. main 측정값
(strict_action_f1 0.6182 / deadline_f1 0.8702 / action_fp 234) 및 Layer 2
분포는 P2 정정의 영향을 받지 않는다.
