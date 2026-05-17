# Semantic-aware Guard v0 Candidate (자문 6차 §5/M-7)

## metadata
- actual_github_pr: 738
- legacy_handoff_label: PR #738+ (chat 인계 박스 표기)
- source_pr: 738
- branch: Residual-A4-9-Review-Protocol
- verdict: MEASURED_ONLY

## 목적

잔여 A4 9건에 대한 semantic-aware guard v0 의 **candidate generation**
(후보 형태 명세). 실제 구현·적용은 별도 PR — Internal Alpha feedback
수집 후 post-hoc policy 데이터 기반.

## 허용 형태 (자문 6차 §5/M-7)

| candidate | 설명 |
|---|---|
| post-hoc policy | Internal Alpha feedback 기반 사후 정책 (추론 후 단계) |
| warning badge | manual review 단계 high-risk suggestion '검토 필요' 표시 |
| low_confidence marking | 차단 아님 — 우선순위 조정 (낮은 confidence 표기) |

핵심: guard 는 **차단(block)이 아니라 표시(mark)** — auto_apply OFF 유지,
사용자가 manual review 에서 위험을 인지하도록 보조.

## 절대 금지 형태 (자문 6차 §12)

- prompt recall 강화 (Branch B-2R) — 금지.
- LoRA / fine-tuning — 금지.
- 모델 교체 (Branch F) — 금지.
- auto_apply gate 완화 — 금지.
- text-only guard 추가 강화 (자문 6차 M-1) — 금지.

## Internal Alpha feedback 기반 rule 후보

잔여 9건의 4 카테고리 feedback 수집 후:
- `unsafe` 다수 → 해당 표면형에 warning badge candidate.
- `needs_edit` 다수 → low_confidence marking candidate.
- `useful` 다수 → guard 불요, manual suggestion 으로 유지.

본 PR 은 candidate 형태만 정의 — rule 확정은 권위 feedback 후 별도 PR.

## main 측정값 정합

candidate generation 은 명세 정착만 — 알고리즘/측정 변경 0. main 측정값
변동 0.
