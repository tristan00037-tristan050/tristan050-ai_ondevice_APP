# Privacy Meta-only Audit (강화 안건 18 — Codex P1 정정)

## metadata
- actual_github_pr: 738
- legacy_handoff_label: PR #738+ (chat 인계 박스 표기)
- source_pr: 738
- branch: Residual-A4-9-Review-Protocol
- correction_cycle: Codex P1 (Privacy meta-only)
- verdict: MEASURED_ONLY

## Codex P1 결함 본질

`pr738_residual_a4_9_review_protocol.py` 가 `residual_a4_9_본질_분석.json`
의 각 row 에 원문 utterance(`text`)를 직접 저장했다. Butler 핵심 가치
(Privacy) 위반 — AGENTS.md meta-only/원문0 원칙, Butler 지침서 §7,
PR #733 privacy audit (raw_text_leak 0), 자문 6차 권위 측정 path 의
원문 비저장 원칙 위반 가능.

## 정정 — meta-only

| 정정 전 (결함) | 정정 후 (meta-only) |
|---|---|
| `text`: 원문 utterance | (제거) |
| — | `utterance_digest`: sha256 16자 |
| — | `text_len`: 길이 메타 |
| — | `redaction_status`: "meta_only" |

row 의 허용 키는 `sample_id` / `surface_form` / `gold_intent` /
`utterance_digest` / `text_len` / `redaction_status` 6종으로 한정한다.
원문은 `classify_residual()` 등 내부 계산에만 사용하고 산출물에 기록하지
않는다.

## Privacy meta-only 표준 (강화 안건 18)

1. evidence 산출물의 어떤 row 에도 원문 utterance 키(`text` / `raw_text` /
   `utterance` / `raw_utterance` / `original_text`)를 저장하지 않는다.
2. 원문이 필요한 경우 `utterance_digest` (sha256 16자)로만 기록한다.
3. 분류/판정 결과는 메타 필드(surface_form / gold_intent / text_len 등)
   로만 저장한다.
4. sentinel 로 원문 키 부재를 검증한다 (negative test 의무).

## sentinel 정합 보증

- `#15 test_rows_내_text_키_부재` — 원문 키 부재 검증.
- `#16 test_meta_only_정합` — 허용 6키만 + redaction_status meta_only.
- `#17 test_utterance_digest_정합` — sha256 16자 패턴.

## 정합 출처

- AGENTS.md meta-only / 원문0 원칙.
- Butler 대표 지침서 §7 (Privacy 절대 금지 항목).
- PR #733 privacy audit (raw_text_leak 0 + 외부 전송 0).
- 자문 6차 권위 측정 path 의 digest 저장 원칙.

## 측정값 영향 (정직 보고 — 시나리오 1)

본 정정은 evidence 산출물의 privacy 정합 정정만이다. main 측정값
(strict_action_f1 0.6452 / deadline_f1 0.8702 / action_fp 207 / safety
6종) delta 0, 잔여 A4 9건 분류 분포(polite 7 / intent_to_report 2) 불변.

## 거버넌스 안전망 자기 진화 사례 3호

- 사례 1 (PR #734): 코드 패턴 latent gap (Codex 봇).
- 사례 2 (PR #737): 작성 프로세스 결함 (재검토팀).
- 사례 3 (PR #738): Privacy meta-only 표준 정량 정착 (Codex 봇).

강화 안건 18번 (Privacy meta-only audit, Standard 12-L 정량 기반)으로
정착한다. 향후 모든 evidence 생성 PR 은 본 표준을 의무 적용한다.
