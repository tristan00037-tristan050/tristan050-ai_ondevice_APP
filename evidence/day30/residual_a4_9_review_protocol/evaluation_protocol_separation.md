# Evaluation Protocol Separation

## metadata
- actual_github_pr: 738
- legacy_handoff_label: PR #738+ (chat 인계 박스 표기)
- source_pr: 738
- branch: Residual-A4-9-Review-Protocol
- verdict: MEASURED_ONLY

## 분리 원칙

잔여 A4 9건은 text-only guard 로 안전 분리 불가하므로, 알고리즘 수정이
아니라 **평가 protocol** 로 분리한다.

## strict extraction 기준 유지

- 잔여 9건은 strict layer (Layer 1) 에서 **FP 로 유지** — FP→TP 처리 0.
- `strict_action_f1` 산식 불변. production gate 0.90 불변.
- 잔여 9건의 강제 차단/정정은 하지 않는다 (M-1/M-3).

## gold/contract review path

잔여 9건은 다음 경로로 분리 평가한다:

1. **별도 분류** — `residual_a4_9_본질_분석.json` 에 surface-form ambiguous
   over-extraction cases 로 별도 분류.
2. **Internal Alpha feedback** — 사용자 가치를 실측 (`internal_alpha_feedback_target.md`).
3. **contract review** — feedback 결과로 metric contract review (옵션 B).
   gold label 수정은 어떤 경로에서도 금지.

## Layer 2 평가 candidate

잔여 9건은 Layer 2 manual suggestion 평가의 candidate 다 —
`residual_a4_9_metric_연동_명세.json` 의 candidate metric
(manual_suggestion_precision / suggestion_usefulness_rate /
unsafe_suggestion_rate / edit_required_rate)으로 연동한다. 실제 metric
contract bump 는 권위 측정 후 (자문 6차 M-8).

## main 측정값 정합

평가 protocol 분리는 잔여 9건을 직접 수정하지 않는다 — main 측정값
(strict_action_f1 0.6452 / action_fp 207 / deadline_f1 0.8702 / safety
6종) 변동 0.
