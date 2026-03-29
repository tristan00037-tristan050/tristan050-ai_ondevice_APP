# AI-24 v6 Judge + Hard-case 벤치마킹 메모

## 이번 개정의 초점
v4의 확장 슬롯 수준이던 judge 계층을 실제 rule-based judge로 올리고, hard-case/adversarial 50건 세트를 별도 버킷으로 운영 가능한 형태로 바꿨습니다.

## 공식 기준 반영 요약
1. OpenAI 공식 evals 가이드는 success criteria, dataset, graders, eval harness를 분리해 지속적으로 반복하라고 안내합니다.
2. Anthropic 공식 문서는 real-world task distribution과 edge case를 반영한 task-specific eval을 강조합니다.
3. Vertex AI 공식 문서는 evaluation dataset에 prompt / response / reference / baseline_model_response 같은 스키마 정합성을 요구합니다.
4. Qwen3-4B 공식 모델 카드는 thinking이 기본값이므로, 자동 비교 평가에서는 enable_thinking=False를 고정하는 편이 재현성에 유리합니다.

## 이번 구현의 차별점
- `judge_score=None` 제거
- `judge_source='rule_v1'`, `judge_confidence` 실제 기록
- hard-case 5개 버킷을 별도 관리
- `non-refusal hard-case = expected_keywords + rule_judge` 동시 통과
- `must_refuse hard-case = refusal detection` 분리
- verify 단계에서 hard-case 수량과 rule judge를 함께 점검

## OpenAI / Claude / Gemini 대비 격차 축소 방향
- OpenAI 대비: continuous eval + grader 구조를 흉내 내는 judge 계층과 hard-case 세트 확보
- Claude 대비: edge-case 우선, 자동 채점 가능한 평가 구조 강화
- Gemini / Vertex 대비: strict schema + dataset validation + calibration-ready 필드 확보
- 다음 단계: LLM-as-judge calibration, human spot check, pairwise regression review

## 이번 범위에서 의도적으로 제외한 것
- GPU real-run 실측
- baseline 실운영 갱신
- 운영 배포 승인 판정
- human spot check 실데이터 운영
