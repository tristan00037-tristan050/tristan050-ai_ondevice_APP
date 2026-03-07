# ADR: ALGORITHM_EXECUTION_DIRECTIVE_V1_1

- 날짜: 2026-03-07
- 상태: Accepted

## 배경(왜 필요한가)
- 운영/공급망/검증 체계는 강해졌지만, 저사양 기기에서도 체감되는 실제 AI 본체 구조가 아직 약하다.
- 버틀러 본체를 실제품으로 만들기 위해서는 기기 프로파일링 / 모델 사다리 / 예산 기반 라우팅이 필요하다.

## 결정(무엇을 고정/변경하는가)
- 알고리즘팀 다음 단계 핵심 축을 아래 5개로 고정한다.
  1. DEVICE_PROFILE_METRICS_SSOT_V1
  2. MODEL_PACK_CATALOG_V1
  3. ROUTING_BY_BUDGET_WITH_HYSTERESIS_V1
  4. EXEC_MODE_AI_QUALITY_GATES_V1
  5. MODEL_PACK_SBOM_AND_TUF_WIRING_V1

## 대안(왜 다른 선택을 안 했나)
- 단일 소형 모델 1개만으로는 저사양~고사양 기기 전체에서 체감 품질과 반응성을 동시에 만족시키기 어렵다.
- 문서형 SSOT 과다는 시간이 지날수록 파싱/운영 드리프트를 낳는다.

## 영향(개발/운영/보안/상품성)
- 개발: 버틀러 본체의 실제 AI 실체가 명확해진다.
- 운영: 기존 fail-closed/verify 체인 위에 pack/device 기반 품질 추적이 올라간다.
- 보안: 모델팩도 공급망 검증 체인 안으로 편입된다.
- 상품성: 저사양 기기에서도 "항상 반응하는 버틀러"로 체감 품질이 개선된다.

## 검증(DoD/게이트/증빙)
- 후속 PR의 DoD 키로 확인한다.
- SSOT 변경 discipline, CHANGELOG, ADR, 콘솔 Updates/Decisions 반영으로 추적한다.
