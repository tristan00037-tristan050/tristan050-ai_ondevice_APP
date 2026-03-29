# 주간 진행현황 — AI-24 Judge + Hard-case 배포 게이트 엔진 v6

기준일: 2026-03-29

| 항목 | 진행률 | 비고 |
|---|---:|---|
| fail-closed 게이트 로직 | 99% | `gate_basis=fail_reasons_empty` 유지 |
| dataset validator | 97% | malformed / imbalance / leakage / duplicate prompt 반영 |
| rule judge 실동작 | 95% | `judge_score`, `judge_source`, `judge_confidence` 실제 값 |
| hard-case / adversarial 세트 | 96% | 50건 / refusal 15건 이상 |
| dry-run / pytest / shell 검증 | 100% | GPU 없이 완료 |
| Markdown 리포트 | 97% | hardcase, rule judge, 재현성 metadata 반영 |
| real-run GPU 실측 | 20% | 운영 환경 필요 |
| LLM-as-judge calibration | 35% | rule judge 이후 후속 단계 |
| human spot check 운영 | 25% | 규칙만 남김 |

전체 완성도: **87%**

## 이번 주 완료
- `eval_judge_rule_v1.py` 추가
- `butler_hardcase_v1.jsonl` 50건 세트 추가
- `eval_domain_v3.py` rule judge 실연동
- `eval_judge_v3.py` hard-case 결과 포함
- `eval_verify_v3.py`에 hard-case/rule judge 검증 추가

## 다음 주 우선순위
- GPU real-run 수행
- judge calibration 경로 추가
- 운영 hard-case 세트 확장
- human spot check 샘플링 규칙 추가
