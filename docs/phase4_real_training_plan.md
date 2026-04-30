# Phase 4 실제 학습 계획 (Week 2-4)

## 현황 (베타 1차 기준)

`train_student_qlora_worldclass_v1.py`는 현재 `--dry-run` 모드만 지원.
`--dry-run` 없이 실행 시 `status=NOT_IMPLEMENTED`, `exit 2`로 안전하게 차단.
실제 학습 로직은 본 문서가 정의하는 Week 2-4 단계에서 구현.

## 학습 환경 2단계

### 1단계 — 검증 학습 (Week 2)

| 항목 | 값 |
|------|----|
| 인프라 | 네이버클라우드 HPC GPU VM — L40S × 2 |
| 데이터 규모 | 1,000 ~ 5,000 스텝 (소규모 검증) |
| 목적 | 파이프라인 정상 동작 확인, 수렴 여부 조기 검증 |
| 완료 조건 | eval_loss 수렴 확인, 체크포인트 정상 저장 |

### 2단계 — 본 학습 (Week 3-4)

| 항목 | 값 |
|------|----|
| 인프라 | RunPod — H100 × 8 |
| 데이터 규모 | 300만 건 (AI Hub 한국어 데이터셋) |
| 베이스 모델 | Qwen3-4B |
| 학습 방법 | QLoRA fine-tuning (transformers + peft + trl) |
| 완료 조건 | 아래 평가 기준 충족 |

## 평가 기준

| 기준 | 목표값 |
|------|--------|
| KR-GATE 50문항 정확도 | 96% 이상 |
| 금지 오답 (hallucination · 개인정보 · 욕설) | 0건 |
| 체크포인트 manifest 서명 | 유효 |
| promotion gate | `blocked_promotion=False` 전환 후 수동 승인 |

## Promotion 절차

1. 2단계 학습 완료 → `status=READY`, `ready=True`, `blocked_promotion=False`로 갱신
2. KR-GATE 자동 평가 통과
3. 리뷰어 수동 승인 (PR 필수)
4. `packs/micro_default/` 번들 업데이트 + manifest 서명 갱신
5. CI green 확인 후 main 머지

## 관련 파일

- `scripts/upgrade/train_student_qlora_worldclass_v1.py` — 학습 진입점
- `scripts/upgrade/evaluate_and_promote_v1.py` — 평가·promotion 로직 (Week 3 구현)
- `scripts/upgrade/run_continual_autolearn_cycle_v1.py` — 전체 cycle 오케스트레이터 (Week 2 구현)
